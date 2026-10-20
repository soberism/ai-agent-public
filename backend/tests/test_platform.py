"""Run integration cases with RUN_INTEGRATION=1 and the isolated cloud database."""

from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import UUID

from fastapi.testclient import TestClient
from helpers import HEADERS, create, register
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.api.platform_schemas import PlatformSettingsPatch
from backend.api.routes import platform
from backend.app import app
from backend.db.models import Todo, User
from backend.db.session import engine, get_session


def test_platform_settings_validation():
    assert PlatformSettingsPatch(timezone="Asia/Shanghai").timezone == ("Asia/Shanghai")
    assert PlatformSettingsPatch(nickname=" 小赵 ").nickname == "小赵"
    for payload in (
        {},
        {"nickname": "   "},
        {"nickname": "x" * 31},
        {"timezone": "Mars/Olympus"},
        {"unknown": True},
    ):
        try:
            PlatformSettingsPatch(**payload)
        except ValueError:
            pass
        else:
            raise AssertionError(f"应拒绝设置: {payload}")


def test_settings_and_atomic_rollback(cloud):
    user, email = register(cloud)
    timed = create(cloud, due_date="2026-09-20", due_time="18:00")
    completed = cloud.patch(
        "/api/todos/" + create(cloud, due_date="2026-09-21", due_time="12:00")["id"],
        json={"status": "completed"},
    ).json()
    assert cloud.patch("/api/platform/settings", json={}).status_code == 422
    assert (
        cloud.patch("/api/platform/settings", json={"timezone": "Bad/Zone"}).status_code
        == 422
    )
    changed = cloud.patch(
        "/api/platform/settings",
        json={
            "nickname": "小赵",
            "timezone": "Asia/Shanghai",
        },
    ).json()
    assert changed["id"] == user["id"]
    assert changed["nickname"] == "小赵"
    assert cloud.get("/api/auth/me").json()["nickname"] == "小赵"
    assert changed["timezone"] == "Asia/Shanghai"
    assert changed["has_todos"]
    assert cloud.get("/api/todos/" + timed["id"]).json()["due_at"] == (
        "2026-09-20T10:00:00Z"
    )
    unchanged = cloud.get("/api/todos/" + completed["id"]).json()
    assert unchanged["timezone"] == "Asia/Shanghai"
    assert unchanged["due_at"] == "2026-09-21T04:00:00Z"
    assert unchanged["completed_at"] == completed["completed_at"]
    assert unchanged["updated_at"] == completed["updated_at"]

    with Session(engine) as db:
        original_commit = db.commit
        original_rollback = db.rollback
        db.commit = Mock(side_effect=SQLAlchemyError("forced"))
        db.rollback = Mock(wraps=original_rollback)
        app.dependency_overrides[get_session] = lambda: db
        response = cloud.patch("/api/platform/settings", json={"nickname": "不应保存"})
        assert response.status_code == 503
        assert db.rollback.called
        db.commit = original_commit
    app.dependency_overrides.clear()
    with Session(engine) as db:
        stored = db.scalar(select(User).where(User.email == email))
        todo = db.get(Todo, UUID(timed["id"]))
        assert stored.nickname == "小赵"
        assert todo.timezone == "Asia/Shanghai"


def test_home_exact_counts_order_and_account_isolation(cloud, monkeypatch):
    register(cloud)
    now = datetime(2026, 9, 16, 12, tzinfo=UTC)
    monkeypatch.setattr(platform, "utcnow", lambda: now)
    today_overdue = create(
        cloud, title="今日已逾期", due_date="2026-09-16", due_time="07:00"
    )
    create(cloud, title="今日稍后", due_date="2026-09-16", due_time="23:00")
    create(cloud, title="昨日日期", due_date="2026-09-15")
    completed = create(cloud, title="已完成", due_date="2026-09-16", due_time="06:00")
    cloud.patch("/api/todos/" + completed["id"], json={"status": "completed"})

    other = TestClient(app, headers=HEADERS)
    register(other)
    create(other, title="其他账号", due_date="2026-09-16", due_time="06:00")
    home = cloud.get("/api/platform/home").json()
    assert home["timezone"] == "Asia/Shanghai"
    assert home["server_time"] == "2026-09-16T12:00:00Z"
    assert home["today"]["count"] == 2
    assert home["overdue"]["count"] == 2
    assert today_overdue["id"] in {item["id"] for item in home["today"]["items"]}
    assert all(item["title"] != "其他账号" for item in home["recent"])
    assert len(home["recent"]) == 4
    other.close()


def test_platform_requires_login():
    with TestClient(app, headers=HEADERS) as client:
        assert client.get("/api/platform/home").status_code == 401
        assert client.get("/api/platform/settings").status_code == 401
