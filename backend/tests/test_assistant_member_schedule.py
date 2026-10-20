import json
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from backend.api.routes import assistant_read_steps as reads
from backend.core.security import APIError


def test_member_schedule_reads_keep_linking_ids_without_emails(monkeypatch):
    household_id, account_id = uuid4(), uuid4()
    user, session = SimpleNamespace(id=uuid4()), Mock()
    session.scalars.return_value = [SimpleNamespace(id=household_id, name="四驱车队")]
    observed = []

    def events(query, principal, db):
        observed.append((query, principal, db))
        return SimpleNamespace(
            model_dump=lambda **_: {
                "items": [
                    {
                        "id": str(uuid4()),
                        "assignee_id": str(account_id),
                        "title": "聚餐",
                        "status": "scheduled",
                        "start_date": "2026-09-22",
                        "start_time": "09:00",
                        "end_date": "2026-09-22",
                        "end_time": "10:00",
                    }
                ]
            }
        )

    def household(identifier, principal, db):
        observed.append((identifier, principal, db))
        return SimpleNamespace(
            model_dump=lambda **_: {
                "members": [
                    {
                        "account_id": str(account_id),
                        "display_name": "测试成员甲",
                        "email": "private@example.invalid",
                    }
                ]
            }
        )

    monkeypatch.setattr(reads, "list_events", events)
    monkeypatch.setattr(reads, "household_detail", household)
    args = {"query": {"date_from": "2026-09-22", "date_to": "2026-09-29"}}
    items = json.loads(
        reads.inspect("list_events", args, Mock(), user, session, uuid4())
    )["items"]
    members = json.loads(
        reads.inspect(
            "get_household",
            {"household_id": str(household_id)},
            Mock(),
            user,
            session,
            uuid4(),
        )
    )["members"]
    assert items[0]["assignee_id"] == members[0]["account_id"]
    assert members[0]["display_name"] == "测试成员甲"
    assert "email" not in members[0]
    assert all(principal is user and db is session for _, principal, db in observed)


def test_household_read_resolves_accessible_name_before_detail(monkeypatch):
    household_id = uuid4()
    user, session = SimpleNamespace(id=uuid4()), Mock()
    session.scalars.return_value = [SimpleNamespace(id=household_id, name="四驱车队")]
    seen = []

    def household(identifier, principal, db):
        seen.append((identifier, principal, db))
        return SimpleNamespace(
            model_dump=lambda **_: {"name": "四驱车队", "members": []}
        )

    monkeypatch.setattr(reads, "household_detail", household)
    result = json.loads(
        reads.inspect(
            "get_household",
            {"household_id": "四驱车队"},
            Mock(),
            user,
            session,
            uuid4(),
        )
    )
    assert result == {"name": "四驱车队", "members": [], "complete": True}
    assert seen == [(household_id, user, session)]


def test_household_read_resolves_member_name_within_accessible_home(monkeypatch):
    household_id = uuid4()
    user, session = SimpleNamespace(id=uuid4()), Mock()
    session.scalars.side_effect = [
        [],
        [SimpleNamespace(id=household_id, name="四驱车队")],
    ]
    seen = []

    def household(identifier, principal, db):
        seen.append(identifier)
        return SimpleNamespace(
            model_dump=lambda **_: {
                "name": "四驱车队",
                "members": [{"display_name": "测试成员甲", "account_id": str(uuid4())}],
            }
        )

    monkeypatch.setattr(reads, "household_detail", household)
    result = json.loads(
        reads.inspect(
            "get_household",
            {"household_id": "测试成员甲"},
            Mock(),
            user,
            session,
            uuid4(),
        )
    )
    assert result["members"][0]["display_name"] == "测试成员甲"
    assert seen == [household_id]


def test_household_read_with_unknown_name_has_user_facing_error():
    user, session = SimpleNamespace(id=uuid4()), Mock()
    session.scalars.return_value = []
    with pytest.raises(APIError) as failure:
        reads.inspect(
            "get_household",
            {"household_id": "不存在的家庭"},
            Mock(),
            user,
            session,
            uuid4(),
        )
    assert failure.value.status == 422
    assert "目标不存在" in failure.value.message
    assert "UUID" not in failure.value.message
