from types import SimpleNamespace
from uuid import uuid4

from backend.features.assistant import access
from backend.features.assistant.threads import ThreadItem


def test_recent_created_item_is_available_to_followup(monkeypatch):
    item = ThreadItem(id=uuid4(), title="订去马来西亚的机票", status="ongoing")
    action = SimpleNamespace(result={"items": [item.model_dump(mode="json")]})
    session = SimpleNamespace(scalars=lambda _: [action])
    user = SimpleNamespace(id=uuid4())
    thread = SimpleNamespace(last_results=[], messages=[])
    monkeypatch.setattr(access, "current_item", lambda *_: item)
    monkeypatch.setattr(access, "current_data", lambda *_: {"title": item.title})
    monkeypatch.setattr("backend.features.assistant.history.messages", lambda *_: [])

    history, results = access.current_context(session, user, thread, uuid4())

    assert history == []
    assert results == [
        {
            "index": 1,
            "reference_origin": "recent_action",
            **item.model_dump(mode="json"),
            "data": {"title": item.title},
        }
    ]

    monkeypatch.setattr(access, "current_item", lambda *_: None)
    assert access.current_context(session, user, thread, uuid4())[1] == []


def test_latest_query_results_are_distinguished_from_other_historical_candidates(
    monkeypatch,
):
    todo = ThreadItem(id=uuid4(), title="接孩子", status="ongoing")
    event = ThreadItem(id=uuid4(), title="去超市", kind="event", status="scheduled")
    older = ThreadItem(id=uuid4(), title="旧清单", kind="checklist", status="available")
    session = SimpleNamespace(
        scalars=lambda _: [
            SimpleNamespace(result={"items": [older.model_dump(mode="json")]})
        ]
    )
    thread = SimpleNamespace(last_results=[todo, event], messages=[])
    monkeypatch.setattr(access, "current_item", lambda session, user, item: item)
    monkeypatch.setattr(access, "current_data", lambda *_: {})
    monkeypatch.setattr("backend.features.assistant.history.messages", lambda *_: [])
    _, results = access.current_context(
        session, SimpleNamespace(id=uuid4()), thread, uuid4()
    )
    assert [(item["title"], item["reference_origin"]) for item in results] == [
        ("接孩子", "last_result"),
        ("去超市", "last_result"),
        ("旧清单", "recent_action"),
    ]
