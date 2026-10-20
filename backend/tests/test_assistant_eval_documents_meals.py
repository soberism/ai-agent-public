"""New direct material, folder, meal and daily dump cases in ai_agent_test."""

import os
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_assistant_eval_live import action_tools, cases, isolated_api, replay

from backend.db.parity_models import DailyDump
from backend.db.session import engine

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_MODEL") != "1", reason="显式启用真实模型"
)
DIRECT = {case["target_tool"]: case for case in cases.values() if "target_tool" in case}
TOOLS = [
    "edit_material",
    "delete_material",
    "rename_folder",
    "delete_folder",
    "confirm_meal",
    "add_meal_preference",
    "delete_meal_preference",
    "create_dump",
    "commit_dump",
]


def snapshot(cloud, tool, owner_id):
    if tool.endswith(("material", "folder")):
        return cloud.get("/api/documents/materials").json()
    if "meal" in tool:
        return cloud.get("/api/life/meal-plans").json()["items"]
    with Session(engine) as session:
        return [
            (str(row.id), row.source_text, row.status)
            for row in session.scalars(
                select(DailyDump).where(DailyDump.owner_id == UUID(owner_id))
            )
        ]


@pytest.mark.parametrize("tool", TOOLS)
def test_direct_document_meal_dump(cloud, monkeypatch, tool):
    baseline = None
    owner_id = None

    def before_confirm():
        assert snapshot(cloud, tool, owner_id) == baseline

    api = isolated_api(cloud, monkeypatch, before_confirm=before_confirm)
    owner_id = cloud.get("/api/auth/me").json()["id"]
    if tool.endswith("material"):
        filename = "空调保修凭证.txt" if tool == "edit_material" else "过期服务说明.txt"
        response = cloud.post(
            "/api/documents/materials",
            files={"file": (filename, b"synthetic document 1", "text/plain")},
        )
        assert response.status_code == 201, response.text
        target_id = response.json()["id"]
        if tool == "delete_material":
            assert (
                cloud.post(
                    "/api/documents/materials",
                    files={
                        "file": ("保留资料.txt", b"synthetic document 2", "text/plain")
                    },
                ).status_code
                == 201
            )
    elif tool.endswith("folder"):
        name = "旧收据" if tool == "rename_folder" else "临时文件"
        response = cloud.post("/api/documents/folders", json={"name": name})
        assert response.status_code == 201, response.text
        target_id = response.json()["id"]
        if tool == "delete_folder":
            upload = cloud.post(
                "/api/documents/materials",
                data={"folder_id": target_id},
                files={"file": ("保留材料.txt", b"synthetic material", "text/plain")},
            )
            assert upload.status_code == 201, upload.text
            material_id = upload.json()["id"]
    elif "meal" in tool:
        preferences = (
            [{"label": "少盐", "kind": "preference"}]
            if tool == "delete_meal_preference"
            else []
        )
        response = cloud.post(
            "/api/life/meal-plans",
            json={
                "title": "周日午餐蘑菇烩饭",
                "date": "2026-10-04",
                "meal_type": "lunch",
                "dish": "蘑菇烩饭",
                "diners": 2,
                "preferences": preferences,
            },
        )
        assert response.status_code == 201, response.text
        target_id = response.json()["id"]
    elif tool == "commit_dump":
        response = cloud.post(
            "/api/workflows/daily-dumps", json={"text": "整理阳台花架"}
        )
        assert response.status_code == 201, response.text
        target_id = response.json()["id"]
    baseline = snapshot(cloud, tool, owner_id)
    result = replay(api, DIRECT[tool], 60, True)
    assert all(step["result"] == "review" for step in result["steps"]), result
    assert action_tools(result["steps"][0]["actual"]["run_id"]) == [tool]
    actual = snapshot(cloud, tool, owner_id)
    if tool == "edit_material":
        item = next(item for item in actual["items"] if item["id"] == target_id)
        assert item["name"] == "空调保修单.txt"
    elif tool == "delete_material":
        assert (
            target_id not in {item["id"] for item in actual["items"]}
            and len(actual["items"]) == 1
        )
    elif tool == "rename_folder":
        assert (
            next(item for item in actual["folders"] if item["id"] == target_id)["name"]
            == "票据归档"
        )
    elif tool == "delete_folder":
        assert target_id not in {item["id"] for item in actual["folders"]}
        assert (
            next(item for item in actual["items"] if item["id"] == material_id)[
                "folder_id"
            ]
            is None
        )
    elif tool == "confirm_meal":
        assert next(item for item in actual if item["id"] == target_id)["calendar_url"]
    elif tool == "add_meal_preference":
        assert "少盐" in {item["label"] for item in actual[0]["preferences"]}
    elif tool == "delete_meal_preference":
        assert actual[0]["preferences"] == []
    elif tool == "create_dump":
        assert len(actual) == 1 and "自行车刹车" in actual[0][1]
    elif tool == "commit_dump":
        assert (
            len(actual) == 1
            and actual[0][0] == target_id
            and actual[0][2] == "committed"
        )
        assert any(
            "整理阳台花架" in item["title"]
            for item in cloud.get("/api/todos").json()["items"]
        )
    print(f"{tool}: business result checked")
