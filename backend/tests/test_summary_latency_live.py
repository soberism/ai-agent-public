"""真实模型、隔离回答/摘要队列，比较同步、立即追问及空档后追问。"""

import json
import os
import subprocess
from pathlib import Path
from time import monotonic, perf_counter, sleep
from uuid import UUID, uuid4

import pytest
from helpers import register
from langgraph.checkpoint.postgres import PostgresSaver
from sqlalchemy.orm import Session
from test_latency_continuous_live import checkpoints, worker_records

from backend.api.routes import agent_runs
from backend.core.security import redis, settings
from backend.db.models import AssistantMessage
from backend.db.session import engine
from backend.features.assistant import summary_jobs as jobs
from backend.features.assistant.agent_celery import celery
from backend.features.assistant.summary_worker import authorized_messages

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_SUMMARY_LATENCY") != "1", reason="显式启用真实模型双队列采样"
)


def wait_until(predicate):
    deadline = monotonic() + 60
    while monotonic() < deadline:
        if predicate():
            return
        sleep(0.1)
    pytest.fail("隔离测试等待超时")


def test_background_summary_latency(cloud, monkeypatch, tmp_path):
    assert engine.url.database == "ai_agent_test"
    output = Path(os.environ["SUMMARY_LATENCY_OUTPUT"])
    assert not output.exists(), "必须指定新结果文件"
    account, _ = register(cloud)
    owner = account["id"]
    workers, logs, queues, runs, samples = [], [], [], [], []
    summary_queue = "ai-agent-summary-test-" + uuid4().hex
    queues.append(summary_queue)
    monkeypatch.setattr(jobs, "QUEUE", summary_queue)
    metrics = tmp_path / "metrics.jsonl"
    original_task = agent_runs.run_task

    def launch(queue, mode):
        queues.append(queue)
        env = {
            **os.environ,
            "POSTGRES_DB": "ai_agent_test",
            "REDIS_NAMESPACE": settings.redis_namespace,
            "ASSISTANT_SUMMARY_QUEUE": summary_queue,
            "LATENCY_QUEUE": queue,
            "LATENCY_MODE": mode,
            "LATENCY_METRICS_PATH": str(metrics),
            "LANGSMITH_TRACING": "false",
            "EMAIL_SCHEDULER_ENABLED": "false",
        }
        env.pop("LATENCY_BASELINE_REF", None)
        log = (tmp_path / (queue + ".log")).open("w")
        logs.append(log)
        count = sum(r.get("phase") == "worker_ready" for r in worker_records(metrics))
        workers.append(
            subprocess.Popen(
                ["uv", "run", "python", "tests/latency_conversation_worker.py"],
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        )
        wait_until(
            lambda: (
                sum(r.get("phase") == "worker_ready" for r in worker_records(metrics))
                > count
            )
        )

    def seeded_thread(early_only=False):
        thread = cloud.post("/api/assistant/threads", json={"fresh": True}).json()[
            "thread_id"
        ]
        with Session(engine) as db:
            for index in range(8):
                for role, content in [
                    (
                        "user",
                        f"旅行讨论第{index + 1}项：目的地是苏州，同行四人，喜欢园林、步行和清淡饮食。预算每人两千元，优先公共交通，不要代订酒店，也不创建事项。",
                    ),
                    (
                        "assistant",
                        "已理解苏州出行讨论。可以按园林、老街和运河安排路线，保留休息时间；以上只是交流建议，没有执行预订或写入操作。",
                    ),
                ]:
                    if early_only and index > 0:
                        content = content.replace("苏州", "此前选定的城市")
                    db.add(
                        AssistantMessage(
                            thread_id=UUID(thread),
                            role=role,
                            content=content,
                            kind="message",
                        )
                    )
                    db.flush()
            db.commit()
        return thread

    def cache_ready(thread):
        with Session(engine) as db:
            messages = authorized_messages(db, owner, thread)
        cached = jobs.cached(redis, owner, thread, messages)
        older, _ = jobs.memory.split_history(messages)
        return bool(
            cached
            and cached.covered >= len(older)
            and not redis.get(jobs.keys(thread)[1])
        )

    def ask(thread, queue, label):
        monkeypatch.setattr(
            original_task,
            "delay",
            lambda *args: original_task.apply_async(args=args, queue=queue),
        )
        started = perf_counter()
        response = cloud.post(
            "/api/agent/runs",
            json={
                "thread_id": thread,
                "prompt": "之前讨论的旅行目的地是哪里？请只用一句话回答。",
            },
        )
        assert response.status_code < 400, response.text
        result = response.json()
        run_id = result["id"]
        runs.append(run_id)
        while (
            result["status"] in {"queued", "running"} and perf_counter() - started < 90
        ):
            sleep(0.7)
            result = cloud.get("/api/agent/runs/" + run_id).json()
        sample = {
            "scenario": label,
            "run_id": run_id,
            "thread_id": thread,
            "visible_seconds": perf_counter() - started,
            "status": result["status"],
            "answer": result.get("final_answer"),
            "metrics": [
                r for r in worker_records(metrics) if r.get("run_id") == run_id
            ],
            **checkpoints(run_id),
        }
        samples.append(sample)
        output.write_text(
            "\n".join(json.dumps(s, ensure_ascii=False) for s in samples) + "\n"
        )
        print(f"SUMMARY_LATENCY {label} {sample['visible_seconds']:.3f}s", flush=True)
        assert result["status"] == "completed", result.get("error")
        assert "苏州" in result["final_answer"]

    try:
        launch(summary_queue, "background")
        baseline_queue = "ai-agent-summary-test-" + uuid4().hex
        launch(baseline_queue, "synchronous")
        background_queue = "ai-agent-summary-test-" + uuid4().hex
        launch(background_queue, "background")
        ask(seeded_thread(), baseline_queue, "synchronous_baseline")
        thread = seeded_thread()
        assert jobs.schedule(owner, thread)
        assert redis.get(jobs.keys(thread)[1]), "立即追问必须发生在摘要未完成时"
        ask(thread, background_queue, "immediate_followup")
        wait_until(lambda: cache_ready(thread))
        ask(thread, background_queue, "idle_followup_1")
        wait_until(lambda: cache_ready(thread))
        ask(thread, background_queue, "idle_followup_2")
        wait_until(lambda: cache_ready(thread))
        early_thread = seeded_thread(early_only=True)
        assert jobs.schedule(owner, early_thread)
        wait_until(lambda: cache_ready(early_thread))
        with Session(engine) as db:
            early_messages = authorized_messages(db, owner, early_thread)
        cached = jobs.cached(redis, owner, early_thread, early_messages)
        assert "苏州" in cached.summary
        assert all("苏州" not in m["content"] for m in early_messages[cached.covered :])
        ask(early_thread, background_queue, "older_context_only_in_summary")
        wait_until(lambda: cache_ready(early_thread))
        output.with_suffix(".metrics.jsonl").write_text(
            "\n".join(json.dumps(r) for r in worker_records(metrics)) + "\n"
        )
        idle = [s for s in samples if s["scenario"].startswith("idle")]
        assert all(
            sum(m["seconds"] for m in s["metrics"] if m["phase"] == "context_wait")
            < 0.1
            for s in idle
        )
        assert all(
            not any(m["phase"] == "summary_model" for m in s["metrics"])
            for s in samples[1:]
        )
    finally:
        for worker in workers:
            worker.terminate()
        for worker in workers:
            try:
                worker.wait(timeout=30)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait(timeout=5)
        for log in logs:
            log.close()
        with celery.connection_for_write() as connection:
            for queue in set(queues):
                assert queue.startswith("ai-agent-summary-test-")
                connection.default_channel.queue_delete(queue=queue)
        with PostgresSaver.from_conn_string(settings.checkpoint_url) as saver:
            for run_id in runs:
                saver.delete_thread(run_id)
