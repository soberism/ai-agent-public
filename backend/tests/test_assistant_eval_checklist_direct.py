"""New direct checklist prompts against isolated real business state."""

import os

import pytest
from test_assistant_eval_live import action_tools, cases, isolated_api, replay

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_MODEL") != "1", reason="显式启用真实模型"
)
DIRECT = {case["target_tool"]: case for case in cases.values() if "target_tool" in case}
SEEDS = {
    "add_checklist_item": ("新家验收", []),
    "delete_checklist_item": ("园艺采购", ["塑料铲", "园艺手套"]),
    "duplicate_checklist": ("亲子野餐", ["餐垫", "水杯"]),
    "pin_checklist": ("搬迁当天", []),
    "bulk_checklist": ("离家检查", ["关窗", "关灯", "锁门"]),
    "rename_checklist": ("露营物资旧版", []),
}


@pytest.mark.parametrize("tool", list(SEEDS))
def test_checklist_direct_business_result(cloud, monkeypatch, tool):
    def checklists():
        response = cloud.get("/api/planning/checklists")
        assert response.status_code == 200
        return response.json()["items"]

    before = []

    def before_confirm():
        assert checklists() == before

    api = isolated_api(cloud, monkeypatch, before_confirm=before_confirm)
    title, items = SEEDS[tool]
    seeded = cloud.post(
        "/api/planning/checklists", json={"title": title, "items": items}
    )
    assert seeded.status_code == 201, seeded.text
    target_id = seeded.json()["id"]
    before = checklists()
    result = replay(api, DIRECT[tool], 60, True)
    assert all(step["result"] == "review" for step in result["steps"]), result
    assert action_tools(result["steps"][0]["actual"]["run_id"]) == [tool]
    after = checklists()
    if tool == "duplicate_checklist":
        assert len(after) == 2
        assert next(item for item in after if item["id"] == target_id) == before[0]
    else:
        assert len(after) == 1
        target = after[0]
        assert target["id"] == target_id
        if tool == "add_checklist_item":
            assert [item["title"] for item in target["items"]] == ["检查门锁"]
        elif tool == "delete_checklist_item":
            assert [item["title"] for item in target["items"]] == ["园艺手套"]
        elif tool == "pin_checklist":
            assert target["pinned"] is True
        elif tool == "bulk_checklist":
            assert target["completed_count"] == 3
        elif tool == "rename_checklist":
            assert target["title"] == "露营物资最新版"
    print(f"{tool}: business result checked")
