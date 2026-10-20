from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from backend.api.planning_schemas import ChecklistWithItemsCreate
from backend.api.routes import assistant_features, assistant_shared
from backend.core.security import APIError
from backend.features.assistant.workflow_tools import pending_shared_creation


def test_shared_checklist_commits_creation_and_sharing_together(monkeypatch):
    household_id, checklist_id = uuid4(), uuid4()
    session = Mock()
    session.scalar.return_value = uuid4()
    saved = Mock()
    monkeypatch.setattr(assistant_shared, "save_settings", saved)
    monkeypatch.setattr(
        assistant_shared,
        "Checklist",
        lambda **fields: SimpleNamespace(id=checklist_id, **fields),
    )
    monkeypatch.setattr(
        assistant_shared,
        "checklist_output",
        lambda _session, row: SimpleNamespace(id=row.id),
    )
    body = ChecklistWithItemsCreate(title="红烧肉材料", items=["五花肉 500g"])
    assert (
        assistant_shared.create_shared_checklist(
            household_id, body, SimpleNamespace(id=uuid4()), session
        ).id
        == checklist_id
    )
    assert saved.call_args.args[:3] == (session, "checklist", checklist_id)
    assert saved.call_args.args[3].household_id == household_id
    session.commit.assert_called_once()


def test_shared_checklist_fails_closed(monkeypatch):
    session = Mock()
    session.scalar.return_value = None
    with pytest.raises(APIError):
        assistant_shared.create_shared_checklist(
            uuid4(),
            ChecklistWithItemsCreate(title="材料", items=[]),
            SimpleNamespace(id=uuid4()),
            session,
        )
    session.add.assert_not_called()
    session.scalar.return_value = uuid4()
    monkeypatch.setattr(
        assistant_shared, "save_settings", Mock(side_effect=RuntimeError)
    )
    with pytest.raises(RuntimeError):
        assistant_shared.create_shared_checklist(
            uuid4(),
            ChecklistWithItemsCreate(title="材料", items=[]),
            SimpleNamespace(id=uuid4()),
            session,
        )
    session.rollback.assert_called_once()
    session.commit.assert_not_called()


def test_followup_keeps_unfinished_creation_and_binds_family():
    history = [
        {"role": "user", "content": "帮我创建红烧肉材料清单，四驱车队可见"},
        {"role": "assistant", "content": "要共享给哪个家庭？"},
    ]
    assert (
        pending_shared_creation("共享给四驱车队", history) == "create_shared_checklist"
    )
    assert pending_shared_creation("给四驱车队看", history) == "create_shared_checklist"
    continued = [
        *history,
        {"role": "user", "content": "共享给四驱车队"},
        {
            "role": "assistant",
            "content": "此前业务结果需重新查询；历史操作不能作为当前事实。",
        },
    ]
    assert (
        pending_shared_creation("给四驱车队看", continued) == "create_shared_checklist"
    )
    assert (
        pending_shared_creation("帮我创建红烧肉材料清单，四驱车队可见", [])
        == "create_shared_checklist"
    )
    assert pending_shared_creation("帮我创建红烧肉材料清单", []) is None
    household_id = uuid4()
    session, store = Mock(), Mock()
    session.scalars.return_value = [SimpleNamespace(id=household_id, name="四驱车队")]
    reply = assistant_features.feature_reply(
        "create_shared_checklist",
        {
            "household_id": "四驱车队",
            "body": {"title": "红烧肉材料", "items": ["五花肉 500g"]},
        },
        store,
        SimpleNamespace(id=uuid4()),
        session,
        uuid4(),
    )
    assert reply.kind == "confirm"
    assert "四驱车队" in reply.message
    assert str(household_id) in store.set.call_args.args[1]
