"""每条独立准备、完整真实模型回放、业务前后状态与内部轨迹采集。"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from runpy import run_path
from uuid import UUID

import pytest
from eval_seed_setup import current_state, prepare
from eval_seed_sql import observer
from eval_seed_state import cleanup_sharing, delta
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from backend.api.routes import agent_runs
from backend.db.agent_models import AgentAction
from backend.db.session import engine
from backend.features.assistant import agent_tasks

CASES = list(
    run_path(str(Path(__file__).parents[1] / "infra/assistant_eval.py"))[
        "load_cases"
    ]().values()
)
OFFSET = int(os.getenv("ASSISTANT_EVAL_OFFSET", "0"))
LIMIT = int(os.getenv("ASSISTANT_EVAL_MAX_CASES", "576"))
IDS = os.getenv("ASSISTANT_EVAL_IDS", "").split(",")
SELECTED = (
    [case for case in CASES if case["id"] in IDS]
    if IDS != [""]
    else CASES[OFFSET : OFFSET + LIMIT]
)
OUTPUT = Path(
    os.getenv(
        "ASSISTANT_EVAL_OUTPUT",
        str(Path(__file__).parent / "results/assistant_eval_seeded_2026-10-16.jsonl"),
    )
)


def actions(run):
    with Session(engine) as db:
        return [
            {
                "id": str(row.id),
                "tool_name": row.tool_name,
                "arguments": row.arguments,
                "status": row.status,
                "result": row.result,
                "error": row.error,
            }
            for row in db.scalars(
                select(AgentAction)
                .where(AgentAction.run_id == UUID(run["id"]))
                .order_by(AgentAction.position)
            )
        ]


@pytest.mark.skipif(
    os.getenv("RUN_SEEDED_ASSISTANT_EVAL") != "1", reason="显式启用576条隔离回放"
)
@pytest.mark.parametrize("case", SELECTED, ids=lambda case: case["id"])
def test_seeded_assistant_case(cloud, monkeypatch, case):
    record = {
        "id": case["id"],
        "title": case["title"],
        "variant": case.get("variant", "main"),
        "setup_required": case.get("setup", ""),
        "steps": [],
        "account_isolation": "每条独立测试账号、会话与Redis命名空间",
    }
    sql_hook = None
    writes = []
    try:
        setup = prepare(cloud, case)
        record["setup"] = setup
        if os.getenv("ASSISTANT_EVAL_PREPARE_ONLY") == "1":
            return
        sql_hook = observer(writes)
        event.listen(engine, "after_cursor_execute", sql_hook)
        traces = []
        original = agent_tasks.run_graph

        def trace(*args, **kw):
            result = original(*args, **kw)
            traces.append(
                {
                    k: result.get(k)
                    for k in (
                        "observations",
                        "knowledge",
                        "web_results",
                        "decision",
                        "proposed_actions",
                        "iteration",
                        "claim_retries",
                        "stalled_on",
                    )
                }
            )
            return result

        monkeypatch.setattr(agent_tasks, "run_graph", trace)
        monkeypatch.setattr(agent_runs.run_task, "delay", agent_tasks.execute_run)
        monkeypatch.setattr(agent_runs.resume_task, "delay", agent_tasks.execute_plan)
        thread = cloud.post("/api/assistant/threads", json={"fresh": True})
        assert thread.status_code == 200, thread.text
        thread_id = thread.json()["thread_id"]
        current, approval = None, None
        for step in case["steps"]:
            writes.clear()
            trace_start = len(traces)
            before = current_state(setup)
            start = time.monotonic()
            entry = {
                "input": step.get("user", step.get("ui_action")),
                "expected": step["expect"],
                "started_at": datetime.now().astimezone().isoformat(),
            }
            if "user" in step:
                response = cloud.post(
                    "/api/agent/runs",
                    json={"thread_id": thread_id, "prompt": step["user"]},
                )
            elif step["ui_action"] == "approve_again":
                response = (
                    cloud.post(approval[0], json=approval[1]) if approval else None
                )
            elif current and current["status"] == "waiting":
                selected = (
                    [a["id"] for a in current["actions"] if a["status"] == "proposed"]
                    if step["ui_action"] == "approve"
                    else []
                )
                path = f"/api/agent/runs/{current['id']}/resume"
                body = {
                    "plan_version": current["plan_version"],
                    "selected_action_ids": selected,
                }
                if step["ui_action"] == "approve":
                    approval = (path, body)
                response = cloud.post(path, json=body)
            else:
                response = None
            if response is None:
                entry["skipped"] = "当前没有可确认计划或上次确认请求"
            else:
                entry["http_status"] = response.status_code
                if response.status_code >= 400:
                    entry["error"] = response.json()
                    current = None
                else:
                    current = response.json()
                    current = cloud.get(f"/api/agent/runs/{current['id']}").json()
                    entry["actual"] = current
                    entry["actions"] = actions(current)
            entry["latency_ms"] = round((time.monotonic() - start) * 1000)
            entry["business_writes"] = list(writes)
            after = current_state(setup)
            entry["business_delta"] = delta(before, after)
            entry["guard_changes"] = [
                c for c in entry["business_delta"] if c["id"] in setup["guard_ids"]
            ]
            entry["trace"] = (
                traces[-1] if "user" in step and len(traces) > trace_start else None
            )
            record["steps"].append(entry)
        record["after"] = current_state(setup)
    except Exception as error:
        record["capture_error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        if sql_hook is not None:
            event.remove(engine, "after_cursor_execute", sql_hook)
        cleanup_sharing(record)
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        with OUTPUT.open("a") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        print("SEEDED_CAPTURED", case["id"], flush=True)
