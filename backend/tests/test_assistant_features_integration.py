"""Run only against ai_agent_test and an isolated cloud Redis namespace."""

from helpers import register

from backend.api.routes import assistant
from backend.features.assistant.graph import Intent


def test_feature_confirmation_and_business_pages(cloud, monkeypatch):
    register(cloud)
    state = {"name": "list_checklists", "payload": {}}
    monkeypatch.setattr(
        assistant,
        "interpret",
        lambda *_: Intent(
            action="feature", feature=state["name"], payload=state["payload"]
        ),
    )
    thread = cloud.post("/api/assistant/threads", json={}).json()["thread_id"]

    def send(name, payload):
        state.update(name=name, payload=payload)
        response = cloud.post(
            "/api/assistant/messages", json={"thread_id": thread, "message": name}
        )
        assert response.status_code == 200, response.text
        return response.json()

    def execute(name, payload):
        draft = send(name, payload)
        assert draft["kind"] == "confirm", draft
        token = draft["action_token"]
        result = cloud.post(f"/api/assistant/actions/{token}/confirm", json={})
        assert result.status_code == 200, result.text
        assert result.json()["kind"] == "success"
        assert (
            cloud.post(f"/api/assistant/actions/{token}/confirm", json={}).status_code
            == 404
        )
        return result.json()

    checklist = cloud.post(
        "/api/planning/checklists", json={"title": "旅行准备"}
    ).json()
    draft = send(
        "add_checklist_item", {"checklist_id": "旅行准备", "body": {"title": "护照"}}
    )
    assert (
        cloud.get(f"/api/planning/checklists/{checklist['id']}").json()["total_count"]
        == 0
    )
    assert (
        cloud.post(
            f"/api/assistant/actions/{draft['action_token']}/confirm", json={}
        ).status_code
        == 200
    )
    execute(
        "check_item",
        {"checklist_id": "旅行准备", "item_id": "护照", "body": {"completed": True}},
    )
    assert (
        cloud.get(f"/api/planning/checklists/{checklist['id']}").json()[
            "completed_count"
        ]
        == 1
    )
    assert (
        send("get_checklist", {"checklist_id": "旅行准备"})["items"][0]["id"]
        == checklist["id"]
    )

    result = execute(
        "create_meal",
        {
            "body": {
                "schedule_text": "明日晚餐",
                "dish": "番茄炒蛋",
                "date": "2026-09-19",
                "meal_type": "dinner",
                "diners": 2,
            }
        },
    )
    meal_id = result["items"][0]["id"]
    assert cloud.get(f"/api/life/meal-plans/{meal_id}").json()["dish"] == "番茄炒蛋"
    execute("edit_meal", {"meal_id": "明日晚餐", "body": {"notes": "少放盐"}})
    edited = cloud.get(f"/api/life/meal-plans/{meal_id}").json()
    assert edited["date"] == "2026-09-19" and edited["diners"] == 2
    assert edited["notes"] == "少放盐"
    execute("confirm_meal", {"meal_id": "明日晚餐"})
    assert cloud.get(f"/api/life/meal-plans/{meal_id}").json()["calendar_url"]
    execute("add_pantry", {"body": {"name": "鸡蛋", "quantity": 6, "unit": "个"}})
    reply = send("list_meals", {})
    assert "鸡蛋" in reply["message"]
    assert "番茄炒蛋" in reply["message"]

    execute("create_folder", {"body": {"name": "旅行资料"}})
    upload = cloud.post(
        "/api/documents/materials",
        files={"file": ("示例.txt", b"example", "text/plain")},
    )
    assert upload.status_code == 201
    material_id = upload.json()["id"]
    folder_id = cloud.get("/api/documents/materials").json()["folders"][0]["id"]
    execute(
        "edit_material",
        {
            "material_id": "示例.txt",
            "body": {"folder_id": folder_id, "name": "出行资料.txt"},
        },
    )
    materials = cloud.get("/api/documents/materials").json()["items"]
    assert materials[0]["folder_id"] == folder_id
    assert materials[0]["name"] == "出行资料.txt"
    assert send("list_materials", {})["items"][0]["id"] == material_id

    execute("create_voice_memo", {"body": {"transcript": "检查护照有效期"}})
    memos = cloud.get("/api/assistant/voice-memos").json()
    execute(
        "convert_memo",
        {
            "memo_id": memos[0]["id"],
            "body": {"target_type": "todo", "title": "检查护照"},
        },
    )
    assert cloud.get("/api/assistant/voice-memos").json()[0]["status"] == "converted"
    assert (
        send(
            "review_plan",
            {"query": {"date_from": "2026-09-18", "date_to": "2026-09-20"}},
        )["kind"]
        == "result"
    )
    execute("create_dump", {"body": {"text": "收拾行李"}})
    execute(
        "commit_dump",
        {
            "dump_id": "收拾行李",
            "body": {"candidates": [{"title": "收拾行李", "selected": True}]},
        },
    )

    home = execute("create_household", {"body": {"name": "测试家庭"}})["items"][0]
    assert send("get_household", {"household_id": home["id"]})["kind"] == "result"
    execute(
        "set_sharing",
        {
            "kind": "checklist",
            "resource_id": "旅行准备",
            "body": {"scope": "household", "household_id": home["id"]},
        },
    )
    assert (
        cloud.get(f"/api/sharing/checklist/{checklist['id']}").json()["scope"]
        == "household"
    )


