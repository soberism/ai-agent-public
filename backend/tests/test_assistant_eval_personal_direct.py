"""New direct personal-data operations with isolated API state checks."""

import os

import pytest
from test_assistant_eval_live import action_tools, cases, isolated_api, replay

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_MODEL") != "1", reason="显式启用真实模型"
)
DIRECT = {case["target_tool"]: case for case in cases.values() if "target_tool" in case}
TOOLS = [
    "edit_memory",
    "delete_memory",
    "delete_pantry",
    "add_preference",
    "delete_preference",
    "set_preferences",
]


def state(cloud, tool):
    if tool.endswith("memory"):
        return cloud.get("/api/assistant/memories").json()
    if tool == "set_preferences":
        return cloud.get("/api/assistant/preferences").json()
    data = cloud.get("/api/life/meal-plans").json()
    return data["pantry" if tool == "delete_pantry" else "preferences"]


@pytest.mark.parametrize("tool", TOOLS)
def test_personal_direct_business_result(cloud, monkeypatch, tool):
    baseline = None

    def before_confirm():
        assert state(cloud, tool) == baseline

    api = isolated_api(cloud, monkeypatch, before_confirm=before_confirm)
    if tool in {"edit_memory", "delete_memory"}:
        content = "晚上处理重要任务" if tool == "edit_memory" else "喜欢蓝色封面"
        response = cloud.post("/api/assistant/memories", json={"content": content})
        assert response.status_code == 201, response.text
        target_id = response.json()["id"]
        if tool == "delete_memory":
            assert (
                cloud.post(
                    "/api/assistant/memories", json={"content": "喜欢绿色封面"}
                ).status_code
                == 201
            )
    elif tool == "delete_pantry":
        response = cloud.post(
            "/api/life/pantry", json={"name": "过期豆浆", "quantity": 1, "unit": "盒"}
        )
        assert response.status_code == 201, response.text
        target_id = response.json()["id"]
        assert (
            cloud.post(
                "/api/life/pantry",
                json={"name": "新鲜牛奶", "quantity": 1, "unit": "瓶"},
            ).status_code
            == 201
        )
    elif tool == "delete_preference":
        response = cloud.post(
            "/api/life/preferences", json={"label": "不吃芹菜", "kind": "preference"}
        )
        assert response.status_code == 201, response.text
        target_id = response.json()["id"]
        assert (
            cloud.post(
                "/api/life/preferences",
                json={"label": "不吃香菇", "kind": "preference"},
            ).status_code
            == 201
        )
    elif tool == "set_preferences":
        assert (
            cloud.patch(
                "/api/assistant/preferences", json={"custom_instructions": "请详细回答"}
            ).status_code
            == 200
        )
    baseline = state(cloud, tool)
    result = replay(api, DIRECT[tool], 60, True)
    assert all(step["result"] == "review" for step in result["steps"]), result
    assert action_tools(result["steps"][0]["actual"]["run_id"]) == [tool]
    actual = state(cloud, tool)
    if tool == "edit_memory":
        assert (
            len(actual) == 1
            and actual[0]["id"] == target_id
            and "早晨" in actual[0]["content"]
        )
    elif tool in {"delete_memory", "delete_pantry", "delete_preference"}:
        assert target_id not in {item["id"] for item in actual}
        assert len(actual) == len(baseline) - 1
    elif tool == "add_preference":
        assert len(actual) == 1 and "香菜" in actual[0]["label"]
    elif tool == "set_preferences":
        assert "简短" in actual["custom_instructions"]
    print(f"{tool}: business result checked")
