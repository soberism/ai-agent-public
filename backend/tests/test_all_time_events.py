"""不限日期日程的范围、完整性和权限边界。"""

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from helpers import family_accounts, register
from sqlalchemy.orm import Session

from backend.api.calendar_schemas import EventQuery
from backend.api.routes.assistant_read_steps import inspect
from backend.api.routes.sharing import SharingSettings, save_settings
from backend.core.security import APIError
from backend.db.models import CalendarEvent, User
from backend.db.session import engine
from backend.features.assistant.answer_claims import AnswerClaim
from backend.features.assistant.autonomous_types import initial_state
from backend.features.assistant.claim_verification import verify
from backend.features.assistant.feature_tools import contract
from backend.features.assistant.tool_registry import search


def event(owner_id, title, year):
    start = datetime(year, 5, 1, 1, tzinfo=UTC)
    return CalendarEvent(
        owner_id=UUID(owner_id),
        title=title,
        starts_at=start,
        ends_at=start + timedelta(hours=1),
        timezone="Asia/Shanghai",
        source="app",
        status="scheduled",
    )


def test_all_time_count_cannot_use_monthly_evidence_or_scope():
    state = initial_state("全部时间日程呢")
    state["observations"] = [
        {
            "tool_name": "list_all_events",
            "arguments": {},
            "result": {
                "items": [{"id": "one", "title": "旧日程", "start_date": "1990-05-01"}],
                "total_count": 1,
                "complete": True,
            },
        }
    ]
    claim = AnswerClaim(
        kind="count",
        domain="event",
        scope={"range": "all"},
        value=1,
        evidence_ids=["read-1"],
    )
    result, errors = verify(state, [claim])
    assert not errors and "全部时间" in result[0] and "旧日程" in result[0]
    assert verify(state, [claim.model_copy(update={"scope": {}})])[1]
    state["observations"][0]["tool_name"] = "list_events"
    state["observations"][0]["arguments"] = {
        "query": {"date_from": "2026-10-01", "date_to": "2026-10-31"}
    }
    assert verify(state, [claim])[1]


def test_all_time_discovery_and_existing_date_contract_remain_separate():
    assert "list_all_events" in {row["name"] for row in search("全部时间日程")}
    _, model = contract("list_all_events")
    assert model.model_validate({}).model_dump() == {}
    with pytest.raises(ValueError):
        model.model_validate({"query": {"date_from": "1990-01-01"}})
    with pytest.raises(ValueError):
        EventQuery.model_validate({})
    with pytest.raises(ValueError):
        EventQuery.model_validate({"date_from": "1990-01-01", "date_to": "2035-01-01"})


@pytest.mark.parametrize("size", [0, 50, 51])
def test_cloud_all_time_limits_are_complete_or_explicitly_rejected(cloud, size):
    user, _ = register(cloud)
    with Session(engine) as db:
        db.add_all([event(user["id"], f"日程{i}", 1990 + i) for i in range(size)])
        db.commit()
        principal = db.get(User, UUID(user["id"]))
        if size > 50:
            with pytest.raises(APIError) as error:
                inspect("list_all_events", {}, None, principal, db, uuid4())
            assert error.value.code == "TOO_MANY_EVENTS"
        else:
            data = json.loads(
                inspect("list_all_events", {}, None, principal, db, uuid4())
            )
            assert data["complete"] and data["total_count"] == size
            assert len(data["items"]) == size


def test_cloud_all_time_includes_shared_events_but_not_others_private(cloud):
    owner, _, home, member, _, _, _ = family_accounts(cloud)
    with Session(engine) as db:
        private = event(owner["id"], "私人旧日程", 1990)
        shared = event(owner["id"], "家庭未来日程", 2035)
        own = event(member["id"], "成员私有日程", 2026)
        db.add_all([private, shared, own])
        db.flush()
        save_settings(
            db,
            "event",
            shared.id,
            SharingSettings(scope="household", household_id=UUID(home["id"])),
        )
        db.commit()
        principal = db.get(User, UUID(member["id"]))
        data = json.loads(inspect("list_all_events", {}, None, principal, db, uuid4()))
        assert {row["title"] for row in data["items"]} == {
            "家庭未来日程",
            "成员私有日程",
        }
        principal = db.get(User, UUID(owner["id"]))
        data = json.loads(inspect("list_all_events", {}, None, principal, db, uuid4()))
        assert {row["title"] for row in data["items"]} == {"家庭未来日程", "私人旧日程"}


def test_all_time_overflow_finishes_with_clear_scope_request():
    from types import SimpleNamespace

    from backend.features.assistant.autonomous_types import AutonomousContext, Decision
    from backend.features.assistant.autonomous_workflow import read

    def reader(*_):
        raise APIError(
            422,
            "TOO_MANY_EVENTS",
            "全部时间日程超过50条，请指定日期范围查询，当前未返回完整列表",
        )

    state = initial_state("全部时间日程")
    state["decision"] = Decision(
        action="read_api", tool_name="list_all_events"
    ).model_dump()
    runtime = SimpleNamespace(context=AutonomousContext(lambda _: None, reader))
    result = read(state, runtime)
    assert result["decision"]["action"] == "final_answer"
    assert (
        "超过50条" in result["final_answer"]
        and "未返回完整列表" in result["final_answer"]
    )
