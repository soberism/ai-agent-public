from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4


def test_navigation_history_is_not_treated_as_revoked_business_data(monkeypatch):
    from backend.features.assistant import access, history

    message = "请在材料管理页面继续操作。"
    item = {
        "id": str(uuid4()),
        "title": "材料管理",
        "kind": "navigation",
        "status": "available",
        "url": "/documents",
    }
    monkeypatch.setattr(
        history,
        "messages",
        lambda *_: [SimpleNamespace(kind="message", items=[item], content=message)],
    )
    thread = SimpleNamespace(
        last_results=[], messages=[SimpleNamespace(role="assistant", content=message)]
    )
    session = Mock()
    session.scalars.return_value = []
    context, _ = access.current_context(session, Mock(), thread, uuid4())
    assert context[0]["content"] == message
