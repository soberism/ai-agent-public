import os
from unittest.mock import Mock

if os.environ.get("RUN_INTEGRATION") != "1":
    for key in ("POSTGRES_PASSWORD", "REDIS_PASSWORD", "RABBITMQ_PASSWORD"):
        os.environ.setdefault(key, "test-only")
    os.environ.setdefault("CURSOR_SECRET", "test-only-cursor-secret-32-characters")

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from backend.app import app
from backend.core.config import Settings
from backend.db.session import get_session


def test_health_and_database_readiness():
    session = Mock()
    app.dependency_overrides[get_session] = lambda: session
    try:
        with TestClient(app) as client:
            assert client.get("/health").json() == {"status": "ok"}
            assert client.get("/ready").json() == {"status": "ok", "database": "ok"}
            session.execute.side_effect = OperationalError(
                "SELECT 1", {}, Exception("secret")
            )
            result = client.get("/ready")
            assert result.status_code == 503
            assert result.json() == {"detail": "数据库暂不可用"}
            assert client.get("/health").status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_password_special_characters():
    settings = Settings(
        _env_file=None,
        postgres_password="p@ss:/%word",
        redis_password="test-only",
        rabbitmq_password="test-only",
        cursor_secret="test-only-cursor-secret-32-characters",
    )
    assert settings.database_url.password == "p@ss:/%word"
    assert "p@ss" not in repr(settings)
