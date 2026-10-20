"""多轮日程缺少结束时间时，补充后仍保持家庭共享范围。"""

import copy
import os
from pathlib import Path

import pytest
import test_assistant_eval_seeded_live as seeded


@pytest.mark.skipif(
    os.getenv("RUN_SEEDED_ASSISTANT_EVAL") != "1", reason="显式启用真实模型隔离回放"
)
def test_shared_event_followup(cloud, monkeypatch):
    case = copy.deepcopy(
        next(case for case in seeded.CASES if case["id"] == "TURN-011")
    )
    case["steps"].insert(
        -1,
        {
            "user": "只这一次，十一点结束。现在请帮我生成待确认操作计划。",
            "expect": {"kind": "confirm", "tool": "create_shared_event"},
        },
    )
    monkeypatch.setattr(
        seeded,
        "OUTPUT",
        Path(__file__).parent / "results/assistant_scope_followup_2026-10-16.jsonl",
    )
    seeded.test_seeded_assistant_case(cloud, monkeypatch, case)
