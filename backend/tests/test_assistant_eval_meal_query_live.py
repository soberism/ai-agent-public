"""复测用户反馈的餐食列表查询，保存真实模型和读取证据。"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from helpers import register

from backend.api.routes import agent_runs
from backend.features.assistant import agent_tasks, autonomous_model
from backend.features.assistant.claim_verification import verify

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_MODEL") != "1", reason="显式启用真实模型"
)


@pytest.mark.parametrize("populated", [False, True])
def test_meal_query_report(cloud, monkeypatch, populated):
    register(cloud)
    monkeypatch.setattr(agent_runs.run_task, "delay", agent_tasks.execute_run)
    original = agent_tasks.run_graph
    traces = []
    decisions = []
    original_guard = autonomous_model.guard_decision

    def traced_guard(state, decision):
        guarded = original_guard(state, decision)
        decisions.append(
            {
                "model_decision": decision.model_dump(mode="json"),
                "verification": verify(state, decision.claims),
                "guarded_decision": guarded.model_dump(mode="json"),
            }
        )
        return guarded

    monkeypatch.setattr(autonomous_model, "guard_decision", traced_guard)

    def traced(*args, **kwargs):
        result = original(*args, **kwargs)
        traces.append(
            {
                key: result.get(key)
                for key in (
                    "observations",
                    "decision",
                    "final_answer",
                    "answer_claims",
                    "answer_kind",
                    "error",
                    "requested_domains",
                )
            }
        )
        return result

    monkeypatch.setattr(agent_tasks, "run_graph", traced)
    if populated:
        response = cloud.post(
            "/api/life/meal-plans",
            json={
                "title": "测试晚餐番茄牛腩",
                "date": datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat(),
                "meal_type": "dinner",
                "dish": "番茄牛腩",
                "diners": 4,
            },
        )
        assert response.status_code == 201, response.text
    baseline = cloud.get("/api/life/meal-plans").json()
    thread = cloud.post("/api/assistant/threads", json={"fresh": True}).json()
    started = time.monotonic()
    response = cloud.post(
        "/api/agent/runs",
        json={
            "thread_id": thread["thread_id"],
            "prompt": "餐食计划有啥",
        },
    )
    assert response.status_code < 400, response.text
    run = response.json()
    run = cloud.get(f"/api/agent/runs/{run['id']}").json()
    record = {
        "id": "SUP-MEAL-POPULATED" if populated else "SUP-MEAL-EMPTY",
        "prompt": "餐食计划有啥",
        "baseline": baseline,
        "run": run,
        "trace": traces,
        "decisions": decisions,
        "latency_ms": round((time.monotonic() - started) * 1000),
    }
    tag = os.getenv("ASSISTANT_EVAL_RESULT_TAG", "2026-10-16")
    output = Path(__file__).parent / "results" / (record["id"] + "_" + tag + ".json")
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2, default=str))
    assert cloud.get("/api/life/meal-plans").json() == baseline
    assert run["status"] == "completed", run
    answer = run.get("final_answer") or ""
    assert "当前证据尚不足" not in answer, answer
    if populated:
        assert all(word in answer for word in ("番茄牛腩", "晚餐", "4人")), answer
    else:
        assert any(
            word in answer for word in ("没有", "暂无", "还没", "0条", "0 条", "0项")
        ), answer
