import smtplib
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
from uuid import uuid4

import pytest
from helpers import MAILBOX, PASSWORD, register, request_code
from pydantic import SecretStr
from sqlalchemy.exc import OperationalError

from backend.app import app
from backend.core import security as auth
from backend.db.session import get_session
from backend.features.auth import verification as codes


def address():
    return uuid4().hex + "@integration.example.com"


def payload(email, code):
    return {
        "email": email,
        "password": PASSWORD,
        "confirm_password": PASSWORD,
        "verification_code": code,
    }


def test_code_required_and_no_secret_echo(cloud):
    email = address()
    for code in (None, 123456, "12345", "１２３４５６", "1234567", "123456\n"):
        result = cloud.post("/api/auth/register", json=payload(email, code))
        assert result.status_code == 422
        assert PASSWORD not in result.text
    result = cloud.post("/api/auth/register/code", json={"email": "bad"})
    assert result.status_code == 422
    result = cloud.post(
        "/api/auth/register/code", json={"email": email}, headers={"Origin": ""}
    )
    assert result.status_code == 403


def test_single_use_wrong_email_exhaustion_and_expiry(cloud):
    email = address()
    code = request_code(cloud, email)
    key = codes.keys(email, "")[0]
    record = auth.redis.hgetall(key)
    assert code not in record.values() and email not in key
    assert 590 <= auth.redis.ttl(key) <= 600
    assert (
        cloud.post("/api/auth/register", json=payload(address(), code)).status_code
        == 422
    )
    wrong = "000000" if code != "000000" else "000001"
    for _ in range(5):
        result = cloud.post("/api/auth/register", json=payload(email, wrong))
        assert result.json()["error"]["code"] == "INVALID_VERIFICATION_CODE"
    assert not auth.redis.exists(key)
    assert (
        cloud.post("/api/auth/register", json=payload(email, code)).status_code == 422
    )
    email = address()
    code = request_code(cloud, email)
    auth.redis.expire(codes.keys(email, "")[0], 0)
    assert (
        cloud.post("/api/auth/register", json=payload(email, code)).status_code == 422
    )


def test_resend_concurrency_quota_and_existing_email(cloud):
    email = address()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: cloud.post("/api/auth/register/code", json={"email": email}),
                range(2),
            )
        )
    assert sorted(r.status_code for r in results) == [200, 429]
    old_nonce = auth.redis.hget(codes.keys(email, "")[0], "nonce")
    for _ in range(4):
        auth.redis.delete(codes.keys(email, "")[1])
        request_code(cloud, email)
    auth.redis.delete(codes.keys(email, "")[1])
    result = cloud.post("/api/auth/register/code", json={"email": email})
    assert result.status_code == 429 and int(result.headers["Retry-After"]) > 60
    key = codes.keys(email, "")[0]
    assert auth.redis.eval(codes.FINISH, 1, key, old_nonce, "delete") == 0
    assert auth.redis.eval(codes.FINISH, 1, key, old_nonce, "active") == 0
    assert auth.redis.exists(key)
    _, existing = register(cloud)
    auth.redis.delete(codes.keys(existing, "")[1])
    code = request_code(cloud, existing)
    assert (
        cloud.post("/api/auth/register", json=payload(existing, code)).status_code
        == 409
    )
    for _ in range(13):
        request_code(cloud, address())
    assert (
        cloud.post("/api/auth/register/code", json={"email": address()}).status_code
        == 429
    )


def test_smtp_failure_pending_and_missing_config(cloud, monkeypatch):
    email = address()
    observed = []

    def failure(mailbox, code):
        result = cloud.post("/api/auth/register", json=payload(mailbox, code))
        observed.append(result.status_code)
        raise smtplib.SMTPException("private-credential")

    monkeypatch.setattr(codes, "send_code", failure)
    result = cloud.post("/api/auth/register/code", json={"email": email})
    assert result.status_code == 503 and observed == [422]
    assert "private-credential" not in result.text
    assert not auth.redis.exists(codes.keys(email, "")[0])
    assert (
        cloud.post("/api/auth/register/code", json={"email": email}).status_code == 429
    )
    monkeypatch.setattr(auth.settings, "email_verification_secret", SecretStr(""))
    assert (
        cloud.post("/api/auth/register/code", json={"email": address()}).status_code
        == 503
    )


def test_consumed_code_database_failure(cloud):
    email = address()
    code = request_code(cloud, email)
    fake = Mock()
    fake.commit.side_effect = OperationalError("query", {}, Exception("secret"))
    app.dependency_overrides[get_session] = lambda: fake
    result = cloud.post("/api/auth/register", json=payload(email, code))
    app.dependency_overrides.clear()
    assert result.status_code == 503
    assert result.json()["error"]["code"] == "REGISTRATION_FAILED"
    assert "secret" not in result.text
    assert (
        cloud.post("/api/auth/register", json=payload(email, code)).status_code == 422
    )


def test_subsecond_limits_remain_enforced(cloud):
    email = address()
    keyset = codes.keys(email, "testclient")
    for index, value in ((1, 1), (2, 5), (3, 20)):
        auth.redis.delete(*keyset)
        # PEXPIRE + Lua are pipelined to avoid adding client round-trip latency.
        pipe = auth.redis.pipeline()
        pipe.set(keyset[index], value, px=200)
        pipe.eval(codes.RESERVE, 4, *keyset, "nonce", "digest", 5, 20)
        assert pipe.execute()[1] == 1
        assert not auth.redis.exists(keyset[0])


@pytest.mark.parametrize("fail_activation", [False, True])
def test_redis_send_failure(cloud, fail_activation):
    from redis.exceptions import ConnectionError

    email = address()
    fake = Mock(wraps=auth.redis)
    real_eval = auth.redis.eval

    def evaluate(script, *args):
        if (
            (script == codes.FINISH and args[-1] == "active")
            if fail_activation
            else script == codes.RESERVE
        ):
            raise ConnectionError("private-secret")
        return real_eval(script, *args)

    fake.eval.side_effect = evaluate
    app.dependency_overrides[auth.get_redis] = lambda: fake
    response = cloud.post("/api/auth/register/code", json={"email": email})
    app.dependency_overrides.clear()
    assert response.status_code == 503 and "private-secret" not in response.text
    assert not auth.redis.exists(codes.keys(email, "")[0])


def test_old_code_after_resend(cloud, monkeypatch):
    email = address()
    monkeypatch.setattr(codes.secrets, "randbelow", Mock(side_effect=[123456, 654321]))
    old = request_code(cloud, email)
    auth.redis.delete(codes.keys(email, "")[1])
    request_code(cloud, email)
    response = cloud.post("/api/auth/register", json=payload(email, old))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_VERIFICATION_CODE"


def test_legacy_user_login_without_mail_configuration(cloud, monkeypatch):
    from sqlalchemy.orm import Session

    from backend.db.models import User
    from backend.db.session import engine

    email = address()
    MAILBOX[email] = None  # Track exactly this test's row for cleanup.
    with Session(engine) as session:
        session.add(
            User(email=email, password_hash=auth.password_hasher.hash(PASSWORD))
        )
        session.commit()
    monkeypatch.setattr(auth.settings, "email_verification_secret", SecretStr(""))
    monkeypatch.setattr(auth.settings, "smtp_host", "")
    response = cloud.post(
        "/api/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 200
