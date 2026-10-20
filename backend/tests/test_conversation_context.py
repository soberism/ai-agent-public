import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.core.security import APIError
from backend.features.assistant import autonomous_model
from backend.features.assistant import conversation_context as memory
from backend.features.assistant.answer_guard import guard_decision
from backend.features.assistant.autonomous_types import Decision, initial_state
from backend.features.assistant.model_input import build_model_input


class Store:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, ex):
        self.values[key] = value


def exchanges(count):
    return [
        message
        for i in range(count)
        for message in (
            {"role": "user", "content": f"讨论第{i}项计划"},
            {"role": "assistant", "content": f"第{i}项的历史回答"},
        )
    ]


@pytest.mark.parametrize(
    "prompt", ["后天呢", "只看没完成的", "第二条展开说说", "换一个", "你好"]
)
def test_context_is_available_without_keyword_gates(prompt):
    messages = exchanges(2)
    state = initial_state(
        prompt, history=messages, conversation_summary="更早讨论了旅行"
    )
    inputs = build_model_input(state, "reason")
    assert inputs[:-2] == messages
    assert inputs[-1]["content"] == prompt
    context = json.loads(inputs[-2]["content"])
    assert context["目标"] == prompt
    assert context["会话历史摘要_非当前事实"] == "更早讨论了旅行"
    assert not context["本轮证据"]
    assert "写入确认" in context["对话上下文规则"]
    assert "日期追问规则" not in context


def test_incremental_summary_survives_worker_instances_and_only_adds_new_history(
    monkeypatch,
):
    store, owner, thread = Store(), uuid4(), uuid4()
    calls = []

    def summarize(previous, messages):
        calls.append((previous, messages))
        return f"摘要版本{len(calls)}"

    monkeypatch.setattr(memory, "summarize", summarize)
    messages = exchanges(8)
    recent, summary = memory.prepare(store, owner, thread, messages)
    assert recent == messages[-12:]
    assert calls == [("", messages[:4])]
    assert summary == "摘要版本1"
    assert memory.prepare(store, owner, thread, messages) == (recent, summary)
    assert len(calls) == 1
    extended = exchanges(9)
    memory.prepare(store, owner, thread, extended)
    assert calls[-1] == ("摘要版本1", extended[4:6])


def test_threads_and_owners_do_not_share_summaries_and_cache_loss_rebuilds(monkeypatch):
    store, owner, thread = Store(), uuid4(), uuid4()
    calls = []
    monkeypatch.setattr(
        memory, "summarize", lambda old, new: calls.append(old) or "摘要"
    )
    memory.prepare(store, owner, thread, exchanges(8))
    memory.prepare(store, owner, uuid4(), exchanges(8))
    memory.prepare(store, uuid4(), thread, exchanges(8))
    store.values.clear()
    memory.prepare(store, owner, thread, exchanges(8))
    assert calls == ["", "", "", ""]


def test_permission_redaction_or_history_trim_rebuilds_instead_of_reusing_old_summary(
    monkeypatch,
):
    store, owner, thread = Store(), uuid4(), uuid4()
    calls = []
    monkeypatch.setattr(
        memory, "summarize", lambda old, new: calls.append((old, new)) or "摘要"
    )
    messages = exchanges(10)
    memory.prepare(store, owner, thread, messages)
    redacted = [dict(item) for item in messages]
    redacted[1]["content"] = "历史共享内容已不可访问"
    memory.prepare(store, owner, thread, redacted)
    assert calls[-1][0] == ""
    assert calls[-1][1][1]["content"] == "历史共享内容已不可访问"
    memory.prepare(store, owner, thread, redacted[2:])
    assert calls[-1][0] == ""


