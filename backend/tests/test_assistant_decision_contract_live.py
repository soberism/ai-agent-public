"""用合成请求捕获决策契约错误，避免统一错误掩盖解析原因。"""

import json
import os
from pathlib import Path

import pytest
from test_assistant_priority_fixes_live import agent  # noqa: F401

from backend.features.assistant import autonomous_model

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_MODEL") != "1", reason="显式启用真实模型"
)


@pytest.mark.parametrize("repeat", range(5))
def test_explicit_todo_decision_contract(cloud, request, monkeypatch, repeat):
    send = request.getfixturevalue("agent")
    original = autonomous_model.parse_decision
    records = []

    def parsed(arguments, state):
        record = {"arguments": arguments, "stalled_on": state.get("stalled_on")}
        records.append(record)
        try:
            result = original(arguments, state)
            record["parsed"] = result.model_dump(mode="json")
            return result
        except (ValueError, TypeError) as error:
            record["parse_error"] = str(error)
            raise

    monkeypatch.setattr(autonomous_model, "parse_decision", parsed)
    run, tools = send("下个月 3 号上午十点提醒我给植物换盆。")
    output = (
        Path(__file__).parent
        / "results"
        / "assistant_decision_diagnostics_2026-10-16.jsonl"
    )
    with output.open("a") as stream:
        stream.write(
            json.dumps(
                {
                    "repeat": repeat,
                    "attempt": os.getenv("PRIORITY_EVAL_ATTEMPT"),
                    "records": records,
                    "run": run,
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    assert run["status"] == "waiting", run
    assert [t["tool_name"] for t in tools] == ["create_todo"], tools
    assert cloud.get("/api/todos").json()["items"] == []
