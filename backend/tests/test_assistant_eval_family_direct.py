"""New direct family and sharing cases with synthetic multi-account setup."""

import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from helpers import create, login_as, register
from test_assistant_eval_live import action_tools, cases, isolated_api, replay

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_MODEL") != "1", reason="显式启用真实模型"
)
DIRECT = {case["target_tool"]: case for case in cases.values() if "target_tool" in case}
TOOLS = [
    "create_shared_event",
    "create_shared_checklist",
    "edit_member",
    "leave_household",
    "delete_household",
    "decide_invitation",
]


def home_name(tool):
    return {
        "leave_household": "周末协作组",
        "delete_household": "备用家庭组",
        "decide_invitation": "家庭事务组",
    }.get(tool, "测试家庭")


@pytest.mark.parametrize("tool", TOOLS)
def test_family_direct_business_result(cloud, monkeypatch, tool):
    api = isolated_api(cloud, monkeypatch)
    actor = cloud.get("/api/auth/me").json()
    actor_cookie = dict(cloud.cookies)
    if tool in {"leave_household", "decide_invitation"}:
        cloud.cookies.clear()
        register(cloud)
        home = cloud.post("/api/households", json={"name": home_name(tool)})
        assert home.status_code == 201, home.text
        home_id = home.json()["id"]
        invitation = cloud.post(
            f"/api/households/{home_id}/invitations",
            json={"email": actor["email"], "role": "member"},
        )
        assert invitation.status_code == 201, invitation.text
        invite_id = invitation.json()["id"]
        login_as(cloud, actor_cookie)
        if tool == "leave_household":
            assert (
                cloud.post(
                    f"/api/households/invitations/{invite_id}/accept", json={}
                ).status_code
                == 200
            )
    else:
        home = cloud.post("/api/households", json={"name": home_name(tool)})
        assert home.status_code == 201, home.text
        home_id = home.json()["id"]
        if tool == "delete_household":
            personal_id = create(cloud, title="保留个人待办")["id"]
        if tool == "edit_member":
            cloud.cookies.clear()
            member, member_email = register(cloud)
            member_cookie = dict(cloud.cookies)
            assert (
                cloud.patch(
                    "/api/platform/settings", json={"nickname": "小周"}
                ).status_code
                == 200
            )
            login_as(cloud, actor_cookie)
            invitation = cloud.post(
                f"/api/households/{home_id}/invitations",
                json={"email": member_email, "role": "member"},
            )
            assert invitation.status_code == 201
            login_as(cloud, member_cookie)
            assert (
                cloud.post(
                    f"/api/households/invitations/{invitation.json()['id']}/accept",
                    json={},
                ).status_code
                == 200
            )
            login_as(cloud, actor_cookie)
            member_id = member["id"]
    result = replay(api, DIRECT[tool], 60, True)
    assert all(step["result"] == "review" for step in result["steps"]), result
    assert action_tools(result["steps"][0]["actual"]["run_id"]) == [tool]
    if tool == "create_shared_event":
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        calendar = cloud.get(
            "/api/calendar/events",
            params={
                "date_from": today.isoformat(),
                "date_to": (today + timedelta(days=14)).isoformat(),
            },
        )
        assert calendar.status_code == 200
        assert len(calendar.json()["items"]) == 1
    elif tool == "create_shared_checklist":
        rows = cloud.get("/api/planning/checklists").json()["items"]
        assert len(rows) == 1 and home_id in rows[0]["shared_household_ids"]
    elif tool == "edit_member":
        members = cloud.get(f"/api/households/{home_id}").json()["members"]
        assert (
            next(item for item in members if item["account_id"] == member_id)["role"]
            == "admin"
        )
    elif tool == "leave_household":
        assert home_id not in {
            item["id"] for item in cloud.get("/api/households").json()["items"]
        }
    elif tool == "delete_household":
        assert cloud.get(f"/api/households/{home_id}").status_code == 404
        assert cloud.get(f"/api/todos/{personal_id}").status_code == 200
    elif tool == "decide_invitation":
        assert home_id in {
            item["id"] for item in cloud.get("/api/households").json()["items"]
        }
    print(f"{tool}: business result checked")
