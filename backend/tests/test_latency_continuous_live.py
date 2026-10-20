"""一个连续会话、多功能真实队列回放，测量每题完整等待时间。"""

import json
import os
import subprocess
from itertools import pairwise
from pathlib import Path
from time import monotonic, perf_counter, sleep
from uuid import UUID, uuid4

import pytest
from langgraph.checkpoint.postgres import PostgresSaver
from latency_conversation_cases import GROUPS, seed
from sqlalchemy.orm import Session

from backend.api.routes import agent_runs
from backend.core.security import settings
from backend.db.agent_models import AgentRun
from backend.db.session import engine
from backend.features.assistant.agent_celery import celery

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LATENCY_CONVERSATION") != "1", reason="显式启用全功能连续对话采样"
)
OUTPUT = Path(
    os.getenv(
        "ASSISTANT_LATENCY_OUTPUT",
        str(
            Path(__file__).parent
            / "results/assistant_latency_continuous_2026-10-19.jsonl"
        ),
    )
)


def worker_records(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def checkpoints(run_id):
    with PostgresSaver.from_conn_string(settings.checkpoint_url) as saver:
        points = list(
            reversed(
                list(saver.list({"configurable": {"thread_id": run_id}}, limit=80))
            )
        )
    actions = []
    for previous, current in pairwise(points):
        old = previous.checkpoint.get("channel_values", {})
        new = current.checkpoint.get("channel_values", {})
        if new.get("iteration", 0) > old.get("iteration", 0):
            actions.append((new.get("decision") or {}).get("action"))
    final = points[-1].checkpoint.get("channel_values", {}) if points else {}
    return {
        "graph_actions": actions,
        "reads": len(final.get("observations", [])),
        "history_messages": len(final.get("history", [])),
        "summary_chars": len(final.get("conversation_summary", "")),
        "answer_kind": (final.get("decision") or {}).get("answer_kind"),
    }


def test_continuous_conversation_all_features(cloud, monkeypatch, tmp_path):
    assert engine.url.database == "ai_agent_test"
    assert not OUTPUT.exists(), (
        "请通过ASSISTANT_LATENCY_OUTPUT指定新文件，保留已有原始记录"
    )
    available = seed(cloud)
    queue = "ai-agent-latency-" + uuid4().hex
    metrics = tmp_path / "worker-metrics.jsonl"
    env = {
        **os.environ,
        "POSTGRES_DB": "ai_agent_test",
        "REDIS_NAMESPACE": settings.redis_namespace,
        "LATENCY_QUEUE": queue,
        "LATENCY_METRICS_PATH": str(metrics),
        "LATENCY_BASELINE_REF": "d3d3d68",
        "LANGSMITH_TRACING": "false",
        "EMAIL_SCHEDULER_ENABLED": "false",
    }
    log = (tmp_path / "worker.log").open("w")
    worker = subprocess.Popen(
        ["uv", "run", "python", "tests/latency_conversation_worker.py"],
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    try:
        deadline = monotonic() + 40
        while monotonic() < deadline and worker.poll() is None:
            if any(r.get("phase") == "worker_ready" for r in worker_records(metrics)):
                break
            sleep(0.2)
        else:
            pytest.fail("隔离Worker未就绪；日志仅保留于本地临时目录")
        original_task = agent_runs.run_task
        monkeypatch.setattr(
            original_task,
            "delay",
            lambda *args: original_task.apply_async(args=args, queue=queue),
        )
        thread = cloud.post("/api/assistant/threads", json={"fresh": True}).json()[
            "thread_id"
        ]
        OUTPUT.write_text(
            json.dumps(
                {
                    "metadata": True,
                    "thread_id": thread,
                    "question_count": sum(map(len, GROUPS.values())),
                    "groups": len(GROUPS),
                    "baseline_registry": "d3d3d68",
                    "model": settings.llm_model,
                    "dependencies": available,
                    "transport": "TestClient + isolated real Celery queue + 700ms polling",
                }
            )
            + "\n"
        )
        index = 0
        for group, prompts in GROUPS.items():
            for prompt in prompts:
                index += 1
                started = perf_counter()
                response = cloud.post(
                    "/api/agent/runs", json={"thread_id": thread, "prompt": prompt}
                )
                submit_seconds = perf_counter() - started
                assert response.status_code < 400, response.text
                result = response.json()
                run_id = result["id"]
                polls = 0
                while (
                    result["status"] in {"queued", "running"}
                    and perf_counter() - started < 120
                ):
                    sleep(0.7)
                    polls += 1
                    response = cloud.get("/api/agent/runs/" + run_id)
                    assert response.status_code == 200, response.text
                    result = response.json()
                visible_seconds = perf_counter() - started
                with Session(engine) as db:
                    run = db.get(AgentRun, UUID(run_id))
                    created_at = run.created_at.timestamp()
                    backend_seconds = (run.updated_at - run.created_at).total_seconds()
                records = [
                    r for r in worker_records(metrics) if r.get("run_id") == run_id
                ]
                beginnings = [
                    r["time"] for r in records if r.get("phase") == "worker_start"
                ]
                sample = {
                    "index": index,
                    "group": group,
                    "prompt": prompt,
                    "run_id": run_id,
                    "status": result["status"],
                    "visible_seconds": visible_seconds,
                    "submit_seconds": submit_seconds,
                    "backend_seconds": backend_seconds,
                    "queue_start_seconds": beginnings[0] - created_at
                    if beginnings
                    else None,
                    "poll_count": polls,
                    "metrics": records,
                    "answer": result.get("final_answer"),
                    "error": result.get("error"),
                    "actions": [
                        {"title": a["title"], "status": a["status"]}
                        for a in result.get("actions", [])
                    ],
                    **checkpoints(run_id),
                }
                with OUTPUT.open("a") as stream:
                    stream.write(
                        json.dumps(sample, ensure_ascii=False, default=str) + "\n"
                    )
                print(
                    f"LATENCY {index:02d} {group} {visible_seconds:.2f}s status={result['status']} rounds={len(sample['graph_actions'])}",
                    flush=True,
                )
                if result["status"] == "waiting":
                    cancelled = cloud.post(
                        "/api/agent/runs/" + run_id + "/cancel", json={}
                    )
                    assert cancelled.status_code == 200
                elif result["status"] in {"queued", "running"}:
                    cloud.post("/api/agent/runs/" + run_id + "/cancel", json={})
                    pytest.fail("单题超过120秒，停止继续排队；已记录并请求取消")
    finally:
        worker.terminate()
        try:
            worker.wait(timeout=40)
        except subprocess.TimeoutExpired:
            worker.kill()
            worker.wait(timeout=5)
        log.close()
        assert queue.startswith("ai-agent-latency-")
        with celery.connection_for_write() as connection:
            connection.default_channel.queue_delete(queue=queue)
