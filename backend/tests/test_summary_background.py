"""摘要任务去重、等待、超时及历史边界。"""

from uuid import uuid4

from test_conversation_context import Store, exchanges

from backend.features.assistant import conversation_context as memory
from backend.features.assistant import summary_jobs as jobs
from backend.features.assistant.autonomous_types import initial_state
from backend.features.assistant.model_input import selected_history


def put(store, owner, thread, messages, count):
    store.set(
        jobs.keys(thread)[0],
        memory.ConversationMemory(
            owner_id=str(owner),
            covered=count,
            digest=memory.fingerprint(messages[:count]),
            summary="历史摘要",
        ).model_dump_json(),
        ex=1800,
    )


def test_ready_summary_is_used_without_dispatch_or_wait(monkeypatch):
    store, owner, thread, messages = Store(), uuid4(), uuid4(), exchanges(8)
    put(store, owner, thread, messages, 4)
    monkeypatch.setattr(
        jobs, "request", lambda *_: (_ for _ in ()).throw(AssertionError())
    )
    assert jobs.prepare(store, owner, thread, messages) == (messages[4:], "历史摘要")


def test_fast_followup_waits_for_existing_task(monkeypatch):
    store, owner, thread, messages = Store(), uuid4(), uuid4(), exchanges(8)
    calls = []
    monkeypatch.setattr(jobs, "request", lambda *_: calls.append("join") or True)
    monkeypatch.setattr(jobs, "sleep", lambda _: put(store, owner, thread, messages, 4))
    assert jobs.prepare(store, owner, thread, messages) == (messages[4:], "历史摘要")
    assert calls == ["join"]


def test_timeout_keeps_uncovered_messages_and_old_valid_summary(monkeypatch):
    store, owner, thread, messages = Store(), uuid4(), uuid4(), exchanges(9)
    put(store, owner, thread, messages, 4)
    monkeypatch.setattr(jobs, "WAIT_SECONDS", 0)
    monkeypatch.setattr(jobs, "request", lambda *_: True)
    recent, summary = jobs.prepare(store, owner, thread, messages)
    assert recent == messages[4:] and len(recent) > 12 and summary == "历史摘要"
    state = initial_state("继续", history=recent, history_prepared=True)
    assert selected_history(state) == recent


def test_permission_revision_and_foreign_owner_discard_old_summary(monkeypatch):
    store, owner, thread, messages = Store(), uuid4(), uuid4(), exchanges(8)
    put(store, owner, thread, messages, 4)
    monkeypatch.setattr(jobs, "request", lambda *_: False)
    changed = [dict(m) for m in messages]
    changed[1]["content"] = "此前内容已不可访问"
    assert jobs.prepare(store, owner, thread, changed) == (changed, "")
    assert jobs.prepare(store, uuid4(), thread, messages) == (messages, "")


def test_fallback_is_bounded_and_explains_missing_context(monkeypatch):
    messages = exchanges(30)
    for item in messages:
        item["content"] *= 100
    monkeypatch.setattr(jobs, "request", lambda *_: False)
    recent, summary = jobs.prepare(Store(), uuid4(), uuid4(), messages)
    assert sum(len(m["content"]) for m in recent) <= memory.RECENT_CHARS
    assert "未能完整纳入" in summary and "先澄清" in summary
