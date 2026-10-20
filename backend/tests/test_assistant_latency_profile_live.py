"""分场景采样模型等待，不以单次样本宣称整体延迟分位数。"""

import json
import os
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

import pytest
from test_assistant_priority_fixes_live import agent  # noqa: F401

from backend.features.assistant import autonomous_model

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_MODEL") != "1", reason="显式启用真实模型"
)


@pytest.mark.parametrize(
    "prompts",
    [
        ["你好"],
        ["简单解释一下什么是时间管理"],
        ["有什么待办"],
        ["有什么餐食计划"],
        ["介绍一下番茄意面", "怎么做？"],
    ],
)
def test_profile_assistant_latency_by_scenario(cloud, monkeypatch, request, prompts):
    import test_assistant_priority_fixes_live as priority

    output = (
        Path(__file__).parent / "results/assistant_latency_profile_2026-10-19.jsonl"
    )
    monkeypatch.setattr(priority, "OUTPUT", output)
    send = request.getfixturevalue("agent")
    make_client = autonomous_model.client
    calls = []

    def measured_client():
        api = make_client()
        create = api.chat.completions.create

        def measured_create(**kwargs):
            started = perf_counter()
            result = create(**kwargs)
            calls.append(
                {
                    "seconds": perf_counter() - started,
                    "input_chars": sum(
                        len(str(m.get("content", "")))
                        for m in kwargs.get("messages", [])
                    ),
                    "tool_count": len(kwargs.get("tools", [])),
                    "usage": result.usage.model_dump() if result.usage else None,
                }
            )
            return result

        return SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=measured_create))
        )

    monkeypatch.setattr(autonomous_model, "client", measured_client)
    for prompt in prompts:
        calls.clear()
        started = perf_counter()
        result, actions = send(prompt)
        metrics = {
            "timing_sample": True,
            "prompt": prompt,
            "total_seconds": perf_counter() - started,
            "model_calls": list(calls),
            "status": result["status"],
            "reads": len(send.traces[-1]["observations"]),
        }
        with output.open("a") as stream:
            stream.write(json.dumps(metrics, ensure_ascii=False) + "\n")
        assert result["status"] == "completed" and not actions
