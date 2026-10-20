"""Direct-tool cases use fresh accounts and the isolated cloud test database."""

import os

import pytest
from helpers import create, login_as, register
from test_assistant_eval_live import action_tools, cases, isolated_api, replay

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_MODEL") != "1",
    reason="显式 RUN_LIVE_MODEL=1 才调用真实模型",
)

DIRECT = {case["target_tool"]: case for case in cases.values() if "target_tool" in case}


@pytest.mark.parametrize(
    "tool",
    [
        "get_todo",
        "get_event",
        "get_meal",
        "list_memories",
        "list_reminders",
        "get_preferences",
        "get_sharing",
        "incoming_invitations",
        "set_settings",
    ],
)
def test_direct_tools_with_business_evidence(cloud, monkeypatch, tool):
    reads = []
    before_confirm = None
    if tool == "set_settings":

        def before_confirm():
            assert cloud.get("/api/platform/settings").json()["nickname"] != "测试小岚"

    api = isolated_api(
        cloud, monkeypatch, before_confirm=before_confirm, read_tools=reads
    )
    if tool == "get_todo":
        created = create(cloud, title="更换净水滤芯", description="厨房水槽下方")
        expected_id = created["id"]
    elif tool == "get_event":
        response = cloud.post(
            "/api/calendar/events",
            json={
                "title": "阳台植物养护",
                "location": "阳台",
                "start_date": "2026-10-03",
                "start_time": "10:00",
                "end_date": "2026-10-03",
                "end_time": "11:00",
            },
        )
        assert response.status_code == 201, response.text
        expected_id = response.json()["id"]
    elif tool == "list_memories":
        for content in ("喜欢早晨跑步", "喜欢看植物养护资料"):
            response = cloud.post("/api/assistant/memories", json={"content": content})
            assert response.status_code == 201, response.text
    elif tool == "get_meal":
        response = cloud.post(
            "/api/life/meal-plans",
            json={
                "title": "周四晚餐南瓜汤",
                "date": "2026-10-01",
                "meal_type": "dinner",
                "dish": "南瓜汤",
                "diners": 2,
            },
        )
        assert response.status_code == 201, response.text
        expected_id = response.json()["id"]
    elif tool == "list_reminders":
        todo = create(cloud, title="保养咖啡机")
        response = cloud.post(
            "/api/planning/reminders",
            json={
                "todo_id": todo["id"],
                "remind_date": "2026-10-02",
                "remind_time": "08:00",
            },
        )
        assert response.status_code == 201, response.text
    elif tool == "get_sharing":
        response = cloud.post(
            "/api/planning/checklists", json={"title": "露台养护", "items": ["浇水"]}
        )
        assert response.status_code == 201, response.text
        expected_id = response.json()["id"]
    elif tool == "incoming_invitations":
        invitee = cloud.get("/api/auth/me").json()
        invitee_cookie = dict(cloud.cookies)
        cloud.cookies.clear()
        register(cloud)
        home = cloud.post("/api/households", json={"name": "家庭事务组"})
        assert home.status_code == 201, home.text
        invitation = cloud.post(
            f"/api/households/{home.json()['id']}/invitations",
            json={"email": invitee["email"], "role": "member"},
        )
        assert invitation.status_code == 201, invitation.text
        login_as(cloud, invitee_cookie)
        assert cloud.get("/api/auth/me").status_code == 200
    elif tool == "get_preferences":
        response = cloud.patch(
            "/api/assistant/preferences",
            json={"custom_instructions": "回答先说结论"},
        )
        assert response.status_code == 200, response.text
    result = replay(api, DIRECT[tool], 60, True)
    assert all(step["result"] == "review" for step in result["steps"]), result
    if tool == "set_settings":
        assert action_tools(result["steps"][0]["actual"]["run_id"]) == [tool]
        assert cloud.get("/api/platform/settings").json()["nickname"] == "测试小岚"
    else:
        assert tool in reads, (tool, reads, result)
        answer = result["steps"][0]["actual"]["answer"] or ""
        if tool == "get_todo":
            assert cloud.get(f"/api/todos/{expected_id}").status_code == 200
            assert "更换净水滤芯" in answer
        elif tool == "get_event":
            assert cloud.get(f"/api/calendar/events/{expected_id}").status_code == 200
            assert "阳台植物养护" in answer
        elif tool == "list_memories":
            assert len(cloud.get("/api/assistant/memories").json()) == 2
            assert "早晨跑步" in answer
        elif tool == "get_meal":
            assert cloud.get(f"/api/life/meal-plans/{expected_id}").status_code == 200
            assert "南瓜汤" in answer
        elif tool == "list_reminders":
            assert len(cloud.get("/api/planning/reminders").json()) == 1
        elif tool == "get_sharing":
            assert cloud.get(f"/api/sharing/checklist/{expected_id}").status_code == 200
        elif tool == "incoming_invitations":
            assert len(cloud.get("/api/households/invitations/incoming").json()) == 1
        elif tool == "get_preferences":
            assert "回答先说结论" in answer
    print(f"{tool}: reviewed")
