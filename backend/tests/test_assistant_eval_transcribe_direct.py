"""A synthetic spoken memo exercises real audio transcription through Agent Run."""

import base64
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import pytest
from test_assistant_eval_live import action_tools, cases, isolated_api, replay

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_MODEL") != "1", reason="显式启用真实模型"
)
DIRECT = next(
    case for case in cases.values() if case.get("target_tool") == "transcribe_memo"
)


def test_direct_transcribe_memo(cloud, monkeypatch):
    api = isolated_api(cloud, monkeypatch)
    with TemporaryDirectory(prefix="assistant-eval-audio-") as directory:
        source = Path(directory) / "speech.aiff"
        target = Path(directory) / "speech.ogg"
        subprocess.run(
            ["say", "-v", "Tingting", "-o", str(source), "今天下午检查会议室窗户"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-i",
                str(source),
                "-c:a",
                "libopus",
                str(target),
            ],
            check=True,
            capture_output=True,
        )
        response = cloud.post(
            "/api/assistant/voice-memos/audio",
            json={
                "upload_id": str(uuid4()),
                "audio_base64": base64.b64encode(target.read_bytes()).decode(),
                "mime_type": "audio/ogg",
            },
        )
    assert response.status_code == 201, response.text
    memo_id = response.json()["id"]
    assert response.json()["transcript"] == ""
    result = replay(api, DIRECT, 60, True)
    assert all(step["result"] == "review" for step in result["steps"]), result
    assert action_tools(result["steps"][0]["actual"]["run_id"]) == ["transcribe_memo"]
    memo = next(
        item
        for item in cloud.get("/api/assistant/voice-memos").json()
        if item["id"] == memo_id
    )
    assert "窗户" in memo["transcript"]
    print("transcribe_memo: synthetic audio transcribed")
