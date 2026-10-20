from datetime import date

import pytest
from helpers import PASSWORD, register
from pydantic import ValidationError

from backend.api.calendar_schemas import EventCreate, EventQuery


def body(**changes):
    return {
        "title": "社区读书会",
        "description": "带上笔记",
        "location": "社区中心",
        "start_date": "2026-09-16",
        "start_time": "23:30",
        "end_date": "2026-09-17",
        "end_time": "00:30",
        **changes,
    }


def test_event_validation_rejects_reverse_range():
    with pytest.raises(ValidationError):
        EventCreate(**body(end_date="2026-09-16", end_time="23:00"))
    with pytest.raises(ValidationError):
        EventQuery(date_from=date(2026, 1, 1), date_to=date(2027, 1, 2))


def test_event_crud_query_and_isolation(cloud):
    _, first_email = register(cloud)
    created = cloud.post("/api/calendar/events", json=body())
    assert created.status_code == 201, created.text
    event = created.json()
    assert event["timezone"] == "Asia/Shanghai"

    for day in ("2026-09-16", "2026-09-17"):
        result = cloud.get(
            "/api/calendar/events", params={"date_from": day, "date_to": day}
        )
        assert [item["id"] for item in result.json()["items"]] == [event["id"]]

    updated = cloud.put(
        f"/api/calendar/events/{event['id']}",
        json=body(title="改期后的读书会", start_time="20:00", end_time="21:00"),
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "改期后的读书会"

    assert cloud.post("/api/auth/logout").status_code == 204
    register(cloud)
    assert cloud.get(f"/api/calendar/events/{event['id']}").status_code == 404
    assert (
        cloud.delete(
            f"/api/calendar/events/{event['id']}",
            headers={"Content-Type": "application/json"},
        ).status_code
        == 404
    )

    assert cloud.post("/api/auth/logout").status_code == 204
    assert (
        cloud.post(
            "/api/auth/login", json={"email": first_email, "password": PASSWORD}
        ).status_code
        == 200
    )
    assert (
        cloud.delete(
            f"/api/calendar/events/{event['id']}",
            headers={"Content-Type": "application/json"},
        ).status_code
        == 204
    )
