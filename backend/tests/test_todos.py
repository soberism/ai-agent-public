"""Run with RUN_INTEGRATION=1 POSTGRES_DB=ai_agent_test; cloud services only."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.api.routes import todos
from backend.api.schemas import TodoQuery
from backend.app import app

HEADERS = {"Origin": "http://localhost:5173", "X-App-Request": "1"}
PASSWORD = "合法测试密码12345678"


from helpers import create, register


def test_future_time_query_validation():
    query = TodoQuery(due="future", due_time="18:00")
    assert query.due == "future" and query.due_time == "18:00"


def test_custom_date_range_validation():
    query = TodoQuery(date_from=date(2026, 9, 21), date_to=date(2026, 9, 27))
    assert query.date_from == date(2026, 9, 21)
    assert query.date_to == date(2026, 9, 27)


def test_custom_date_range_filters_todos(cloud):
    register(cloud)
    monday = create(cloud, title="周一事项", due_date="2026-09-21")
    tuesday = create(cloud, title="周二事项", due_date="2026-09-22")
    create(cloud, title="再下一周", due_date="2026-09-28")

    items = cloud.get(
        "/api/todos",
        params={"date_from": "2026-09-21", "date_to": "2026-09-27"},
    ).json()["items"]
    assert {item["id"] for item in items} == {monday["id"], tuesday["id"]}


def test_todos_idempotency_state_dates_and_pagination(cloud, monkeypatch):
    register(cloud)
    key = str(uuid4())
    body = {
        "title": " 🐈买牛奶 ",
        "description": "<script>原样</script>\n第二行",
        "due_date": "2026-09-15",
        "due_time": "18:00",
    }

    def post():
        return cloud.post("/api/todos", json=body, headers={"Idempotency-Key": key})

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: post(), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 201]
    item = responses[0].json()
    assert item["due_at"] == "2026-09-15T10:00:00Z"
    path = "/api/todos/" + item["id"]
    first = cloud.patch(path, json={"status": "completed"}).json()
    second = cloud.patch(path, json={"status": "completed"}).json()
    assert (
        first["completed_at"] == second["completed_at"]
        and first["updated_at"] == second["updated_at"]
    )
    assert cloud.patch(path, json={"title": "新标题"}).json()["status"] == "completed"
    assert post().json()["title"] == "新标题"
    assert (
        cloud.post(
            "/api/todos", json={"title": "别的"}, headers={"Idempotency-Key": key}
        ).status_code
        == 409
    )
    updated = cloud.patch(path, json={"status": "ongoing", "due_date": None}).json()
    assert (
        updated["completed_at"] is None
        and updated["due_time"] is None
        and updated["due_at"] is None
    )
    assert cloud.patch(path, json={"due_time": "18:00"}).status_code == 422
    monkeypatch.setattr(todos, "utcnow", lambda: datetime(2026, 9, 14, 16, tzinfo=UTC))
    dated = create(cloud, due_date="2026-09-14")
    assert dated["is_overdue"]
    assert not create(cloud, due_date="2026-09-15")["is_overdue"]
    for i in range(22):
        create(cloud, title=f"条目{i}")
    first = cloud.get("/api/todos").json()
    second = cloud.get("/api/todos", params={"cursor": first["next_cursor"]}).json()
    assert len(first["items"]) == 20 and len(second["items"]) == 5
    assert len({t["id"] for t in first["items"] + second["items"]}) == 25
    assert second["next_cursor"] is None
    assert (
        cloud.get(
            "/api/todos", params={"cursor": first["next_cursor"], "due": "none"}
        ).status_code
        == 422
    )
    assert (
        cloud.get(
            "/api/todos", params={"cursor": first["next_cursor"] + "X"}
        ).status_code
        == 422
    )
    assert (
        cloud.get(
            "/api/todos", params={"status": "completed", "due": "overdue"}
        ).status_code
        == 422
    )
    assert len(cloud.get("/api/todos", params={"due": "today"}).json()["items"]) == 1
    future_six = create(cloud, due_date="2026-09-16", due_time="18:00")
    create(cloud, due_date="2026-09-16", due_time="19:00")
    filtered = cloud.get(
        "/api/todos", params={"due": "future", "due_time": "18:00"}
    ).json()["items"]
    assert [item["id"] for item in filtered] == [future_six["id"]]
    other = TestClient(app, headers=HEADERS)
    register(other)
    assert other.delete(f"/api/todos/{future_six['id']}").status_code == 404
    assert cloud.get(f"/api/todos/{future_six['id']}").status_code == 200
    assert cloud.delete(f"/api/todos/{future_six['id']}").status_code == 204
    assert cloud.get(f"/api/todos/{future_six['id']}").status_code == 404
    other.close()


def test_malformed_payloads_are_validation_errors(cloud):
    register(cloud)
    item = create(cloud)
    for payload in (["title"], "title", 1, None):
        assert (
            cloud.patch(
                "/api/todos/" + item["id"],
                json=payload,
                headers={"Content-Type": "application/json"},
            ).status_code
            == 422
        )
    for day in ("0001-01-01", "9999-12-31"):
        assert (
            cloud.post(
                "/api/todos",
                headers={"Idempotency-Key": str(uuid4())},
                json={"title": "边界", "due_date": day, "due_time": "00:00"},
            ).status_code
            == 422
        )
    assert (
        cloud.post(
            "/api/todos?owner_id=other",
            headers={"Idempotency-Key": str(uuid4())},
            json={"title": "不可创建"},
        ).status_code
        == 422
    )


def test_anchored_cross_day_and_owner_cursor(cloud, monkeypatch):
    register(cloud)
    now = datetime(2026, 9, 14, 15, 59, tzinfo=UTC)
    monkeypatch.setattr(todos, "utcnow", lambda: now)
    for _ in range(3):
        create(cloud, due_date="2026-09-14")
    create(cloud, due_date="2026-09-15")
    first = cloud.get("/api/todos", params={"due": "today", "limit": 2}).json()
    monkeypatch.setattr(todos, "utcnow", lambda: now + timedelta(minutes=2))
    second = cloud.get(
        "/api/todos",
        params={"due": "today", "limit": 2, "cursor": first["next_cursor"]},
    ).json()
    assert len(second["items"]) == 1 and second["server_time"] == first["server_time"]
    assert not second["items"][0]["is_overdue"]
    assert len(cloud.get("/api/todos", params={"due": "today"}).json()["items"]) == 1
    other = TestClient(app, headers=HEADERS)
    register(other)
    assert (
        other.get(
            "/api/todos", params={"due": "today", "cursor": first["next_cursor"]}
        ).status_code
        == 422
    )
    other.close()
