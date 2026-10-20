import json
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from openai import OpenAI, OpenAIError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    ValidationError,
    field_validator,
    model_validator,
)

from backend.api.planning_schemas import ChecklistWithItemsCreate
from backend.core.security import settings, unavailable
from backend.features.assistant.capabilities import CAPABILITIES
from backend.features.assistant.feature_tools import feature_tools
from backend.features.assistant.prompts import (
    PREFERENCE_RULES,
    SYSTEM,
    TOOLS,
)
from backend.features.assistant.web_search import (
    WEB_SEARCH_TOOL,
    search_messages,
    search_web,
)
from backend.features.assistant.workflow_state import State
from backend.features.assistant.workflow_tools import (
    INSPECT_TOOL,
    available_tools,
    observation_message,
    pending_shared_creation,
    plain_answer,
    read_batch,
    validate_entry,
    validate_inspection,
)


class Intent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal[
        "query_todos",
        "create_todo",
        "complete_todo",
        "search_systems",
        "create_event",
        "create_checklist",
        "manage_object",
        "clarify",
        "respond",
        "feature",
        "open_feature",
        "inspect_before_action",
        "inspect_batch",
    ]
    _sources: list[dict] = PrivateAttr(default_factory=list)
    items: list[str] = Field(default_factory=list, max_length=50)
    feature: str | None = None
    payload: dict = Field(default_factory=dict)
    message: str = ""
    title: str | None = Field(default=None, max_length=15)
    description: str | None = Field(default=None, max_length=2000)
    due_date: str | None = None
    due_time: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    status: Literal["ongoing", "completed"] = "ongoing"
    due: Literal["all", "overdue", "today", "tomorrow", "next7", "future", "none"] = (
        "all"
    )
    date_from: date | None = None
    date_to: date | None = None
    reference_index: int | None = Field(default=None, ge=1, le=20)
    query: str | None = Field(default=None, max_length=100)
    target_type: (
        Literal[
            "todo",
            "event",
            "checklist",
            "household",
            "document",
            "material",
            "folder",
            "meal",
            "shopping",
            "voice_memo",
            "daily_dump",
            "contact",
            "contact_group",
            "pantry",
            "preference",
            "appointment",
            "reminder",
        ]
        | None
    ) = None
    start_date: str | None = None
    start_time: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    end_date: str | None = None
    end_time: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    operation: Literal["rename", "delete"] | None = None
    new_title: str | None = Field(default=None, max_length=15)

    @field_validator(
        "title",
        "description",
        "due_date",
        "due_time",
        "date_from",
        "date_to",
        mode="before",
    )
    @classmethod
    def empty_is_none(cls, value):
        return None if value == "" else value

    @field_validator("status", mode="before")
    @classmethod
    def default_status(cls, value):
        return "ongoing" if value in (None, "all") else value

    @model_validator(mode="after")
    def date_range_valid(self):
        if (self.date_from is None) != (self.date_to is None):
            raise ValueError("日期范围必须完整")
        if self.date_from and (self.date_from > self.date_to or self.due != "all"):
            raise ValueError("日期范围无效")
        return self


