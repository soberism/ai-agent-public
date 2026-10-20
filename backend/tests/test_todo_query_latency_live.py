"""真实模型验证常用查询不再重复发现工具，计时仅作样本。"""

import json
import os
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import pytest
from test_assistant_priority_fixes_live import agent  # noqa: F401

from backend.features.assistant import autonomous_model, tool_registry

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_MODEL") != "1", reason="显式启用真实模型"
)


@pytest.mark.parametrize("size", [0, 1])
def test_todo_query_uses_one_discovery_and_verified_results(
    cloud, monkeypatch, request, size
):
    import test_assistant_priority_fixes_live as priority

    from backend.features.assistant import agent_resume

    output = Path(__file__).parent / "results/assistant_todo_latency_2026-10-19.jsonl"
    monkeypatch.setattr(priority, "OUTPUT", output)
    send = request.getfixturevalue("agent")
    if size:
        created = cloud.post(
            "/api/todos",
            json={"title": "延迟回归测试待办"},
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert created.status_code == 201, created.text
    search, decide = tool_registry.search, autonomous_model.decide
    searches, decisions = [], []

    def measured_search(*args, **kwargs):
        result = search(*args, **kwargs)
        searches.append([item["name"] for item in result])
        return result

    def measured_decide(state):
        started = perf_counter()
        result = decide(state)
        decisions.append({"action": result.action, "seconds": perf_counter() - started})
        return result

    monkeypatch.setattr(tool_registry, "search", measured_search)
    monkeypatch.setattr(agent_resume, "decide", measured_decide)
    started = perf_counter()
    result, actions = send("有什么待办")
    elapsed = perf_counter() - started
    with output.open("a") as stream:
        stream.write(
            json.dumps(
                {
                    "timing_sample": True,
                    "items": size,
                    "seconds": elapsed,
                    "decisions": decisions,
                    "search_results": searches,
                }
            )
            + "\n"
        )
    assert result["status"] == "completed" and not actions
    assert f"待办{size}项" in result["final_answer"]
    assert len(searches) <= 1
    if searches:
        assert "list_todos" in searches[0][:5]
    trace = send.traces[-1]
    assert any(row["tool_name"] == "list_todos" for row in trace["observations"])
    assert all(claim["domain"] == "todo" for claim in trace["decision"]["claims"])