def test_summary_failure_does_not_advance_cached_prefix(monkeypatch):
    store, owner, thread = Store(), uuid4(), uuid4()
    monkeypatch.setattr(memory, "summarize", lambda *_: "已有摘要")
    memory.prepare(store, owner, thread, exchanges(8))
    previous = store.values.copy()

    def unavailable(*_):
        raise APIError(503, "MODEL_UNAVAILABLE", "摘要不可用")

    monkeypatch.setattr(memory, "summarize", unavailable)
    recent, summary = memory.prepare(store, owner, thread, exchanges(9))
    assert recent == exchanges(9)[-12:]
    assert "已有摘要" in summary and "未覆盖全部旧消息" in summary
    assert "先请用户澄清" in summary
    assert store.values == previous


def test_long_messages_and_summary_share_model_input_budget(monkeypatch):
    monkeypatch.setattr(memory, "summarize", lambda *_: "旧对话摘要")
    messages = exchanges(10)
    for message in messages:
        message["content"] *= 150
    recent, summary = memory.prepare(Store(), uuid4(), uuid4(), messages)
    assert sum(len(item["content"]) for item in recent) <= memory.RECENT_CHARS
    state = initial_state("继续", history=recent, conversation_summary=summary)
    inputs = build_model_input(state, "reason")
    assert sum(len(item["content"]) for item in inputs) <= 12000


@pytest.mark.parametrize(
    "finish,content", [("length", "不完整"), ("stop", ""), ("stop", "字" * 2401)]
)
def test_summary_rejects_truncated_empty_or_oversized_model_output(
    monkeypatch, finish, content
):
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason=finish, message=SimpleNamespace(content=content)
            )
        ]
    )
    api = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_: response))
    )
    monkeypatch.setattr(autonomous_model, "client", lambda: api)
    with pytest.raises(APIError):
        memory.summarize("", exchanges(1))


def test_semantic_followup_requires_current_read_and_explicit_new_topic_wins():
    state = initial_state(
        "后天呢", history=exchanges(2), conversation_summary="曾查过待办"
    )
    decision = Decision(
        action="final_answer",
        resolved_request="查看后天有哪些待办",
        requires_current_data=True,
        answer="后天没有待办。",
    )
    assert guard_decision(state, decision).action == "search_tools"
    greeting = Decision(action="final_answer", resolved_request="你好", answer="你好")
    assert guard_decision(state, greeting) == greeting
    assert initial_state("你好")["conversation_summary"] == ""
    assert initial_state("你好")["observations"] == []
    assert initial_state("你好")["approval"] == {}


def test_fact_answer_without_structured_evidence_is_revised_not_published():
    state = initial_state("查看我今天的待办")
    state["observations"] = [
        {
            "tool_name": "list_events",
            "arguments": {},
            "result": {"items": [], "complete": True, "total_count": 0},
        }
    ]
    decision = Decision(
        action="final_answer", answer_kind="business", answer="今天没有待办。"
    )
    assert guard_decision(state, decision).action == "revise_answer"


def test_first_summary_failure_preserves_recent_context_without_caching(monkeypatch):
    store = Store()

    def failed(*_):
        raise APIError(503, "SERVICE_UNAVAILABLE", "对话摘要不完整")

    monkeypatch.setattr(memory, "summarize", failed)
    recent, summary = memory.prepare(store, uuid4(), uuid4(), exchanges(15))
    assert recent == exchanges(15)[-12:]
    assert "摘要暂不可用" in summary
    assert not store.values
    inputs = build_model_input(
        initial_state("有什么待办和日程", history=recent, conversation_summary=summary),
        "reason",
    )
    assert inputs[-1]["content"] == "有什么待办和日程"
    assert inputs[:-2] == recent


def test_summary_fallback_does_not_hide_authorization_errors(monkeypatch):
    def forbidden(*_):
        raise APIError(403, "FORBIDDEN", "拒绝访问")

    monkeypatch.setattr(memory, "summarize", forbidden)
    with pytest.raises(APIError) as error:
        memory.prepare(Store(), uuid4(), uuid4(), exchanges(8))
    assert error.value.status == 403
