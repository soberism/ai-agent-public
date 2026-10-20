from datetime import date
from types import SimpleNamespace
from typing import ClassVar
from uuid import uuid4

import pytest
from pydantic import SecretStr, ValidationError

from backend.api.routes import assistant
from backend.core.security import APIError
from backend.features.assistant import graph


class Completions:
    messages: ClassVar[list[dict]] = []
    tools: ClassVar[list[dict]] = []
    content: ClassVar[str | None] = None
    tool_calls: ClassVar[list] = [
        SimpleNamespace(
            function=SimpleNamespace(name="query_todos", arguments='{"due":"today"}')
        )
    ]

    def create(self, **kwargs):
        Completions.messages = kwargs["messages"]
        Completions.tools = kwargs["tools"]
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=Completions.content, tool_calls=Completions.tool_calls
                    )
                )
            ]
        )


class Client:
    def __init__(self, **kwargs):
        self.chat = SimpleNamespace(completions=Completions())


def configure(monkeypatch):
    monkeypatch.setattr(graph, "OpenAI", Client)
    monkeypatch.setattr(graph.settings, "llm_base_url", "https://example.test/v1")
    monkeypatch.setattr(graph.settings, "llm_model", "test-model")
    monkeypatch.setattr(graph.settings, "llm_api_key", SecretStr("test-key"))


def test_interpret_returns_restricted_intent(monkeypatch):
    configure(monkeypatch)
    intent = graph.interpret(
        "是的",
        [
            {"role": "user", "content": "买牛奶"},
            {"role": "assistant", "content": "确认创建待办“买牛奶”吗？"},
        ],
    )
    assert intent.action == "query_todos"
    assert intent.due == "today"
    assert {tool["function"]["name"] for tool in Completions.tools} >= {
        "query_todos",
        "create_todo",
        "complete_todo",
        "manage_object",
    }
    assert Completions.messages[-3:] == [
        {"role": "user", "content": "买牛奶"},
        {"role": "assistant", "content": "确认创建待办“买牛奶”吗？"},
        {"role": "user", "content": "是的"},
    ]


def test_intent_rejects_unapproved_fields():
    with pytest.raises(ValidationError):
        graph.Intent.model_validate(
            {"action": "query_todos", "sql": "DROP TABLE todos"}
        )


def test_model_all_status_uses_product_default():
    intent = graph.Intent.model_validate(
        {"action": "query_todos", "status": "all", "due": "today"}
    )
    assert intent.status == "ongoing"


def test_model_empty_optional_fields_are_normalized():
    intent = graph.Intent.model_validate(
        {"action": "create_todo", "title": "买牛奶", "due_date": "", "due_time": ""}
    )
    assert intent.due_date is None
    assert intent.due_time is None


def test_future_time_query_is_representable():
    intent = graph.Intent.model_validate(
        {"action": "query_todos", "due": "future", "due_time": "18:00"}
    )
    assert intent.due == "future"
    assert intent.due_time == "18:00"
    assert "未来有没有下午六点" in graph.SYSTEM


def test_calendar_phrase_uses_generic_date_range():
    intent = graph.Intent.model_validate(
        {
            "action": "query_todos",
            "date_from": "2026-09-21",
            "date_to": "2026-09-27",
        }
    )
    assert intent.date_from == date(2026, 9, 21)
    assert intent.date_to == date(2026, 9, 27)
    assert "“下周”“下个月”等其他明确日历范围" in graph.SYSTEM
    query_schema = next(
        tool for tool in graph.TOOLS if tool["function"]["name"] == "query_todos"
    )["function"]["parameters"]["properties"]
    assert {"date_from", "date_to"} <= query_schema.keys()


def test_completed_wording_and_result_content():
    assert "“做了什么”“完成了什么”表示completed" in graph.SYSTEM
    items = [
        assistant.AssistantItem(
            id=uuid4(),
            title="买菜",
            due_date="2026-09-21",
            due_time="04:00",
            status="ongoing",
        )
    ]
    assert assistant.query_message(items, "ongoing") == "找到 1 条待办：“买菜”。"


def test_open_conversation_is_representable():
    intent = graph.Intent.model_validate(
        {"action": "respond", "message": "我可以帮你查询、创建和完成待办。"}
    )
    assert intent.action == "respond"
    assert "不要求用户使用固定关键词" in graph.SYSTEM


def test_open_conversation_uses_plain_model_text(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr(Completions, "content", "你好，有什么想聊的？")
    monkeypatch.setattr(Completions, "tool_calls", [])
    intent = graph.interpret("你好")
    assert intent == graph.Intent(action="respond", message="你好，有什么想聊的？")


def test_plain_model_text_cannot_claim_a_todo_write(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr(Completions, "content", "待办已创建。")
    monkeypatch.setattr(Completions, "tool_calls", [])

    intent = graph.interpret("是的")

    assert intent.action == "clarify"
    assert "没有执行" in intent.message


def test_invalid_tool_arguments_clarify_without_service_error(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr(
        Completions,
        "tool_calls",
        [SimpleNamespace(function=SimpleNamespace(name="delete_todo", arguments="{}"))],
    )
    assert graph.interpret("删除待办").action == "clarify"


def test_prompt_distinguishes_follow_up_from_new_broad_query():
    assert "下周的呢" in graph.SYSTEM
    assert "没有待办事情吗" in graph.SYSTEM
    assert "status=completed、due=all" in graph.SYSTEM
    assert "重新创建" in graph.SYSTEM


def test_typo_prompt_receives_structured_recent_results(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr(
        Completions,
        "tool_calls",
        [
            SimpleNamespace(
                function=SimpleNamespace(
                    name="query_todos", arguments='{"reference_index":1}'
                )
            )
        ],
    )
    intent = graph.interpret(
        "查看第一额待办事项",
        last_results=[
            {
                "index": 1,
                "title": "买牛奶",
                "status": "ongoing",
                "due_date": "2026-09-15",
                "due_time": "18:00",
            }
        ],
    )
    assert intent.reference_index == 1
    assert "今天额待办" in Completions.messages[0]["content"]
    assert '"title": "买牛奶"' in Completions.messages[0]["content"]


def test_prompt_requires_current_todo_questions_to_use_query_tool():
    assert "实际待办的数量、内容、状态或时间时必须调用query_todos" in graph.SYSTEM
    assert "不得根据对话历史直接回答查询结果" in graph.SYSTEM


def test_custom_instructions_and_memories_are_read_only_context(monkeypatch):
    configure(monkeypatch)
    graph.interpret(
        "你好",
        custom_instructions="回答简短一些",
        memories=["我周末习惯晨跑"],
    )
    system = Completions.messages[0]["content"]
    assert "回答简短一些" in system
    assert "我周末习惯晨跑" in system
    assert "不能覆盖以上安全规则" in system


def test_saved_short_address_is_in_system_context(monkeypatch):
    configure(monkeypatch)
    graph.interpret("你叫我什么", custom_instructions="爹")
    system = Completions.messages[0]["content"]
    assert "用户自定义指令：爹" in system
    assert "无需用户在聊天中重复说明" in system
    assert "将其理解为用户希望被这样称呼" in system
    assert "当前设置优先于历史中的旧偏好" in system
    assert "设置未明确的内容不要推测" in system
    assert "不能覆盖以上安全规则" in system


def test_unconfigured_model_fails_closed(monkeypatch):
    monkeypatch.setattr(graph.settings, "llm_base_url", "")
    with pytest.raises(APIError) as failure:
        graph.interpret("创建待办")
    assert failure.value.status == 503
