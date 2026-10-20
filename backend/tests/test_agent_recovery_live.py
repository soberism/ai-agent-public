"""Explicit live-model replay of a correction about a deleted checklist."""

import os

import pytest
from helpers import register
from sqlalchemy.orm import Session

from backend.api.routes import agent_runs
from backend.db.models import AssistantMessage
from backend.db.session import engine
from backend.features.assistant.agent_tasks import execute_run

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_MODEL") != "1", reason="显式 RUN_LIVE_MODEL=1 才调用真实模型"
)


def test_live_model_handles_corrected_deleted_checklist(cloud, monkeypatch):
    register(cloud)
    created = cloud.post(
        "/api/planning/checklists",
        json={"title": "同学录", "items": ["刘", "洲", "网"]},
    )
    assert created.status_code == 201, created.text
    assert (
        cloud.delete(f"/api/planning/checklists/{created.json()['id']}").status_code
        == 204
    )
    thread_id = cloud.post("/api/assistant/threads", json={}).json()["thread_id"]
    with Session(engine) as session:
        session.add(
            AssistantMessage(
                thread_id=thread_id,
                role="assistant",
                content="之前删除的是旅行准备清单中的钱和一次性袜子。",
                kind="message",
            )
        )
        session.commit()
    monkeypatch.setattr(agent_runs.run_task, "delay", execute_run)

    run = cloud.post(
        "/api/agent/runs",
        json={
            "thread_id": thread_id,
            "prompt": "我是说刚才好像把同学录误删除了，能恢复吗？",
        },
    )
    assert run.status_code == 202, run.text
    result = cloud.get(f"/api/agent/runs/{run.json()['id']}").json()
    assert result["status"] == "completed", result
    assert "未知工具" not in result["final_answer"]
    assert "同学录" in result["final_answer"]
    assert "旅行准备" not in result["final_answer"]
    assert not result["actions"]
