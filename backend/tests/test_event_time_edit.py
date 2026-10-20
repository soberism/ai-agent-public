from types import SimpleNamespace
from uuid import uuid4

from backend.api.routes import calendar_events
from backend.features.assistant.feature_edits import complete_edit


def test_start_time_only_preserves_original_duration_and_date(monkeypatch):
    source = {
        "title": "验证行程",
        "description": None,
        "location": None,
        "start_date": "2026-11-12",
        "start_time": "09:00",
        "end_date": "2026-11-12",
        "end_time": "12:00",
        "starts_at": "2026-11-12T01:00:00Z",
        "ends_at": "2026-11-12T04:00:00Z",
        "timezone": "Asia/Shanghai",
        "status": "scheduled",
    }
    monkeypatch.setattr(
        calendar_events,
        "detail",
        lambda *_: SimpleNamespace(model_dump=lambda **_: source),
    )
    result = complete_edit(
        "edit_event",
        {"event_id": str(uuid4()), "body": {"start_time": "12:00"}},
        None,
        None,
    )
    assert result["body"]["start_time"] == "12:00"
    assert result["body"]["end_time"] == "15:00"
    assert result["body"]["start_date"] == result["body"]["end_date"] == "2026-11-12"
    result = complete_edit(
        "edit_event",
        {"event_id": str(uuid4()), "body": {"start_time": "23:00"}},
        None,
        None,
    )
    assert result["body"]["end_date"] == "2026-11-13"
    assert result["body"]["end_time"] == "02:00"
    result = complete_edit(
        "edit_event",
        {
            "event_id": str(uuid4()),
            "body": {"start_time": "12:00", "end_time": "13:00"},
        },
        None,
        None,
    )
    assert result["body"]["end_time"] == "13:00"
