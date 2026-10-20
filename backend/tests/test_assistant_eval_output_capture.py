"""显式运行时捕获全部固定用例的真实模型输出，不将无预置数据当成通过。"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from runpy import run_path

import pytest
from helpers import register

from backend.api.routes import agent_runs
from backend.features.assistant.agent_tasks import execute_plan, execute_run

CASES = run_path(
    str(Path(__file__).resolve().parents[1] / "infra" / "assistant_eval.py")
)["load_cases"]()
RESULT = Path(
    os.getenv(
        "ASSISTANT_EVAL_OUTPUT",
        str(
            Path(__file__).parent
            / "results"
            / "assistant_eval_576_outputs_2026-09-29.jsonl"
        ),
    )
)


@pytest.mark.skipif(
    os.getenv("RUN_ALL_ASSISTANT_EVAL") != "1",
    reason="仅显式 RUN_ALL_ASSISTANT_EVAL=1 才运行真实模型批量回放",
)
def test_capture_all_assistant_outputs(cloud, monkeypatch):
    monkeypatch.setattr(agent_runs.run_task, "delay", execute_run)
    monkeypatch.setattr(agent_runs.resume_task, "delay", execute_plan)
    max_cases = int(os.getenv("ASSISTANT_EVAL_MAX_CASES", "576"))
    offset = int(os.getenv("ASSISTANT_EVAL_OFFSET", "0"))
    selected = list(CASES.values())[offset : offset + max_cases]
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    cloud.cookies.clear()
    register(cloud)
    with RESULT.open("w") as output:
        for case in selected:
            record = {
                "id": case["id"],
                "title": case["title"],
                "setup_required": case.get("setup", ""),
                "setup_ready": False,
                "account_isolation": "共享测试账号；每条独立会话；未做业务数据隔离",
                "steps": [],
            }
            try:
                thread_response = cloud.post(
                    "/api/assistant/threads", json={"fresh": True}
                )
                if thread_response.status_code >= 400:
                    raise RuntimeError(f"创建会话 HTTP {thread_response.status_code}")
                thread_id = thread_response.json()["thread_id"]
                current_run = None
                last_approval = None
                for step in case["steps"]:
                    timer = time.monotonic()
                    started = datetime.now().astimezone().isoformat()
                    if "user" in step:
                        user_input = step["user"]
                        response = cloud.post(
                            "/api/agent/runs",
                            json={"thread_id": thread_id, "prompt": user_input},
                        )
                    else:
                        user_input = step["ui_action"]
                        if user_input == "approve_again":
                            if not last_approval:
                                record["steps"].append(
                                    {"input": user_input, "skipped": "没有上次确认请求"}
                                )
                                continue
                            response = cloud.post(
                                last_approval[0], json=last_approval[1]
                            )
                        elif not current_run or current_run["status"] != "waiting":
                            record["steps"].append(
                                {"input": user_input, "skipped": "当前没有待确认计划"}
                            )
                            continue
                        else:
                            selected_ids = (
                                [
                                    item["id"]
                                    for item in current_run["actions"]
                                    if item["status"] == "proposed"
                                ]
                                if user_input == "approve"
                                else []
                            )
                            path = f"/api/agent/runs/{current_run['id']}/resume"
                            body = {
                                "plan_version": current_run["plan_version"],
                                "selected_action_ids": selected_ids,
                            }
                            if user_input == "approve":
                                last_approval = (path, body)
                            response = cloud.post(path, json=body)
                    detail = {
                        "input": user_input,
                        "expected": step["expect"],
                        "started_at": started,
                        "http_status": response.status_code,
                        "latency_ms": round((time.monotonic() - timer) * 1000),
                    }
                    if response.status_code >= 400:
                        detail["error"] = response.text[:1000]
                        record["steps"].append(detail)
                        current_run = None
                        continue
                    current_run = response.json()
                    if current_run["status"] not in {
                        "completed",
                        "failed",
                        "cancelled",
                        "waiting",
                    }:
                        poll = cloud.get(f"/api/agent/runs/{current_run['id']}")
                        if poll.status_code == 200:
                            current_run = poll.json()
                    detail["actual"] = {
                        "run_status": current_run["status"],
                        "answer": current_run.get("final_answer"),
                        "error": current_run.get("error"),
                        "actions": current_run.get("actions", []),
                        "sources": current_run.get("sources", []),
                    }
                    record["steps"].append(detail)
            except Exception as error:  # noqa: BLE001 - 记录单条失败并继续批量回放
                record["capture_error"] = f"{type(error).__name__}: {error}"
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
            output.flush()
            print(f"CAPTURED {len(record['steps'])} steps {case['id']}", flush=True)
    assert len(selected) == max_cases
