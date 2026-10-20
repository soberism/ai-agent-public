"""New direct shopping, reminder and voice memo tests in the isolated database."""

import os

import pytest
from helpers import create
from test_assistant_eval_live import action_tools, cases, isolated_api, replay

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_MODEL") != "1", reason="显式启用真实模型"
)
DIRECT = {case["target_tool"]: case for case in cases.values() if "target_tool" in case}
TOOLS = [
    "confirm_shopping",
    "delete_shopping",
    "edit_reminder",
    "delete_reminder",
    "create_voice_memo",
    "convert_memo",
    "delete_memo",
]


def state(cloud, tool):
    if "shopping" in tool:
        return cloud.get("/api/life/shopping-lists/overview").json()["items"]
    if "reminder" in tool:
        return cloud.get("/api/planning/reminders").json()
    return cloud.get("/api/assistant/voice-memos").json()


@pytest.mark.parametrize("tool", TOOLS)
def test_life_direct_business_result(cloud, monkeypatch, tool):
    before = None

    def before_confirm():
        assert state(cloud, tool) == before

    api = isolated_api(cloud, monkeypatch, before_confirm=before_confirm)
    if "shopping" in tool:
        title = "节日食材" if tool == "confirm_shopping" else "过季采购"
        response = cloud.post("/api/life/shopping-lists", json={"title": title})
        assert response.status_code == 201, response.text
        target_id = response.json()["id"]
        if tool == "confirm_shopping":
            item = cloud.post(
                f"/api/life/shopping-lists/{target_id}/items",
                json={"name": "玉米", "quantity": 2, "unit": "根"},
            )
            assert item.status_code == 201, item.text
        if tool == "delete_shopping":
            assert (
                cloud.post(
                    "/api/life/shopping-lists", json={"title": "日常补货"}
                ).status_code
                == 201
            )
    elif "reminder" in tool:
        title = "每周清洗水壶" if tool == "edit_reminder" else "更换窗帘"
        todo = create(cloud, title=title)
        response = cloud.post(
            "/api/planning/reminders",
            json={
                "todo_id": todo["id"],
                "remind_date": "2026-10-05",
                "remind_time": "08:00",
            },
        )
        assert response.status_code == 201, response.text
        target_id = response.json()["id"]
    elif tool != "create_voice_memo":
        title = "检查车胎气压" if tool == "convert_memo" else "旧会议录音"
        response = cloud.post("/api/assistant/voice-memos", json={"transcript": title})
        assert response.status_code == 201, response.text
        target_id = response.json()["id"]
        if tool == "delete_memo":
            assert (
                cloud.post(
                    "/api/assistant/voice-memos", json={"transcript": "另一个备忘"}
                ).status_code
                == 201
            )
    before = state(cloud, tool)
    result = replay(api, DIRECT[tool], 60, True)
    assert all(step["result"] == "review" for step in result["steps"]), result
    assert action_tools(result["steps"][0]["actual"]["run_id"]) == [tool]
    after = state(cloud, tool)
    if tool == "confirm_shopping":
        assert (
            len(after) == 1
            and after[0]["id"] == target_id
            and after[0]["status"] != "draft"
        )
    elif tool == "delete_shopping":
        assert target_id not in {item["id"] for item in after} and len(after) == 1
    elif tool == "edit_reminder":
        assert (
            len(after) == 1
            and after[0]["id"] == target_id
            and after[0]["status"] == "disabled"
        )
    elif tool == "delete_reminder":
        assert after == []
    elif tool == "create_voice_memo":
        assert len(after) == 1 and "办公室窗户" in after[0]["transcript"]
    elif tool == "convert_memo":
        assert after[0]["id"] == target_id and after[0]["status"] == "converted"
        assert any(
            "车胎气压" in todo["title"]
            for todo in cloud.get("/api/todos").json()["items"]
        )
    elif tool == "delete_memo":
        assert target_id not in {item["id"] for item in after} and len(after) == 1
    print(f"{tool}: business result checked")
