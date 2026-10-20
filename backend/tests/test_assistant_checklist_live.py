"""显式启用后，在隔离测试库回放完整清单读取。"""

import os

import pytest
from helpers import register

from backend.api.routes import agent_runs
from backend.features.assistant.agent_tasks import execute_run

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_MODEL") != "1", reason="显式 RUN_LIVE_MODEL=1 才调用真实模型"
)


def test_live_model_lists_all_35_checklist_items(cloud, monkeypatch):
    register(cloud)
    titles = [f"旅行物品{index:02d}" for index in range(1, 36)]
    created = cloud.post(
        "/api/planning/checklists", json={"title": "旅行准备", "items": titles}
    )
    assert created.status_code == 201, created.text
    assert created.json()["total_count"] == 35
    thread = cloud.post("/api/assistant/threads", json={}).json()["thread_id"]
    monkeypatch.setattr(agent_runs.run_task, "delay", execute_run)

    run = cloud.post(
        "/api/agent/runs",
        json={"thread_id": thread, "prompt": "把旅行准备清单内容全部列出来"},
    )
    assert run.status_code == 202, run.text
    data = cloud.get(f"/api/agent/runs/{run.json()['id']}").json()
    assert data["status"] == "completed", data
    answer = data["final_answer"]
    assert "35" in answer
    assert all(title in answer for title in titles), answer