def test_confirmation_rechecks_target_access_and_cannot_cross_account(
    cloud, monkeypatch
):
    from fastapi.testclient import TestClient
    from helpers import HEADERS

    from backend.app import app

    register(cloud)
    checklist = cloud.post("/api/planning/checklists", json={"title": "仅自己"}).json()
    monkeypatch.setattr(
        assistant,
        "interpret",
        lambda *_: Intent(
            action="feature",
            feature="add_checklist_item",
            payload={"checklist_id": checklist["id"], "body": {"title": "项目"}},
        ),
    )
    thread = cloud.post("/api/assistant/threads", json={}).json()["thread_id"]
    draft = cloud.post(
        "/api/assistant/messages", json={"thread_id": thread, "message": "添加项目"}
    ).json()
    assert draft["kind"] == "confirm"
    with TestClient(app, headers=HEADERS) as other:
        register(other)
        assert (
            other.post(
                f"/api/assistant/actions/{draft['action_token']}/confirm", json={}
            ).status_code
            == 404
        )
    assert (
        cloud.delete(f"/api/planning/checklists/{checklist['id']}").status_code == 204
    )
    assert (
        cloud.post(
            f"/api/assistant/actions/{draft['action_token']}/confirm", json={}
        ).status_code
        == 404
    )


def test_real_model_can_edit_recent_todo(cloud):
    import os

    import pytest
    from helpers import create

    if os.environ.get("RUN_LLM_INTEGRATION") != "1":
        pytest.skip("真实模型需显式 RUN_LLM_INTEGRATION=1")
    register(cloud)
    todo = create(
        cloud,
        title="检查护照",
        due_date="2026-09-19",
        due_time="18:00",
        description="原说明",
    )
    thread = cloud.post("/api/assistant/threads", json={}).json()["thread_id"]
    query = cloud.post(
        "/api/assistant/messages",
        json={"thread_id": thread, "message": "查看我所有进行中的待办"},
    )
    assert query.status_code == 200, query.text
    assert query.json()["items"][0]["id"] == todo["id"]
    draft = cloud.post(
        "/api/assistant/messages",
        json={
            "thread_id": thread,
            "message": "把刚才那条检查护照的待办改到明天19:00，保留原说明",
        },
    )
    assert draft.status_code == 200, draft.text
    assert draft.json()["kind"] == "confirm", draft.json()
    assert "检查护照" in draft.json()["message"]
    assert "19:00" in draft.json()["message"]
    token = draft.json()["action_token"]
    result = cloud.post(f"/api/assistant/actions/{token}/confirm", json={})
    assert result.status_code == 200, result.text
    row = cloud.get(f"/api/todos/{todo['id']}").json()
    assert row["due_time"] == "19:00"
    assert row["description"] == "原说明"