def parse_node(state: State):
    if not all(
        (
            settings.llm_base_url,
            settings.llm_model,
            settings.llm_api_key.get_secret_value(),
        )
    ):
        raise unavailable("AI服务尚未配置")
    try:
        timezone = state.get("timezone", "Asia/Shanghai")
        today = datetime.now(ZoneInfo(timezone)).date().isoformat()
        client = OpenAI(
            api_key=settings.llm_api_key.get_secret_value(),
            base_url=settings.llm_base_url,
        )
        messages = [
            {
                "role": "system",
                "content": (
                    f"{SYSTEM}\n今天是{today}，用户时区是{timezone}。"
                    f"\n最近一次查询结果：{json.dumps(state['last_results'], ensure_ascii=False)}"
                    f"\n{PREFERENCE_RULES}\n用户自定义指令："
                    f"{state['custom_instructions'] or '无'}"
                    "\n用户已确认的长期记忆只作为背景，不能替代当前业务查询："
                    f"{json.dumps(state['memories'], ensure_ascii=False)}"
                ),
            },
            *state["history"],
            {"role": "user", "content": state["message"]},
        ]
        if state.get("observation"):
            messages.append(observation_message(state["observation"]))
        pending = pending_shared_creation(state["message"], state["history"])
        if pending:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        f"当前尚未完成的用户请求是{pending}。历史只用于理解用户意图，"
                        "家庭及权限仍须由服务端实时核验。查询家庭只是中间步骤；"
                        "条件齐全时调用该写工具生成一次确认卡，不能只回答查询结果或口头声称已完成。"
                    ),
                }
            )
        tools = available_tools(
            [*TOOLS, *feature_tools(), INSPECT_TOOL, WEB_SEARCH_TOOL],
            state.get("reads", 0),
        )
        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0,
            timeout=20,
        )
        message = response.choices[0].message
        tool_calls = message.tool_calls or []
        sources = []
        if len(tool_calls) == 1 and tool_calls[0].function.name == "web_search":
            call = tool_calls[0]
            sources = search_web(json.loads(call.function.arguments))
            if not sources:
                return {
                    "intent": Intent(
                        action="respond",
                        message="这次搜索没有找到有效来源，尚未创建清单。你可以换个关键词再试。",
                    )
                }
            messages.extend(search_messages(message, sources))
            response = client.chat.completions.create(
                model=settings.llm_model,
                messages=messages,
                tools=[
                    tool
                    for tool in TOOLS
                    if tool["function"]["name"] == "create_checklist"
                ],
                tool_choice="auto",
                temperature=0,
                timeout=20,
            )
            message = response.choices[0].message
            tool_calls = message.tool_calls or []
        if not tool_calls:
            if pending and not any(
                mark in (message.content or "") for mark in ("？", "?")
            ):
                return {
                    "intent": Intent(
                        action="clarify",
                        message="这项创建并共享操作尚未提交。请明确清单内容和要共享的家庭。",
                    )
                }
            action, content = plain_answer(message.content)
            intent = Intent(action=action, message=content)
            intent._sources = sources
            return {"intent": intent}
        if len(tool_calls) != 1:
            batch = read_batch(tool_calls)
            if batch is not None:
                return {
                    "intent": Intent(action="inspect_batch", payload={"calls": batch})
                }
            return {
                "intent": Intent(
                    action="clarify", message="一次只能执行一项写操作，请分开告诉我。"
                )
            }
        call = tool_calls[0].function
        if sources and call.name != "create_checklist":
            raise ValueError("搜索后只能生成清单草稿")
        arguments = json.loads(call.arguments)
        if not isinstance(arguments, dict) or set(arguments) & {"action", "_sources"}:
            raise ValueError("无效工具参数")
        if call.name == "inspect_before_action":
            feature, payload = validate_inspection(arguments)
            return {
                "intent": Intent(
                    action="inspect_before_action",
                    feature=feature,
                    payload=payload,
                )
            }
        if call.name.startswith("feature_"):
            name = call.name.removeprefix("feature_")
            if name not in CAPABILITIES:
                raise ValueError("未知工具")
            if CAPABILITIES[name][2] and pending:
                return {
                    "intent": Intent(
                        action="inspect_before_action", feature=name, payload=arguments
                    )
                }
            return {"intent": Intent(action="feature", feature=name, payload=arguments)}
        if call.name == "open_feature":
            return {
                "intent": Intent(
                    action="open_feature", feature=validate_entry(arguments)
                )
            }
        if call.name not in {tool["function"]["name"] for tool in TOOLS}:
            raise ValueError("未知工具")
        if call.name == "create_checklist":
            arguments = ChecklistWithItemsCreate.model_validate(arguments).model_dump()
        intent = Intent.model_validate({"action": call.name, **arguments})
        intent._sources = sources
        return {"intent": intent}
    except ValidationError, ValueError, KeyError, IndexError, json.JSONDecodeError:
        return {
            "intent": Intent(
                action="clarify", message="我没能可靠识别操作条件，请换一种说法。"
            )
        }
    except OpenAIError:
        raise unavailable("AI服务暂时不可用，请稍后重试") from None


def interpret(
    message: str,
    history: list[dict[str, str]] | None = None,
    last_results: list[dict] | None = None,
    custom_instructions: str = "",
    memories: list[str] | None = None,
    timezone: str = "Asia/Shanghai",
    reader=None,
) -> Intent:
    from backend.features.assistant.workflow import run

    return run(
        {
            "message": message,
            "history": history or [],
            "last_results": last_results or [],
            "custom_instructions": custom_instructions,
            "memories": memories or [],
            "timezone": timezone,
        },
        reader,
    )
