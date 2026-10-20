"""Run with RUN_INTEGRATION=1 POSTGRES_DB=ai_agent_test; cloud services only."""

from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from backend.api.routes.auth import change_password
from backend.api.schemas import PasswordChange, TodoCreate, TodoPatch
from backend.app import app
from backend.core import security as auth
from backend.db.models import User

HEADERS = {"Origin": "http://localhost:5173", "X-App-Request": "1"}
PASSWORD = "合法测试密码12345678"


from helpers import create, register


def test_input_boundaries():
    with pytest.raises(ValueError):
        PasswordChange(
            current_password=PASSWORD, new_password=PASSWORD, confirm_password=PASSWORD
        )
    with pytest.raises(ValueError):
        PasswordChange(
            current_password=PASSWORD,
            new_password="新密码abcdefghijkl",
            confirm_password="不同密码abcdefghijkl",
        )
    assert TodoCreate(title=" 🐈 ", description="").title == "🐈"
    for body in (
        {"title": " "},
        {"title": "🐈" * 101},
        {"title": "x", "due_time": "18:00"},
        {"title": "x", "due_date": 1000},
    ):
        with pytest.raises(ValueError):
            TodoCreate(**body)
    for body in (
        {},
        {"title": None},
        {"status": None},
        {"due_date": None, "due_time": "18:00"},
        {"owner_id": str(uuid4())},
    ):
        with pytest.raises(ValueError):
            TodoPatch(**body)


def test_change_password_revokes_existing_sessions(cloud):
    _, email = register(cloud)
    other = TestClient(app, headers=HEADERS)
    assert (
        other.post(
            "/api/auth/login", json={"email": email, "password": PASSWORD}
        ).status_code
        == 200
    )
    old_cookie = cloud.cookies.get("session")
    new_password = "新的合法测试密码12345678"
    path = "/api/auth/password"
    assert (
        cloud.post(
            path,
            json={
                "current_password": "错误原密码12345678",
                "new_password": new_password,
                "confirm_password": new_password,
            },
        ).status_code
        == 400
    )
    assert cloud.get("/api/auth/me").status_code == 200
    assert (
        cloud.post(
            path,
            json={
                "current_password": PASSWORD,
                "new_password": new_password,
                "confirm_password": new_password,
            },
        ).status_code
        == 204
    )
    assert cloud.cookies.get("session") == old_cookie
    assert cloud.get("/api/auth/me").status_code == 401
    assert other.get("/api/auth/me").status_code == 401
    assert (
        cloud.post(
            "/api/auth/login", json={"email": email, "password": PASSWORD}
        ).status_code
        == 401
    )
    assert (
        cloud.post(
            "/api/auth/login", json={"email": email, "password": new_password}
        ).status_code
        == 200
    )


def test_change_password_hash_and_version():
    account = User(id=uuid4(), email="account@example.com", active=True, auth_version=0)
    account.password_hash = auth.password_hasher.hash(PASSWORD)
    session = Mock()
    session.scalar.return_value = account
    store = Mock()
    store.eval.return_value = 0
    new_password = "新的合法测试密码12345678"
    change_password(
        PasswordChange(
            current_password=PASSWORD,
            new_password=new_password,
            confirm_password=new_password,
        ),
        Request({"type": "http", "client": ("127.0.0.1", 1234), "headers": []}),
        account,
        session,
        store,
    )
    assert auth.password_hasher.verify(account.password_hash, new_password)
    assert account.auth_version == 1
    session.commit.assert_called_once()


