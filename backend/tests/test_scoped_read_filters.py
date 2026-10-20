"""真实筛选、范围证据及分页完整性不能互相脱节。"""

import pytest

from backend.features.assistant.answer_claims import AnswerClaim
from backend.features.assistant.autonomous_types import initial_state
from backend.features.assistant.claim_verification import verify
from backend.features.assistant.feature_tools import contract
from backend.features.assistant.read_filters import ReadFilters, filter_result
from backend.features.assistant.tool_registry import describe, search


def test_housework_filter_applies_before_evidence_count():
    filters = {"text": "家务", "status": "ongoing"}
    data = {
        "complete": True,
        "total_count": 3,
        "items": [
            {"id": "a", "title": "家务清洁", "status": "ongoing"},
            {"id": "b", "title": "工作会议准备", "status": "ongoing"},
            {"id": "c", "title": "已完成家务", "status": "completed"},
        ],
    }
    result = filter_result("list_todos", data, filters, "Asia/Shanghai")
    assert result["total_count"] == 1 and result["items"][0]["id"] == "a"
    assert data["total_count"] == 3
    state = initial_state("本周未完成家务")
    state["observations"] = [
        {"tool_name": "list_todos", "arguments": {"filters": filters}, "result": result}
    ]
    claim = AnswerClaim(
        kind="count", domain="todo", scope=filters, value=1, evidence_ids=["read-1"]
    )
    accepted, errors = verify(state, [claim])
    assert not errors and "家务清洁" in accepted[0] and "工作会议" not in accepted[0]
    assert verify(state, [claim.model_copy(update={"scope": {"status": "ongoing"}})])[1]


def test_dates_use_local_day_and_inclusive_bounds():
    filters = {
        "date_field": "created_at",
        "date_from": "2026-10-12",
        "date_to": "2026-10-12",
    }
    result = filter_result(
        "list_voice_memos",
        {
            "complete": True,
            "items": [
                {"id": "a", "created_at": "2026-10-11T16:00:00Z"},
                {"id": "b", "created_at": "2026-10-12T15:59:59Z"},
                {"id": "c", "created_at": "2026-10-12T16:00:00Z"},
                {"id": "d", "created_at": None},
            ],
        },
        filters,
        "Asia/Shanghai",
    )
    assert [r["id"] for r in result["items"]] == ["a", "b"]


def test_exclusion_status_and_partial_lists():
    data = {
        "complete": True,
        "items": [
            {"id": "a", "name": "家电保修资料"},
            {"id": "b", "name": "非保修说明"},
        ],
    }
    assert (
        filter_result(
            "list_materials", data, {"text": "保修", "exclude_text": "非保修"}, "UTC"
        )["total_count"]
        == 1
    )
    data = {
        "complete": False,
        "items": [
            {"id": "a", "status": "scheduled"},
            {"id": "b", "status": "disabled"},
        ],
    }
    result = filter_result("list_reminders", data, {"status": "scheduled"}, "UTC")
    assert result["total_count"] is None and not result["complete"]
    assert [r["id"] for r in result["items"]] == ["a"]


@pytest.mark.parametrize(
    "payload",
    [
        {"date_from": "2026-10-12"},
        {"date_field": "date", "date_from": "2026-10-13", "date_to": "2026-10-12"},
        {"owner_id": "someone"},
        {"text": ""},
    ],
)
def test_invalid_filters_rejected(payload):
    with pytest.raises(ValueError):
        ReadFilters.model_validate(payload)


def test_discovery_explains_domain_boundaries_and_filter_schema():
    assert "私人" in describe("create_event")["description"]
    assert "commit_dump" in describe("convert_memo")["description"]
    assert "delete_memory" in describe("delete_meal_preference")["description"]
    assert "create_shared_event" in {
        t["name"] for t in search("周六全家一起打扫，放到大家的日历里")
    }
    _, model = contract("list_materials")
    assert model.model_validate({"filters": {"text": "保修"}}).filters.text == "保修"


def test_filters_cannot_widen_existing_query_or_invent_date_fields():
    from uuid import uuid4

    from backend.api.routes.assistant_read_steps import inspect
    from backend.core.security import APIError

    with pytest.raises(APIError, match="冲突"):
        inspect(
            "list_todos",
            {"query": {"status": "ongoing"}, "filters": {"status": "completed"}},
            None,
            None,
            None,
            uuid4(),
        )
    with pytest.raises(ValueError, match="日期字段"):
        filter_result(
            "list_pantry",
            {"complete": True, "items": []},
            {"date_field": "created_at", "date_from": "2026-10-12"},
            "UTC",
        )


def test_cloud_shared_event_visible_to_family_but_private_event_is_not(cloud):
    from datetime import UTC, datetime, timedelta
    from uuid import UUID

    from helpers import family_accounts, login_as
    from sqlalchemy.orm import Session

    from backend.api.routes.assistant_features import invoke
    from backend.db.models import User
    from backend.db.session import engine

    owner, cookies, home, _, member_cookies, _, _ = family_accounts(cloud)
    body = {
        "title": "共享清理",
        "start_date": str(datetime.now(UTC).date() + timedelta(days=1)),
        "start_time": "10:00",
        "end_date": str(datetime.now(UTC).date() + timedelta(days=1)),
        "end_time": "11:00",
    }
    login_as(cloud, cookies)
    with Session(engine) as session:
        user = session.get(User, UUID(owner["id"]))
        invoke(
            "create_shared_event",
            {"household_id": home["id"], "body": body},
            user,
            session,
        )
        invoke("create_event", {"body": {**body, "title": "私人清理"}}, user, session)
    login_as(cloud, member_cookies)
    response = cloud.get(
        "/api/calendar/events",
        params={"date_from": body["start_date"], "date_to": body["end_date"]},
    )
    assert response.status_code == 200, response.text
    titles = [row["title"] for row in response.json()["items"]]
    assert "共享清理" in titles and "私人清理" not in titles
