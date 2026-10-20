"""家庭成员名单的证据与截图多轮回归。"""

import os
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_assistant_priority_fixes_live import agent  # noqa: F401

from backend.db.household_models import HouseholdParticipant
from backend.db.session import engine
from backend.features.assistant.answer_claims import AnswerClaim
from backend.features.assistant.autonomous_types import initial_state
from backend.features.assistant.claim_verification import verify
from backend.features.assistant.tool_registry import search


def state_for(members):
    state = initial_state("具体成员列出来")
    state["observations"] = [
        {
            "tool_name": "get_household",
            "arguments": {"household_id": "home"},
            "result": {
                "id": "home",
                "name": "测试家庭",
                "complete": True,
                "members": members,
            },
        }
    ]
    return state


def claim(size):
    return AnswerClaim(
        kind="count",
        domain="household_member",
        scope={"household_id": "home"},
        value=size,
        evidence_ids=["read-1"],
    )


def test_member_count_publishes_names_and_roles():
    state = state_for(
        [
            {"id": "m1", "display_name": "小林", "role": "owner"},
            {"id": "m2", "display_name": "阿青", "role": "member"},
        ]
    )
    accepted, errors = verify(state, [claim(2)])
    assert not errors and "小林" in accepted[0] and "阿青" in accepted[0]
    assert "所有者" in accepted[0] and "家庭成员2项" in accepted[0]
    assert verify(
        state, [claim(2).model_copy(update={"scope": {"household_id": "other"}})]
    )[1]
    assert verify(state, [claim(2).model_copy(update={"domain": "household"})])[1]
    field = AnswerClaim(
        kind="field",
        domain="household",
        scope={"household_id": "home"},
        path="/members/0/display_name",
        subject_id="m1",
        value="小林",
        evidence_ids=["read-1"],
    )
    assert not verify(state, [field])[1]
    assert verify(state, [field.model_copy(update={"subject_id": "home"})])[1]


@pytest.mark.parametrize("members", [[], [{"id": "m", "display_name": "小林"}]])
def test_member_lists_require_complete_evidence(members):
    state = state_for(members)
    assert not verify(state, [claim(len(members))])[1]
    state["observations"][0]["result"]["complete"] = False
    assert verify(state, [claim(len(members))])[1]


def test_summary_and_duplicate_members_cannot_prove_member_list():
    state = state_for([{"id": "same"}, {"id": "same"}])
    assert verify(state, [claim(2)])[1]
    state["observations"][0] = {
        "tool_name": "list_households",
        "arguments": {},
        "result": {
            "complete": True,
            "items": [{"id": "home", "member_count": 3}],
            "total_count": 1,
        },
    }
    assert verify(state, [claim(3).model_copy(update={"scope": {}})])[1]
    assert "get_household" in {x["name"] for x in search("具体成员列出来")}


@pytest.mark.skipif(os.getenv("RUN_LIVE_MODEL") != "1", reason="显式启用真实模型")
def test_household_members_followups(cloud, monkeypatch, request):
    import test_assistant_priority_fixes_live as priority
    from helpers import login_as, register

    monkeypatch.setattr(
        priority,
        "OUTPUT",
        Path(__file__).parent / "results/assistant_household_members_2026-10-16.jsonl",
    )
    send = request.getfixturevalue("agent")
    cookies = dict(cloud.cookies)
    home = cloud.post("/api/households", json={"name": "测试家庭"}).json()
    members = []
    for _ in range(2):
        cloud.cookies.clear()
        members.append(register(cloud)[0])
    login_as(cloud, cookies)
    with Session(engine) as db:
        owner = db.scalar(
            select(HouseholdParticipant).where(
                HouseholdParticipant.household_id == UUID(home["id"])
            )
        )
        owner.display_name = "小林"
        for user, name in zip(members, ["阿青", "小周"], strict=True):
            db.add(
                HouseholdParticipant(
                    household_id=UUID(home["id"]),
                    account_id=UUID(user["id"]),
                    email=f"{user['id']}@integration.example.com",
                    display_name=name,
                    role="member",
                    status="active",
                    permissions=[],
                    invited_by=owner.account_id,
                )
            )
        db.commit()
    first, _ = send("我现在有几个家庭")
    assert first["status"] == "completed" and "家庭1项" in first["final_answer"]
    for prompt in ["成员都有谁", "具体成员列出来"]:
        run, tools = send(prompt)
        assert run["status"] == "completed" and not tools, run
        assert all(name in run["final_answer"] for name in ["小林", "阿青", "小周"]), (
            run
        )
        assert "家庭成员3项" in run["final_answer"]
        reads = send.traces[-1]["observations"]
        assert any(row["tool_name"] == "get_household" for row in reads)
        assert all("email" not in str(row["result"]) for row in reads)


def test_cloud_household_member_read_rejects_outsider(cloud):
    from uuid import uuid4

    from helpers import register

    from backend.api.routes.assistant_read_steps import inspect
    from backend.core.security import APIError
    from backend.db.models import User

    register(cloud)
    home = cloud.post("/api/households", json={"name": "隔离家庭"}).json()
    cloud.cookies.clear()
    other, _ = register(cloud)
    with Session(engine) as db:
        user = db.get(User, UUID(other["id"]))
        with pytest.raises(APIError) as error:
            inspect(
                "get_household", {"household_id": home["id"]}, None, user, db, uuid4()
            )
        assert error.value.status == 422
        assert error.value.code == "AMBIGUOUS_TARGET"
