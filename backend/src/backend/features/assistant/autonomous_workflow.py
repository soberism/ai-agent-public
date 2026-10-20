"""A bounded discover-describe-read loop for the future autonomous agent."""

import json
import re

from fastapi.encoders import jsonable_encoder
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from pydantic import ValidationError

from backend.core.security import APIError
from backend.features.assistant import tool_registry
from backend.features.assistant.answer_repair import revise_answer
from backend.features.assistant.autonomous_guards import (
    after_step,
    finish,
    incomplete_query,
    named_todo_mismatch,
    stall,
)
from backend.features.assistant.autonomous_plan import propose
from backend.features.assistant.autonomous_reason import reason
from backend.features.assistant.autonomous_types import (
    AutonomousContext,
    AutonomousState,
    Decision,
    initial_state,
)
from backend.features.assistant.preferences import sensitive
from backend.features.assistant.web_search import search_web


def route(state: AutonomousState):
    return {
        "search_tools": "discover",
        "describe_tools": "describe",
        "read_api": "read",
        "retrieve_knowledge": "retrieve",
        "web_search": "web_search",
        "propose_actions": "propose",
        "final_answer": END,
        "revise_answer": "revise_answer",
    }[state["decision"]["action"]]


def discover(state: AutonomousState):
    decision = Decision.model_validate(state["decision"])
    found = tool_registry.search(f"{state['prompt']} {decision.query}", limit=10)
    if not found:
        return finish(
            "这次没能找到合适的查询或操作方式。可以换个说法，或先告诉我想处理的那一件事。"
        )
    known = {item["name"] for item in state["discovered_tools"]}
    if all(item["name"] in known for item in found):
        if state.get("search_retries", 0):
            return stall(
                state,
                "search",
                "这次还没能确认你要查或要处理的具体事项。可以再试一次，或补充事项名称等线索。",
            )
        described = {item["name"] for item in state["described_tools"]}
        next_tool = next(
            (item for item in found if item["name"] not in described),
            None,
        )
        if next_tool:
            return {
                "described_tools": [
                    *state["described_tools"],
                    tool_registry.describe(next_tool["name"]),
                ][-10:],
                "search_retries": 1,
            }
        return stall(
            state,
            "search",
            "这次还没能确认你要查或要处理的具体事项。可以再试一次，或补充事项名称等线索。",
        )
    merged = {item["name"]: item for item in [*found, *state["discovered_tools"]]}
    described = state["described_tools"]
    if found[0]["mode"] == "write" and found[0]["name"] not in {
        item["name"] for item in described
    }:
        described = [*described, tool_registry.describe(found[0]["name"])][-10:]
    return {
        "discovered_tools": list(merged.values())[:20],
        "described_tools": described,
        "search_retries": 0,
        "stalled_on": "",
    }


def describe(state: AutonomousState):
    decision = Decision.model_validate(state["decision"])
    candidates = {item["name"] for item in state["discovered_tools"]}
    if not set(decision.names) <= candidates:
        return finish("这次没能完成查询，请再试一次。")
    described = {item["name"]: item for item in state["described_tools"]}
    described.update((name, tool_registry.describe(name)) for name in decision.names)
    return {"described_tools": list(described.values())[-10:]}


