"""专用测试队列Worker，记录计时元数据，不记录模型输入正文。"""

import importlib.util
import json
import os
import subprocess
import sys
from contextvars import ContextVar
from pathlib import Path
from time import perf_counter, time
from types import SimpleNamespace

from celery.signals import task_prerun, worker_ready

from backend.features.assistant import (
    autonomous_model,
    conversation_context,
    summary_jobs,
    tool_registry,
)
from backend.features.assistant.agent_celery import celery

METRICS = Path(os.environ["LATENCY_METRICS_PATH"])
active = ContextVar("latency_run", default="")
phase = ContextVar("latency_phase", default="model")


def record(data):
    with METRICS.open("a") as stream:
        stream.write(json.dumps({"run_id": active.get(), **data}) + "\n")


@task_prerun.connect
def begin(task_id=None, args=None, sender=None, **kwargs):
    index = 1 if sender and sender.name == "assistant.summarize" else 0
    active.set(str(args[index]) if args else "")
    record({"phase": "worker_start", "time": time()})


if os.environ.get("LATENCY_BASELINE_REF"):
    source = subprocess.check_output(
        [
            "git",
            "show",
            os.environ["LATENCY_BASELINE_REF"]
            + ":backend/src/backend/features/assistant/tool_registry.py",
        ],
        text=True,
    )
    baseline_path = METRICS.parent / "baseline_registry.py"
    baseline_path.write_text(source)
    spec = importlib.util.spec_from_file_location(
        "latency_baseline_registry", baseline_path
    )
    baseline = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = baseline
    spec.loader.exec_module(baseline)
    tool_registry.search = baseline.search


@worker_ready.connect
def ready(**kwargs):
    record({"phase": "worker_ready"})


original_client = autonomous_model.client
original_prepare = conversation_context.prepare


def measured_client():
    api = original_client()
    create = api.chat.completions.create

    def measured_create(**kwargs):
        started = perf_counter()
        try:
            result = create(**kwargs)
        except Exception:
            record(
                {
                    "phase": phase.get(),
                    "seconds": perf_counter() - started,
                    "failed": True,
                }
            )
            raise
        record(
            {
                "phase": phase.get(),
                "seconds": perf_counter() - started,
                "input_chars": sum(
                    len(str(m.get("content", ""))) for m in kwargs.get("messages", [])
                ),
                "tool_count": len(kwargs.get("tools", [])),
                "usage": result.usage.model_dump() if result.usage else None,
            }
        )
        return result

    return SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=measured_create))
    )


def measured_prepare(*args, **kwargs):
    started = perf_counter()
    token = phase.set("summary_model")
    try:
        return original_prepare(*args, **kwargs)
    finally:
        phase.reset(token)
        record({"phase": "context_prepare", "seconds": perf_counter() - started})


autonomous_model.client = measured_client
conversation_context.prepare = measured_prepare
# agent_tasks导入了prepare别名，需在Worker启动前同步替换。
from backend.features.assistant import agent_tasks

if os.environ.get("LATENCY_MODE") == "background":
    original_wait = summary_jobs.prepare

    def measured_wait(*args, **kwargs):
        started = perf_counter()
        try:
            return original_wait(*args, **kwargs)
        finally:
            record({"phase": "context_wait", "seconds": perf_counter() - started})

    agent_tasks.conversation_context = measured_wait
else:
    agent_tasks.conversation_context = measured_prepare
celery.worker_main(
    [
        "worker",
        "--pool=solo",
        "--concurrency=1",
        "--without-gossip",
        "--without-mingle",
        "--without-heartbeat",
        "--loglevel=WARNING",
        "-Q",
        os.environ["LATENCY_QUEUE"],
        "-n",
        os.environ["LATENCY_QUEUE"] + "@%h",
    ]
)
