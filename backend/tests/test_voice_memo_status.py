"""语音备忘的状态含义与其他业务状态隔离。"""

import os
from pathlib import Path

import pytest
from test_assistant_priority_fixes_live import agent  # noqa: F401

from backend.features.assistant.answer_claims import AnswerClaim
from backend.features.assistant.autonomous_types import initial_state
from backend.features.assistant.claim_verification import verify


@pytest.mark.parametrize(
    "status,target,meaning",
    [
        ("draft", None, "已保存，尚未转为待办或日程"),
        ("converted", "todo", "已转为待办"),
        ("converted", "event", "已转为日程"),
        ("converted", None, "已转换"),
    ],
)
def test_voice_status_count_and_field_have_same_meaning(status, target, meaning):
    state = initial_state("状态是啥")
    state["observations"] = [
        {
            "tool_name": "list_voice_memos",
            "arguments": {},
            "result": {
                "items": [
                    {
                        "id": "memo",
                        "transcript": "检查窗户",
                        "status": status,
                        "target_type": target,
                    }
                ],
                "total_count": 1,
                "complete": True,
            },
        }
    ]
    count = AnswerClaim(
        kind="count", domain="voice_memo", value=1, evidence_ids=["read-1"]
    )
    field = AnswerClaim(
        kind="field",
        domain="voice_memo",
        subject_id="memo",
        path="/items/0/status",
        value=status,
        evidence_ids=["read-1"],
    )
    for claim in [count, field]:
        accepted, errors = verify(state, [claim])
        assert not errors and meaning in accepted[0] and "检查窗户" in accepted[0]
    assert verify(
        state,
        [
            field.model_copy(
                update={"value": "converted" if status == "draft" else "draft"}
            )
        ],
    )[1]
    state["observations"][0]["tool_name"] = "list_meals"
    accepted, errors = verify(state, [count.model_copy(update={"domain": "meal"})])
    assert not errors and "已保存，尚未转为" not in accepted[0]
    if status == "draft":
        assert "待确认" in accepted[0] and "草稿" not in accepted[0]


@pytest.mark.skipif(os.getenv("RUN_LIVE_MODEL") != "1", reason="显式启用真实模型")
@pytest.mark.parametrize("followup", ["状态是啥", "状态是什么", "这个状态什么意思"])
def test_voice_status_followup_uses_fields_instead_of_repeating_count(
    cloud, monkeypatch, request, followup
):
    import test_assistant_priority_fixes_live as priority

    monkeypatch.setattr(
        priority,
        "OUTPUT",
        Path(__file__).parent
        / "results/assistant_voice_status_overlap_2026-10-19.jsonl",
    )
    send = request.getfixturevalue("agent")
    for text in ["Search.", "这什么？", "嗯。"]:
        response = cloud.post("/api/assistant/voice-memos", json={"transcript": text})
        assert response.status_code == 201, response.text
    first, _ = send("有什么语音备忘")
    assert "语音备忘3项" in first["final_answer"]
    assert "草稿" not in first["final_answer"] and "已保存" in first["final_answer"]
    answer, actions = send(followup)
    assert answer["status"] == "completed" and not actions
    assert (
        "已保存" in answer["final_answer"]
        and "尚未转为待办或日程" in answer["final_answer"]
    )
    assert "语音备忘3项" not in answer["final_answer"]
    for title in ["Search.", "这什么？", "嗯。"]:
        assert answer["final_answer"].count(title) == 1
    assert send.traces[-1]["decision"]["claims"]
    assert any(
        row["tool_name"] == "list_voice_memos"
        for row in send.traces[-1]["observations"]
    )
    assert all(
        claim["kind"] == "field" for claim in send.traces[-1]["decision"]["claims"]
    )
