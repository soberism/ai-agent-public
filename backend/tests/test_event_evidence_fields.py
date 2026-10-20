import json
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from backend.api.routes import assistant_read_steps as reads
from backend.features.assistant.answer_claims import AnswerClaim
from backend.features.assistant.answer_suggestions import from_result
from backend.features.assistant.autonomous_types import initial_state
from backend.features.assistant.claim_verification import verify


def test_event_detail_keeps_native_fields_for_claims_and_existing_recommendations(
    monkeypatch,
):
    target = str(uuid4())
    native = {
        "id": target,
        "title": "会议",
        "status": "scheduled",
        "start_date": "2026-10-16",
        "start_time": "12:00",
        "end_date": "2026-10-16",
        "end_time": "15:00",
        "location": "会议室A",
    }
    monkeypatch.setattr(reads, "prepare", lambda *_: ({"event_id": target}, {}))
    monkeypatch.setattr(
        reads,
        "event_detail",
        lambda *_: SimpleNamespace(model_dump=lambda **_: native.copy()),
    )
    result = json.loads(
        reads.inspect(
            "get_event", {"event_id": target}, Mock(), Mock(), Mock(), uuid4()
        )
    )
    assert result["items"][0]["end_time"] == "15:00"
    assert from_result(uuid4(), result)
    state = initial_state("日程地点")
    state["observations"] = [
        {"tool_name": "get_event", "arguments": {"event_id": target}, "result": result}
    ]
    claim = AnswerClaim(
        kind="field",
        domain="event",
        subject_id=target,
        path="/items/0/location",
        value="会议室A",
        evidence_ids=["read-1"],
    )
    assert "会议室A" in verify(state, [claim])[0][0]
    result["items"][0]["due_time"] = "12:00"
    claim.path, claim.value = "/items/0/due_time", "12:00"
    assert "开始时间" in verify(state, [claim])[0][0]
