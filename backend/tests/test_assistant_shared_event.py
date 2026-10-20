from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from backend.api.calendar_schemas import EventCreate
from backend.api.routes import assistant_features, assistant_shared
from backend.core.security import APIError
from backend.features.assistant.feature_replies import result_reply


def event_body():
    return EventCreate(
        title="开会",
        start_date="2026-09-22",
        start_time="19:00",
        end_date="2026-09-22",
        end_time="20:00",
    )


def test_shared_event_is_created_and_shared_in_one_transaction(monkeypatch):
    household_id, user_id, event_id = uuid4(), uuid4(), uuid4()
    session = Mock()
    session.scalar.return_value = uuid4()
    saved = Mock()
    monkeypatch.setattr(assistant_shared, "save_settings", saved)
    monkeypatch.setattr(
        assistant_shared,
        "CalendarEvent",
        lambda **fields: SimpleNamespace(id=event_id, **fields),
    )
    monkeypatch.setattr(
        assistant_shared, "output", lambda row: SimpleNamespace(id=row.id)
    )
    result = assistant_shared.create_shared_event(
        household_id,
        event_body(),
        SimpleNamespace(id=user_id, timezone="Asia/Shanghai"),
        session,
    )
    assert result.id == event_id
    assert session.add.call_args.args[0].owner_id == user_id
    assert saved.call_args.args[:3] == (session, "event", event_id)
    assert saved.call_args.args[3].scope == "household"
    assert saved.call_args.args[3].household_id == household_id
    session.commit.assert_called_once()


def test_shared_event_rolls_back_when_sharing_fails(monkeypatch):
    session = Mock()
    session.scalar.return_value = uuid4()
    monkeypatch.setattr(
        assistant_shared, "save_settings", Mock(side_effect=RuntimeError("failure"))
    )
    with pytest.raises(RuntimeError):
        assistant_shared.create_shared_event(
            uuid4(),
            event_body(),
            SimpleNamespace(id=uuid4(), timezone="Asia/Shanghai"),
            session,
        )
    session.rollback.assert_called_once()
    session.commit.assert_not_called()


def test_shared_event_rechecks_membership_at_confirmation():
    session = Mock()
    session.scalar.return_value = None
    with pytest.raises(APIError):
        assistant_shared.create_shared_event(
            uuid4(),
            event_body(),
            SimpleNamespace(id=uuid4(), timezone="Asia/Shanghai"),
            session,
        )
    session.add.assert_not_called()


def test_household_summary_omits_member_emails():
    reply = result_reply(
        "get_household",
        {
            "id": str(uuid4()),
            "name": "示例家庭",
            "members": [{"display_name": "成员甲", "email": "hidden@example.test"}],
        },
    )
    assert "成员甲" in reply.message
    assert "hidden@example.test" not in reply.message


def test_shared_event_preview_binds_household_before_confirmation():
    household_id = uuid4()
    session, store = Mock(), Mock()
    session.scalars.return_value = [SimpleNamespace(id=household_id, name="示例家庭")]
    reply = assistant_features.feature_reply(
        "create_shared_event",
        {
            "household_id": "示例家庭",
            "body": event_body().model_dump(mode="json"),
        },
        store,
        SimpleNamespace(id=uuid4()),
        session,
        uuid4(),
    )
    assert reply.kind == "confirm"
    assert "示例家庭" in reply.message
    assert str(household_id) in store.set.call_args.args[1]
