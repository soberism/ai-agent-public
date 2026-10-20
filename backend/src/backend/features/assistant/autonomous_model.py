"""OpenAI-compatible structured decisions for the autonomous read graph."""

import json

from openai import OpenAI, OpenAIError
from pydantic import ValidationError

from backend.core.langsmith_tracing import traced_model
from backend.core.security import settings, unavailable
from backend.features.assistant import tool_registry
from backend.features.assistant.answer_guard import guard_decision
from backend.features.assistant.autonomous_prompts import SYSTEM
from backend.features.assistant.autonomous_types import AutonomousState, Decision
from backend.features.assistant.model_input import build_model_input


def parse_decision(arguments: str, state: AutonomousState) -> Decision:
    data = json.loads(arguments)
    if isinstance(data, dict):
        name = data.get("action")
        if name == "final_answer" and "answer_kind" not in data:
            raise ValueError("最终回答缺少answer_kind")
        if name == "read_api" and data.get("tool_name") in {
            "get_meals",
            "get_meal_plans",
        }:
            data["tool_name"] = "list_meals"
        if name == "read_api" and data.get("tool_name") == "get_todos":
            data["tool_name"] = "list_todos"
            data["arguments"] = {"query": data.get("arguments", {}).get("query", {})}
        known = {
            item["name"]: item
            for item in [*state["discovered_tools"], *state["described_tools"]]
        }
        if name == "propose_actions" and data.get("tool_name"):
            if "actions" in data:
                raise ValueError("操作计划不能同时使用顶层工具和actions")
            tool = data.get("tool_name")
            selected = known.get(tool)
            if selected is None:
                try:
                    selected = tool_registry.describe(tool)
                except ValueError:
                    selected = None
            if (
                selected
                and selected["mode"] == "write"
                and isinstance(data.get("arguments"), dict)
            ):
                data["actions"] = [
                    {
                        "tool_name": data.pop("tool_name"),
                        "arguments": data.pop("arguments"),
                    }
                ]
        if name in known and known[name]["mode"] == "read":
            data = {
                "action": "read_api",
                "tool_name": name,
                "arguments": data.get("arguments", {}),
            }
    return Decision.model_validate(data)


def client():
    return traced_model(
        OpenAI(
            api_key=settings.llm_api_key.get_secret_value(),
            base_url=settings.llm_base_url,
        )
    )


def same_todo_target(requested: str, actual: str) -> bool:
    """Check whether two different titles refer to the same concrete task."""
    try:
        response = client().chat.completions.create(
            model=settings.llm_model,
            messages=[
                {
                    "role": "system",
                    "content": "判断两个待办名称是否指同一件具体的事。仅名称省略、近义表达可回答「是」；只共享个别词或主题但事情不同必须回答「否」。只输出一个字：是或否。",
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"用户所指": requested, "查到的标题": actual},
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=0,
            timeout=10,
        )
    except OpenAIError:
        return False
    return (response.choices[0].message.content or "").strip() == "是"


def same_checklist_item(prompt: str, title: str) -> bool:
    """Verify that a proposed checklist item is the user's intended item."""
    if title in prompt:
        return True
    try:
        response = client().chat.completions.create(
            model=settings.llm_model,
            messages=[
                {
                    "role": "system",
                    "content": "判断候选清单项是否是用户这句话明确要求操作的项目。清单名称不算项目名称；同属一个清单也不代表是同一项目。只输出一个字：是或否。",
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"用户请求": prompt, "候选清单项": title}, ensure_ascii=False
                    ),
                },
            ],
            temperature=0,
            timeout=10,
        )
    except OpenAIError:
        return False
    return (response.choices[0].message.content or "").strip() == "是"


def direct_read_tools(state: AutonomousState) -> list[dict]:
    candidates = {
        item["name"]: item
        for item in [*state["discovered_tools"], *state["described_tools"]]
        if item["mode"] == "read"
    }
    repairing = state.get("stalled_on", "").startswith("invalid-answer:")
    if state["web_results"] or (state.get("stalled_on") and not repairing):
        return []
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": item["description"],
                "parameters": tool_registry.describe(name)["input_schema"],
            },
        }
        for name, item in list(candidates.items())[:5]
    ]


def decide(state: AutonomousState) -> Decision:
    if not all(
        (
            settings.llm_base_url,
            settings.llm_model,
            settings.llm_api_key.get_secret_value(),
        )
    ):
        raise unavailable("AI服务尚未配置")
    api = client()
    read_tools = direct_read_tools(state)
    decision_schema = Decision.model_json_schema()
    decision_schema["properties"]["action"]["enum"].remove("revise_answer")
    decision_schema["required"] = list(
        dict.fromkeys([*decision_schema.get("required", []), "answer_kind"])
    )
    if state.get("stalled_on") == "plan-required":
        decision_schema["properties"]["action"]["enum"] = ["propose_actions"]
    elif state.get("stalled_on") and not state["stalled_on"].startswith(
        ("invalid-plan:", "invalid-read:", "invalid-answer:")
    ):
        decision_schema["properties"]["action"]["enum"] = [
            "final_answer",
            "propose_actions",
        ]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "agent_decision",
                "description": "搜索工具、检索知识、提出待确认操作或给出最终回答",
                "parameters": decision_schema,
            },
        },
        *read_tools,
    ]
    options = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            *build_model_input(state, "reason"),
        ],
        "tools": tools,
        "temperature": 0,
        "timeout": 20,
    }
    try:
        for attempt in range(2):
            response = api.chat.completions.create(
                **options,
                tool_choice="auto"
                if read_tools and attempt == 0
                else {"type": "function", "function": {"name": "agent_decision"}},
            )
            calls = response.choices[0].message.tool_calls or []
            allowed_reads = {tool["function"]["name"] for tool in read_tools}
            for item in calls:
                call = item.function
                try:
                    if call.name == "agent_decision":
                        decision = parse_decision(call.arguments, state)
                        if (
                            decision.action
                            not in decision_schema["properties"]["action"]["enum"]
                        ):
                            continue
                        return guard_decision(state, decision)
                    if call.name in allowed_reads:
                        return Decision(
                            action="read_api",
                            tool_name=call.name,
                            arguments=json.loads(call.arguments),
                        )
                except ValidationError, ValueError, TypeError:
                    continue
            options["messages"] = [
                *options["messages"],
                {
                    "role": "system",
                    "content": "上次决策不符合工具Schema。请仅调用agent_decision，使用允许的action和准确字段层级；写入必须通过propose_actions的actions列表提出，不能直接调用写工具。",
                },
            ]
        raise ValueError
    except ValidationError, ValueError, KeyError, IndexError, TypeError:
        raise unavailable("AI服务返回了无效的自主决策") from None
    except OpenAIError:
        raise unavailable("AI服务暂时不可用，请稍后重试") from None
