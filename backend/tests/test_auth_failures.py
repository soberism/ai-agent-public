"""Run with RUN_INTEGRATION=1 POSTGRES_DB=ai_agent_test; cloud services only."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

from redis.exceptions import ConnectionError, ResponseError
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app import app
from backend.core import security as auth
from backend.db.models import User
from backend.db.session import engine, get_session

HEADERS = {"Origin": "http://localhost:5173", "X-App-Request": "1"}
PASSWORD = "合法测试密码12345678"


from helpers import register, request_code


def test_failure_paths_and_partial_signup(cloud, monkeypatch):
    register(cloud)
    fake = Mock()
    fake.get.side_effect = ConnectionError("secret")
    fake.eval.side_effect = ConnectionError("secret")
    fake.delete.side_effect = ConnectionError("secret")
    app.dependency_overrides[auth.get_redis] = lambda: fake
    assert cloud.get("/api/todos").status_code == 503
    assert (
        cloud.post("/api/auth/logout").json()["error"]["message"] == "退出失败，请重试"
    )
    app.dependency_overrides.clear()
    from backend.api.routes import auth as auth_routes

    monkeypatch.setattr(
        auth_routes, "establish_session", Mock(side_effect=ResponseError("OOM secret"))
    )
    email = uuid4().hex + "@integration.example.com"
    result = cloud.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "confirm_password": PASSWORD,
            "verification_code": request_code(cloud, email),
        },
    )
    assert (
        result.status_code == 503
        and result.json()["error"]["code"] == "ACCOUNT_CREATED_LOGIN_REQUIRED"
    )
    monkeypatch.setattr(auth_routes, "establish_session", auth.establish_session)
    assert "secret" not in result.text
    app.dependency_overrides.clear()
    assert (
        cloud.post(
            "/api/auth/login", json={"email": email, "password": PASSWORD}
        ).status_code
        == 200
    )
    token = cloud.cookies.get("session")
    auth.redis.delete(auth.session_key(token))
    assert cloud.get("/api/todos").status_code == 401


def test_concurrent_signup_session_expiry_and_storage_failures(cloud, monkeypatch):
    email = uuid4().hex + "@integration.example.com"
    payload = {
        "email": email,
        "password": PASSWORD,
        "confirm_password": PASSWORD,
        "verification_code": request_code(cloud, email),
    }
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: cloud.post("/api/auth/register", json=payload), range(2)
            )
        )
    assert sorted(r.status_code for r in results) == [201, 422]
    token = cloud.cookies.get("session")
    key = auth.session_key(token)
    ttl = auth.redis.ttl(key)
    assert 604790 <= ttl <= 604800
    cloud.get("/api/auth/me")
    assert auth.redis.ttl(key) <= ttl
    raw = auth.redis.get(key)
    import json

    value = json.loads(raw)
    value["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    auth.redis.set(key, json.dumps(value), ex=10)
    assert cloud.get("/api/todos").status_code == 401
    auth.redis.set(key, raw, ex=604800)
    with Session(engine) as db:
        user = db.scalar(select(User).where(User.email == email))
        assert (
            user.password_hash.startswith("$argon2id$")
            and PASSWORD not in user.password_hash
        )
    fake_db = Mock()
    from sqlalchemy.exc import OperationalError

    fake_db.get.side_effect = OperationalError("query", {}, Exception("secret"))
    app.dependency_overrides[get_session] = lambda: fake_db
    result = cloud.get("/api/todos")
    assert result.status_code == 503 and "secret" not in result.text
    app.dependency_overrides.clear()
    fake = Mock()
    fake.eval.side_effect = [0, ResponseError("OOM")]
    app.dependency_overrides[auth.get_redis] = lambda: fake
    assert (
        cloud.post(
            "/api/auth/login", json={"email": email, "password": PASSWORD}
        ).status_code
        == 503
    )
    app.dependency_overrides.clear()
    assert auth.redis.exists(key)  # failed rotation retained old session
