from uuid import uuid4

import pytest
from helpers import create, register
from pydantic import ValidationError

from backend.api.planning_schemas import ChecklistCreate, ReminderCreate
from backend.api.routes.planning_review import ReviewQuery


def test_planning_contracts_reject_blank_and_ambiguous_subjects():
    with pytest.raises(ValidationError):
        ChecklistCreate(title="  ")
    with pytest.raises(ValidationError):
        ReminderCreate(remind_date="2026-09-16", remind_time="09:00")
    with pytest.raises(ValidationError):
        ReminderCreate(
            todo_id=uuid4(),
            event_id=uuid4(),
            remind_date="2026-09-16",
            remind_time="09:00",
        )
    with pytest.raises(ValidationError):
        ReminderCreate(todo_id=uuid4(), remind_date="bad", remind_time="09:00")


def test_planning_workflows_and_review_integration(cloud):
    register(cloud)
    todo = create(cloud, due_date="2026-09-16", due_time="18:00")

    checklist = cloud.post("/api/planning/checklists", json={"title": "旅行准备"})
    assert checklist.status_code == 201, checklist.text
    checklist_id = checklist.json()["id"]
    added = cloud.post(
        f"/api/planning/checklists/{checklist_id}/items", json={"title": "带护照"}
    )
    item_id = added.json()["items"][0]["id"]
    toggled = cloud.patch(
        f"/api/planning/checklists/{checklist_id}/items/{item_id}",
        json={"completed": True},
    )
    assert toggled.json()["completed_count"] == 1
    newest = cloud.post(
        f"/api/planning/checklists/{checklist_id}/items", json={"title": "带充电器"}
    )
    assert [item["title"] for item in newest.json()["items"]] == ["带充电器", "带护照"]
    assert [
        item["title"]
        for item in cloud.get(f"/api/planning/checklists/{checklist_id}").json()[
            "items"
        ]
    ] == ["带充电器", "带护照"]
    copied = cloud.post(
        f"/api/planning/checklists/{checklist_id}/duplicate",
        headers={"Content-Type": "application/json"},
    )
    assert copied.status_code == 201
    assert copied.json()["title"] == "旅行准备（副本）"
    assert copied.json()["items"][0]["completed"] is False

    event_body = {
        "title": "专注处理待办",
        "start_date": "2026-09-16",
        "start_time": "10:00",
        "end_date": "2026-09-16",
        "end_time": "11:00",
        "todo_id": todo["id"],
        "recurrence": "daily",
        "recurrence_until": "2026-09-17",
    }
    event = cloud.post("/api/calendar/events", json=event_body)
    assert event.status_code == 201, event.text
    assert event.json()["todo_id"] == todo["id"]
    repeated = cloud.get(
        "/api/calendar/events",
        params={"date_from": "2026-09-17", "date_to": "2026-09-17"},
    )
    assert len(repeated.json()["items"]) == 1
    cloud.post(
        "/api/calendar/events",
        json={
            **event_body,
            "title": "重叠会议",
            "start_time": "10:30",
            "end_time": "11:30",
            "recurrence": "none",
            "recurrence_until": None,
        },
    )
    reminder = cloud.post(
        "/api/planning/reminders",
        json={
            "todo_id": todo["id"],
            "remind_date": "2026-09-16",
            "remind_time": "09:00",
        },
    )
    assert reminder.status_code == 201
    assert reminder.json()["delivery"] == "app_only"
    disabled = cloud.patch(
        f"/api/planning/reminders/{reminder.json()['id']}", json={"status": "disabled"}
    )
    assert disabled.json()["status"] == "disabled"

    review = cloud.get(
        "/api/planning/review", params={"date": "2026-09-16", "range": "day"}
    )
    assert review.status_code == 200, review.text
    assert review.json()["summary"]["events"] == 2
    assert len(review.json()["organize"]["conflicts"]) == 1

    assert review.json()["details"]["ongoing"][0]["id"] == todo["id"]
    assert len(review.json()["details"]["events"]) == review.json()["summary"]["events"]
    assert (
        len(review.json()["details"]["completed"])
        == review.json()["summary"]["completed_todos"]
    )


def test_review_date_range_contract():
    query = ReviewQuery(date_from="2026-09-14", date_to="2026-09-20")
    assert (query.date_to - query.date_from).days == 6
    legacy = ReviewQuery(date="2026-09-14", range="week")
    assert (legacy.date_from, legacy.date_to) == (query.date_from, query.date_to)
    for values in [
        {},
        {"date_from": "2026-09-14"},
        {"date_from": "2026-09-20", "date_to": "2026-09-14"},
        {"date_from": "2026-01-01", "date_to": "2027-01-02"},
        {"date_from": "bad", "date_to": "2026-09-20"},
        {"date_from": "9999-12-31", "date_to": "9999-12-31"},
    ]:
        with pytest.raises(ValidationError):
            ReviewQuery(**values)