def test_auth_and_isolation(cloud):
    a, email = register(cloud)
    cookie = cloud.cookies.get("session")
    assert cloud.get("/api/auth/me").json() == a
    item = create(cloud)
    assert cloud.get("/api/todos").json()["items"][0]["id"] == item["id"]
    fail = cloud.post(
        "/api/auth/login", json={"email": email, "password": "wrong-password123"}
    )
    unknown = cloud.post(
        "/api/auth/login",
        json={
            "email": "unknown@integration.example.com",
            "password": "wrong-password123",
        },
    )
    assert fail.json() == unknown.json() and fail.status_code == 401
    assert cloud.cookies.get("session") == cookie
    other = TestClient(app, headers=HEADERS)
    register(other)
    assert other.get("/api/todos/" + item["id"]).status_code == 404
    assert (
        other.patch(
            "/api/todos/" + item["id"], json={"status": "completed"}
        ).status_code
        == 404
    )
    assert other.get("/api/todos", params={"owner_id": a["id"]}).status_code == 422
    assert (
        other.post(
            "/api/todos",
            headers={"Idempotency-Key": str(uuid4())},
            json={"title": "x", "owner_id": a["id"]},
        ).status_code
        == 422
    )
    login = cloud.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert (
        login.status_code == 200
        and "HttpOnly" in login.headers["set-cookie"]
        and "SameSite=lax" in login.headers["set-cookie"]
    )
    assert cloud.cookies.get("session") != cookie
    assert (
        TestClient(app)
        .get("/api/auth/me", headers={"Cookie": "session=" + cookie})
        .status_code
        == 401
    )
    assert cloud.post("/api/auth/logout").status_code == 204
    assert cloud.get("/api/todos").status_code == 401
    assert cloud.post("/api/auth/logout").status_code == 204
    assert other.get("/api/auth/me").status_code == 200
    for verb, path, kwargs in [
        ("get", "/api/todos", {}),
        ("get", "/api/todos/" + item["id"], {}),
        (
            "post",
            "/api/todos",
            {"json": {"title": "x"}, "headers": {"Idempotency-Key": str(uuid4())}},
        ),
        ("patch", "/api/todos/" + item["id"], {"json": {"status": "completed"}}),
    ]:
        assert getattr(cloud, verb)(path, **kwargs).status_code == 401
    other.close()


def test_protection_and_rate_limit(cloud):
    payload = {"email": "bad", "password": "super-secret", "confirm_password": "other"}
    result = cloud.post("/api/auth/register", json=payload)
    assert result.status_code == 422 and "super-secret" not in result.text
    for headers in (
        {"Origin": "https://evil.test"},
        {"X-App-Request": ""},
        {"Origin": ""},
    ):
        assert (
            cloud.post("/api/auth/register", json=payload, headers=headers).status_code
            == 403
        )
    assert (
        cloud.post(
            "/api/auth/login", content="{}", headers={"Content-Type": "text/plain"}
        ).status_code
        == 415
    )
    email = "missing@integration.example.com"
    for i in range(10):
        assert (
            cloud.post(
                "/api/auth/login",
                json={"email": email, "password": PASSWORD},
                headers={"X-Forwarded-For": f"10.0.0.{i}"},
            ).status_code
            == 401
        )
    result = cloud.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert result.status_code == 429 and int(result.headers["Retry-After"]) > 0
    for key in auth.redis.scan_iter(match=auth.settings.redis_namespace + "login:*"):
        auth.redis.expire(key, 0)
    assert (
        cloud.post(
            "/api/auth/login", json={"email": email, "password": PASSWORD}
        ).status_code
        == 401
    )


def test_openapi_security_and_unexpected_error_redaction():
    schema = app.openapi()
    assert schema["components"]["securitySchemes"]["SessionCookie"]["name"] == "session"
    operation = schema["paths"]["/api/todos"]["post"]
    assert operation["security"] == [{"SessionCookie": []}]
    assert {"Origin", "X-App-Request", "Idempotency-Key"} <= {
        p["name"] for p in operation["parameters"]
    }
    fake = Mock()
    fake.get.side_effect = RuntimeError("must-not-leak-sensitive-input")
    app.dependency_overrides[auth.get_redis] = lambda: fake
    try:
        with TestClient(app) as client:
            response = client.get("/api/auth/me", headers={"Cookie": "session=fake"})
            assert response.status_code == 500
            assert "must-not-leak" not in response.text
    finally:
        app.dependency_overrides.clear()
