"""完整列表与同批对象字段同时返回时只展示一次明细。"""

import pytest

from backend.features.assistant.answer_claims import AnswerClaim
from backend.features.assistant.answer_guard import guard_decision
from backend.features.assistant.autonomous_types import Decision, initial_state


@pytest.mark.parametrize(
    "domain,tool", [("voice_memo", "list_voice_memos"), ("reminder", "list_reminders")]
)
@pytest.mark.parametrize("mode", ["complete", "partial", "invalid", "other_scope"])
def test_count_and_fields_do_not_repeat_complete_details(domain, tool, mode):
    state = initial_state("状态是什么")
    state["observations"] = [
        {
            "tool_name": tool,
            "arguments": {},
            "result": {
                "items": [
                    {"id": "a", "title": "检查窗户", "status": "draft"},
                    {"id": "b", "title": "检查门锁", "status": "draft"},
                ],
                "complete": True,
                "total_count": 2,
            },
        }
    ]
    count = AnswerClaim(kind="count", domain=domain, value=2, evidence_ids=["read-1"])
    fields = [
        AnswerClaim(
            kind="field",
            domain=domain,
            subject_id=key,
            path=f"/items/{i}/status",
            value="draft",
            evidence_ids=["read-1"],
        )
        for i, key in enumerate(["a", "b"])
    ]
    if mode == "partial":
        fields = fields[:1]
    elif mode == "invalid":
        fields[1] = fields[1].model_copy(update={"value": "converted"})
    elif mode == "other_scope":
        fields[1] = fields[1].model_copy(update={"scope": {"status": "draft"}})
    state["claim_retries"] = 1
    result = guard_decision(
        state,
        Decision(
            action="final_answer",
            answer_kind="business",
            claims=[count, *fields],
        ),
    )
    assert "2项" in result.answer
    assert result.answer.count("检查窗户") == (1 if mode == "complete" else 2)
    assert "检查门锁" in result.answer
    assert bool("其余结论暂未核实" in result.answer) == (
        mode in {"invalid", "other_scope"}
    )
