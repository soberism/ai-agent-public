"""餐食草稿追问继承业务语境并核实原始状态。"""

import os
from pathlib import Path

import pytest
from test_assistant_priority_fixes_live import agent  # noqa: F401

from backend.features.assistant.answer_claims import AnswerClaim
from backend.features.assistant.autonomous_types import initial_state
from backend.features.assistant.claim_verification import verify


@pytest.mark.parametrize(
    "status,meaning",
    [("draft", "尚未确认加入日历"), ("planned", "已确认餐食安排")],
)
def test_meal_status_field_explains_native_business_meaning(status, meaning):
    state = initial_state("草稿 是什么意思")
    state["observations"] = [
        {
            "tool_name": "list_meals",
            "arguments": {},
            "result": {
                "items": [{"id": "meal", "title": "午餐", "status": status}],
                "complete": True,
                "total_count": 1,
            },
        }
    ]
    claim = AnswerClaim(
        kind="field",
        domain="meal",
        subject_id="meal",
        path="/items/0/status",
        value=status,
        evidence_ids=["read-1"],
    )
    accepted, errors = verify(state, [claim])
    assert not errors and meaning in accepted[0]
    assert "草稿" not in accepted[0]
    count = claim.model_copy(
        update={"kind": "count", "subject_id": "", "path": "", "value": 1}
    )
    lines, errors = verify(state, [count])
    assert not errors and meaning in lines[0] and "草稿" not in lines[0]
    assert verify(state, [claim.model_copy(update={"value": "不存在的状态"})])[1]


@pytest.mark.skipif(os.getenv("RUN_LIVE_MODEL") != "1", reason="显式启用真实模型")
@pytest.mark.parametrize(
    "followup", ["草稿 是什么意思", "草稿是什么意思", "待确认是什么意思"]
)
def test_meal_draft_explanation_stays_in_previous_meal_context(
    cloud, monkeypatch, request, followup
):
    import test_assistant_priority_fixes_live as priority

    monkeypatch.setattr(
        priority,
        "OUTPUT",
        Path(__file__).parent
        / "results/assistant_meal_status_followup_2026-10-19.jsonl",
    )
    send = request.getfixturevalue("agent")
    for title, dish in [("午餐计划", "番茄意面"), ("加餐计划", "番茄炒蛋")]:
        result = cloud.post(
            "/api/life/meal-plans",
            json={
                "schedule_text": title,
                "dish": dish,
                "date": "2026-10-19",
                "meal_type": "lunch",
                "diners": 4,
            },
        )
        assert result.status_code == 201, result.text
    first, _ = send("有什么餐食计划")
    assert "餐食计划2项" in first["final_answer"]
    assert "待确认" in first["final_answer"] and "草稿" not in first["final_answer"]
    result, actions = send(followup)
    assert result["status"] == "completed" and not actions
    assert "尚未确认加入日历" in result["final_answer"]
    assert all(
        word not in result["final_answer"]
        for word in ["语音", "随手记", "告诉我是", "餐食计划2项"]
    )
    trace = send.traces[-1]
    assert any(row["tool_name"] == "list_meals" for row in trace["observations"])
    claims = trace["decision"]["claims"]
    assert len(claims) == 2
    assert all(
        c["kind"] == "field" and c["domain"] == "meal" and c["value"] == "draft"
        for c in claims
    )
