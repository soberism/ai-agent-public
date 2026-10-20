"""HTTP账号并发约束与云端Redis原子额度，使用专用测试库。"""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from helpers import register
from pydantic import ValidationError

from backend.core.config import Settings
from backend.core.security import APIError, redis, settings
from backend.features.assistant import agent_celery, index_queue, request_limits
from backend.features.assistant.agent_celery import reindex_materials_task, run_task


def test_limits_cannot_be_unbounded():
    for field in (
        "ai_chat_per_minute",
        "ai_chat_per_day",
        "ai_transcription_per_minute",
        "ai_reindex_per_day",
        "ai_max_active_runs",
    ):
        with pytest.raises(ValidationError):
            Settings(**{field: 0})


def test_atomic_limits_do_not_charge_rejected_requests(cloud, monkeypatch):
    monkeypatch.setattr(settings, "ai_chat_per_minute", 5)
    owner = uuid4()

    def attempt(_):
        try:
            request_limits.charge(owner, "chat")
            return True
        except APIError as error:
            assert error.status == 429 and int(error.headers["Retry-After"]) > 0
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(attempt, range(20))) == 5
    prefix = f"{settings.redis_namespace}ai-quota:{owner}:chat:"
    assert redis.get(prefix + "minute") == redis.get(prefix + "day") == "5"
    request_limits.charge(uuid4(), "chat")
    redis.delete(prefix + "minute")
    monkeypatch.setattr(settings, "ai_chat_per_day", 5)
    assert not attempt(None)


def test_concurrent_http_posts_enqueue_one_run_and_cancel_releases_capacity(
    cloud, monkeypatch
):
    register(cloud)
    thread = cloud.post("/api/assistant/threads", json={"fresh": True}).json()[
        "thread_id"
    ]
    queued = []
    monkeypatch.setattr(run_task, "delay", lambda *args: queued.append(args))

    def submit(_):
        return cloud.post(
            "/api/agent/runs", json={"thread_id": thread, "prompt": "你好"}
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(submit, range(2)))
    assert sorted(r.status_code for r in replies) == [202, 409]
    assert len(queued) == 1
    accepted = next(r.json() for r in replies if r.status_code == 202)
    rejected = next(r.json() for r in replies if r.status_code == 409)
    assert rejected["error"]["code"] == "AI_BUSY"
    assert (
        cloud.post(f"/api/agent/runs/{accepted['id']}/cancel", json={}).status_code
        == 200
    )
    assert submit(None).status_code == 202 and len(queued) == 2


def test_reindex_deduplicates_and_worker_releases_only_its_lease(cloud, monkeypatch):
    account, _ = register(cloud)
    owner = account["id"]
    queued, executed = [], []
    monkeypatch.setattr(
        reindex_materials_task, "delay", lambda *args: queued.append(args)
    )
    monkeypatch.setattr(
        agent_celery, "execute_reindex", lambda owner_id: executed.append(owner_id)
    )
    assert cloud.post("/api/agent/runs/knowledge/reindex", json={}).status_code == 202
    assert cloud.post("/api/agent/runs/knowledge/reindex", json={}).status_code == 409
    assert len(queued) == 1
    index_queue.release(owner, "stale-token")
    assert redis.get(index_queue.key(owner)) == queued[0][1]
    reindex_materials_task.run(*queued[0])
    assert executed == [owner] and redis.get(index_queue.key(owner)) is None
    assert cloud.post("/api/agent/runs/knowledge/reindex", json={}).status_code == 429
    assert redis.get(index_queue.key(owner)) is None


def test_transcription_quota_stops_before_model_call(cloud, monkeypatch):
    from pydantic import SecretStr

    from backend.api.routes import assistant_preferences

    register(cloud)
    calls = []
    monkeypatch.setattr(settings, "ai_transcription_per_minute", 2)
    monkeypatch.setattr(settings, "transcription_api_key", SecretStr("synthetic"))
    monkeypatch.setattr(settings, "transcription_model", "synthetic")
    monkeypatch.setattr(
        assistant_preferences, "recognize", lambda *_: calls.append(True) or "测试转写"
    )
    body = {"audio_base64": "dGVzdA==", "mime_type": "audio/webm"}
    assert [
        cloud.post("/api/assistant/transcriptions", json=body).status_code
        for _ in range(3)
    ] == [200, 200, 429]
    assert len(calls) == 2


def test_quota_storage_failure_does_not_enqueue(cloud, monkeypatch):
    from unittest.mock import Mock

    from redis.exceptions import RedisError

    register(cloud)
    thread = cloud.post("/api/assistant/threads", json={"fresh": True}).json()[
        "thread_id"
    ]
    unavailable = Mock()
    unavailable.eval.side_effect = RedisError("synthetic")
    queued = []
    monkeypatch.setattr(request_limits, "redis", unavailable)
    monkeypatch.setattr(run_task, "delay", lambda *args: queued.append(args))
    response = cloud.post(
        "/api/agent/runs", json={"thread_id": thread, "prompt": "你好"}
    )
    assert response.status_code == 503 and not queued


def test_legacy_model_request_holds_account_admission_lock(cloud, monkeypatch):
    from threading import Event

    from backend.api.routes import assistant
    from backend.features.assistant.graph import Intent

    register(cloud)
    thread = cloud.post("/api/assistant/threads", json={"fresh": True}).json()[
        "thread_id"
    ]
    started, release = Event(), Event()
    queued = []

    def model(*_):
        started.set()
        assert release.wait(5)
        return Intent(action="respond", message="synthetic")

    monkeypatch.setattr(assistant, "interpret", model)
    monkeypatch.setattr(run_task, "delay", lambda *args: queued.append(args))
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(
            cloud.post,
            "/api/assistant/messages",
            json={"thread_id": thread, "message": "你好"},
        )
        try:
            assert started.wait(5)
            second = cloud.post(
                "/api/agent/runs", json={"thread_id": thread, "prompt": "你好"}
            )
            assert second.status_code == 409
            assert second.json()["error"]["code"] == "AI_BUSY"
            assert not queued
        finally:
            release.set()
        assert first.result(timeout=5).status_code == 200