def read(state: AutonomousState, runtime: Runtime[AutonomousContext]):
    if state["read_count"] >= runtime.context.max_reads:
        return incomplete_query(state)
    decision = Decision.model_validate(state["decision"])
    tools = {item["name"]: item for item in state["described_tools"]}
    selected = tools.get(decision.tool_name)
    if selected is None:
        discovered = {item["name"]: item for item in state["discovered_tools"]}
        candidate = discovered.get(decision.tool_name)
        if candidate is None:
            try:
                candidate = tool_registry.describe(decision.tool_name)
            except ValueError:
                return stall(
                    state,
                    f"invalid-read:unknown-tool:{decision.tool_name}",
                    "这次没能找到适合的查询方式。可以换个说法再试一次。",
                )
        selected = tool_registry.describe(decision.tool_name)
    if selected["mode"] != "read":
        return stall(
            state,
            f"write:{decision.tool_name}",
            "这次还没能生成修改方案。如果需要修改，我会先列出内容供你确认。",
        )
    _, model = tool_registry.contract(decision.tool_name)
    try:
        arguments = model.model_validate(decision.arguments).model_dump(
            mode="json", exclude_unset=True
        )
    except ValueError as error:
        key = f"invalid-read:{decision.tool_name}:{json.dumps(decision.arguments, sort_keys=True, ensure_ascii=False)}"
        if state.get("stalled_on", "").startswith(key):
            return finish(
                "这次没能确定要查询的具体内容。可以再试一次，或补充事项名称、日期等线索。"
            )
        missing = (
            [
                ".".join(map(str, item["loc"]))
                for item in error.errors()
                if item["type"] == "missing"
            ]
            if isinstance(error, ValidationError)
            else []
        )
        return {
            "described_tools": [*state["described_tools"], selected][-10:]
            if selected["name"] not in tools
            else state["described_tools"],
            "stalled_on": f"{key}; 缺少字段: {', '.join(missing) or '请核对已展开工具 Schema'}",
        }
    fingerprint = json.dumps(
        [decision.tool_name, arguments], ensure_ascii=False, sort_keys=True
    )
    if fingerprint in state["seen_reads"]:
        return stall(
            state,
            f"read:{fingerprint}",
            "相同的数据查询已经执行过，请根据已有结果回答或明确缺少的信息。",
        )
    try:
        result = runtime.context.reader(decision.tool_name, arguments)
    except APIError as error:
        if error.code == "TOO_MANY_EVENTS":
            return finish(error.message)
        if error.status < 500:
            raise
        result = {"error": error.code, "status": "error", "complete": False}
    if isinstance(result, str):
        result = json.loads(result)
    result = jsonable_encoder(result)
    mismatch = named_todo_mismatch(state, decision.tool_name, result, selected, tools)
    if mismatch:
        return mismatch
    serialized = json.dumps(result, ensure_ascii=False)
    if (
        len(serialized) > 14000
        or len(json.dumps(state["observations"], ensure_ascii=False)) + len(serialized)
        > 40000
    ):
        return finish(
            "这次查到的内容较多，暂时无法完整展示。可以先指定一个事项或一段时间。"
        )
    return {
        "described_tools": [*state["described_tools"], selected][-10:]
        if selected["name"] not in tools
        else state["described_tools"],
        "observations": [
            *state["observations"],
            {
                "tool_name": decision.tool_name,
                "arguments": arguments,
                "result": result,
            },
        ],
        "seen_reads": [*state["seen_reads"], fingerprint],
        "read_count": state["read_count"] + 1,
        "search_retries": 0,
        "stalled_on": "",
    }


def retrieve(state: AutonomousState, runtime: Runtime[AutonomousContext]):
    if state.get("knowledge_count", 0) >= runtime.context.max_knowledge:
        return incomplete_query(state, knowledge=True)
    decision = Decision.model_validate(state["decision"])
    results = runtime.context.retriever(decision.query)
    if len(json.dumps([*state["knowledge"], *results], ensure_ascii=False)) > 16000:
        return finish(
            "这次找到的资料内容较多，暂时无法完整整理。可以指定一份资料，或先问其中一个问题。"
        )
    return {
        "knowledge": [*state["knowledge"], *results],
        "knowledge_count": state.get("knowledge_count", 0) + 1,
    }


def web_search(state: AutonomousState):
    decision = Decision.model_validate(state["decision"])
    query = decision.query.strip()
    if len(query) > 200:
        return finish("搜索词过长，请缩短后重试。")
    if state["observations"] or state["knowledge"] or state["web_results"]:
        return finish("不能将应用内数据用于联网搜索，请单独提出公开搜索问题。")
    if sensitive(query) or re.search(
        r"[\w.+-]+@[\w.-]+|(?<!\d)1[3-9]\d{9}(?!\d)", query
    ):
        return finish("搜索词可能包含私人信息，请改用公开关键词。")
    results = search_web({"query": query})
    if not results:
        return finish("这次搜索没有找到有效来源，请换个关键词再试。")
    return {
        "web_results": results,
        "described_tools": [
            *state["described_tools"],
            tool_registry.describe("create_checklist"),
        ][-10:],
    }


builder = StateGraph(AutonomousState, context_schema=AutonomousContext)
builder.add_node("reason", reason)
builder.add_node("discover", discover)
builder.add_node("describe", describe)
builder.add_node("read", read)
builder.add_node("retrieve", retrieve)
builder.add_node("web_search", web_search)
builder.add_node("propose", propose)
builder.add_node("revise_answer", revise_answer)
builder.add_edge("revise_answer", "reason")
builder.add_edge(START, "reason")
builder.add_conditional_edges("reason", route)
builder.add_conditional_edges("discover", after_step)
builder.add_conditional_edges("describe", after_step)
builder.add_conditional_edges("read", after_step)
builder.add_conditional_edges("retrieve", after_step)
builder.add_conditional_edges("web_search", after_step)
builder.add_conditional_edges(
    "propose",
    lambda state: (
        END
        if state.get("approval") or state["decision"]["action"] == "final_answer"
        else "reason"
    ),
)
graph = builder.compile()


def run(
    prompt: str,
    context: AutonomousContext,
    history=None,
    checkpointer=None,
    config=None,
    command=None,
    context_data=None,
):
    runnable = builder.compile(checkpointer=checkpointer) if checkpointer else graph
    return runnable.invoke(
        command or initial_state(prompt, history, **(context_data or {})),
        context=context,
        config=config,
    )
