import base64
import io
import wave
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import SecretStr

from backend.core.security import APIError
from backend.features.assistant import transcription


def test_bailian_converts_audio_and_uses_independent_credentials(monkeypatch):
    audio = io.BytesIO()
    with wave.open(audio, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 1600)
    factory = Mock()
    factory.return_value.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=" 明天买牛奶 "))]
    )
    monkeypatch.setattr(transcription, "OpenAI", factory)
    settings = SimpleNamespace(
        transcription_api_key=SecretStr("test-only"),
        transcription_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        transcription_model="qwen3-asr-flash",
    )
    assert transcription.recognize(audio.getvalue(), settings) == "明天买牛奶"
    assert factory.call_args.kwargs["api_key"] == "test-only"
    request = factory.return_value.chat.completions.create.call_args.kwargs
    assert request["model"] == "qwen3-asr-flash"
    data = request["messages"][0]["content"][0]["input_audio"]["data"]
    assert data.startswith("data:audio/wav;base64,")
    with wave.open(io.BytesIO(base64.b64decode(data.split(",")[1]))) as wav:
        assert wav.getframerate() == 16000
        assert wav.getnchannels() == 1


def test_invalid_audio_is_rejected_before_calling_bailian(monkeypatch):
    factory = Mock()
    monkeypatch.setattr(transcription, "OpenAI", factory)
    with pytest.raises(APIError):
        transcription.recognize(b"not audio", None)
    factory.assert_not_called()
