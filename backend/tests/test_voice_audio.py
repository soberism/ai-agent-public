import base64
from uuid import uuid4

import pytest
from helpers import register

from backend.api.hub_schemas import VoiceMemoAudioCreate
from backend.api.routes.voice_memos import decode_audio
from backend.core.security import APIError

AUDIO = b"\x1a\x45\xdf\xa3" + b"test recording"


def test_audio_validation():
    body = VoiceMemoAudioCreate(
        upload_id=uuid4(),
        audio_base64=base64.b64encode(AUDIO).decode(),
        mime_type="audio/webm",
    )
    assert decode_audio(body) == AUDIO
    for encoded in (
        "invalid!",
        base64.b64encode(b"not audio").decode(),
        base64.b64encode(b"\x1a\x45\xdf\xa3" + b"x" * (8 * 1024 * 1024)).decode(),
    ):
        with pytest.raises(APIError):
            decode_audio(
                VoiceMemoAudioCreate(
                    upload_id=uuid4(), audio_base64=encoded, mime_type="audio/webm"
                )
            )


def test_recording_storage_playback_isolation_and_delete(cloud, monkeypatch):
    from backend.api.assistant_preferences_schemas import TranscriptionOut
    from backend.api.routes import assistant_preferences

    register(cloud)
    body = {
        "upload_id": str(uuid4()),
        "audio_base64": base64.b64encode(AUDIO).decode(),
        "mime_type": "audio/webm",
    }
    response = cloud.post("/api/assistant/voice-memos/audio", json=body)
    assert response.status_code == 201
    memo = response.json()
    assert memo["transcript"] == ""
    found = cloud.get("/api/hub/search", params={"q": "录音"}).json()["items"]
    assert any(
        item["id"] == memo["id"] and item["url"].endswith(memo["id"]) for item in found
    )
    assert (
        cloud.post("/api/assistant/voice-memos/audio", json=body).json()["id"]
        == memo["id"]
    )
    assert "audio_base64" not in memo
    playback = cloud.get(memo["audio_url"])
    assert playback.content == AUDIO
    partial = cloud.get(memo["audio_url"], headers={"Range": "bytes=2-5"})
    assert partial.status_code == 206 and partial.content == AUDIO[2:6]
    assert (
        cloud.get(memo["audio_url"], headers={"Range": "bytes=999-"}).status_code == 416
    )
    assert "no-store" in playback.headers["cache-control"]
    assert (
        cloud.post(
            f"/api/assistant/voice-memos/{memo['id']}/convert",
            json={"target_type": "todo", "title": "事项"},
        ).status_code
        == 422
    )
    monkeypatch.setattr(
        assistant_preferences,
        "transcribe",
        lambda body, user: TranscriptionOut(transcript="明天整理行李"),
    )
    assert (
        cloud.post(
            f"/api/assistant/voice-memos/{memo['id']}/transcribe", json={}
        ).json()["transcript"]
        == "明天整理行李"
    )
    cookies = dict(cloud.cookies)
    cloud.cookies.clear()
    register(cloud)
    for method, path in (
        ("get", memo["audio_url"]),
        ("post", f"/api/assistant/voice-memos/{memo['id']}/transcribe"),
        ("delete", f"/api/assistant/voice-memos/{memo['id']}"),
    ):
        assert (
            getattr(cloud, method)(
                path, headers={"Content-Type": "application/json"}
            ).status_code
            == 404
        )
    cloud.cookies.clear()
    cloud.cookies.update(cookies)
    assert cloud.delete(f"/api/assistant/voice-memos/{memo['id']}").status_code == 204
    assert cloud.get(memo["audio_url"]).status_code == 404
