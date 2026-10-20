"""Run only against the isolated ai_agent_test database and Redis namespace."""

from helpers import family_accounts, login_as

from backend.api.routes import assistant
from backend.features.assistant.graph import Intent


def test_confirmed_shared_event_is_visible_to_family_member(cloud, monkeypatch):
    _, owner_cookie, home, _, member_cookie, *_ = family_accounts(cloud)
    login_as(cloud, owner_cookie)
    monkeypatch.setattr(
        assistant,
        "interpret",
        lambda *_: Intent(
            action="feature",
            feature="create_shared_event",
            payload={
                "household_id": home["name"],
                "body": {
                    "title": "家庭会议",
                    "start_date": "2026-09-22",
                    "start_time": "19:00",
                    "end_date": "2026-09-22",
                    "end_time": "20:00",
                },
            },
        ),
    )
    thread = cloud.post("/api/assistant/threads", json={}).json()["thread_id"]
    draft = cloud.post(
        "/api/assistant/messages",
        json={"thread_id": thread, "message": "创建家庭可见日程"},
    )
    assert draft.status_code == 200, draft.text
    assert draft.json()["kind"] == "confirm"

    created = cloud.post(
        f"/api/assistant/actions/{draft.json()['action_token']}/confirm", json={}
    )
    assert created.status_code == 200, created.text
    event_id = created.json()["items"][0]["id"]

    login_as(cloud, member_cookie)
    calendar = cloud.get(
        "/api/calendar/events",
        params={"date_from": "2026-09-22", "date_to": "2026-09-22"},
    )
    assert calendar.status_code == 200
    assert event_id in {item["id"] for item in calendar.json()["items"]}
