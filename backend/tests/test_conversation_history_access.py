from types import SimpleNamespace
from uuid import uuid4

from backend.features.assistant import access, history
from backend.features.assistant.threads import ThreadItem


def test_authorized_assistant_body_survives_and_revocation_removes_entire_body(
    monkeypatch,
):
    item = ThreadItem(id=uuid4(), title="共享事项", status="ongoing")
    content = "第二条的地点是会议室A，负责人待确认。"
    saved = SimpleNamespace(
        kind="result", content=content, items=[item.model_dump(mode="json")]
    )
    thread = SimpleNamespace(
        last_results=[], messages=[SimpleNamespace(role="assistant", content=content)]
    )
    session = SimpleNamespace(scalars=lambda _: [])
    monkeypatch.setattr(history, "messages", lambda *_: [saved])
    monkeypatch.setattr(access, "current_item", lambda *_: item)
    safe, _ = access.current_context(
        session, SimpleNamespace(id=uuid4()), thread, uuid4()
    )
    assert safe[0]["content"] == content
    monkeypatch.setattr(access, "current_item", lambda *_: None)
    safe, _ = access.current_context(
        session, SimpleNamespace(id=uuid4()), thread, uuid4()
    )
    assert "会议室A" not in str(safe)
    assert "不可访问" in safe[0]["content"]


def test_legacy_result_without_references_is_not_reintroduced_as_history(monkeypatch):
    content = "旧共享事项细节"
    saved = SimpleNamespace(kind="result", content=content, items=None)
    thread = SimpleNamespace(
        last_results=[], messages=[SimpleNamespace(role="assistant", content=content)]
    )
    monkeypatch.setattr(history, "messages", lambda *_: [saved])
    safe, _ = access.current_context(
        SimpleNamespace(scalars=lambda _: []),
        SimpleNamespace(id=uuid4()),
        thread,
        uuid4(),
    )
    assert content not in str(safe)
    assert "可复核对象引用" in safe[0]["content"]


def test_review_references_keep_todo_and_event_domains_for_next_turn_access_checks():
    todo, event = str(uuid4()), str(uuid4())
    references = access.observation_references(
        [
            {
                "tool_name": "review_plan",
                "result": {
                    "details": {
                        "completed": [{"id": todo, "title": "待办一"}],
                        "ongoing": [],
                        "events": [{"id": event, "title": "日程一"}],
                    }
                },
            }
        ]
    )
    assert {(item["id"], item["kind"]) for item in references} == {
        (todo, "todo"),
        (event, "event"),
    }
