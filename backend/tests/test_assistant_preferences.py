from fastapi.testclient import TestClient
from helpers import HEADERS, register

from backend.api.routes import assistant
from backend.app import app
from backend.features.assistant import graph
from backend.features.assistant.preferences import sensitive


def test_sensitive_memory_detection():
    assert sensitive("我的银行卡是 6222 0000 0000 0000")
    assert sensitive("身份证 11010119900101123X")
    assert sensitive("access token: private-value")
    assert not sensitive("我喜欢周末早上跑步")


def test_preferences_memory_isolation_context_and_voice_failure(cloud, monkeypatch):
    register(cloud)
    assert cloud.get("/api/assistant/preferences").json() == {
        "custom_instructions": "",
        "memory_enabled": True,
        "updated_at": None,
    }
    saved = cloud.patch(
        "/api/assistant/preferences",
        json={"custom_instructions": "请称呼我为小周", "memory_enabled": True},
    )
    assert saved.status_code == 200

    memory = cloud.post("/api/assistant/memories", json={"content": "我周末习惯晨跑"})
    assert memory.status_code == 201
    memory_id = memory.json()["id"]
    assert memory.json()["source"] == "user"

    captured = []

    def fake_interpret(*args):
        captured.append(args)
        return graph.Intent(action="respond", message="收到")

    monkeypatch.setattr(assistant, "interpret", fake_interpret)
    thread_id = cloud.post("/api/assistant/threads", json={}).json()["thread_id"]
    reply = cloud.post(
        "/api/assistant/messages", json={"thread_id": thread_id, "message": "你好"}
    )
    assert reply.status_code == 200
    assert captured[-1][3:5] == ("请称呼我为小周", ["我周末习惯晨跑"])

    assert (
        cloud.post(
            "/api/assistant/memories", json={"content": "银行卡 6222000000000000"}
        ).json()["error"]["code"]
        == "SENSITIVE_MEMORY_REJECTED"
    )

    other = TestClient(app, headers=HEADERS)
    register(other)
    assert (
        other.patch(
            f"/api/assistant/memories/{memory_id}", json={"enabled": False}
        ).status_code
        == 404
    )
    other.close()

    updated = cloud.patch(
        f"/api/assistant/memories/{memory_id}",
        json={"content": "我周日上午习惯晨跑", "enabled": False},
    )
    assert updated.status_code == 200
    assert updated.json()["enabled"] is False
    assert len(cloud.get("/api/assistant/memories").json()) == 1

    cloud.patch("/api/assistant/preferences", json={"memory_enabled": False})
    cloud.post(
        "/api/assistant/messages", json={"thread_id": thread_id, "message": "还在吗"}
    )
    assert captured[-1][4] == []

    from pydantic import SecretStr

    from backend.core.security import settings

    monkeypatch.setattr(settings, "transcription_api_key", SecretStr(""))
    transcription = cloud.post(
        "/api/assistant/transcriptions",
        json={"audio_base64": "dGVzdA==", "mime_type": "audio/webm"},
    )
    assert transcription.status_code == 503
    assert transcription.json()["error"]["code"] == "VOICE_TRANSCRIPTION_UNAVAILABLE"

    assert (
        cloud.request(
            "DELETE", f"/api/assistant/memories/{memory_id}", json={}
        ).status_code
        == 204
    )
    assert cloud.get("/api/assistant/memories").json() == []
