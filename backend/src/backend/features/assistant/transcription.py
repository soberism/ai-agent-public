import base64
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from openai import OpenAI

from backend.core.security import APIError


def recognize(audio, settings):
    with TemporaryDirectory(prefix="asr-") as directory:
        source = Path(directory) / "recording"
        target = Path(directory) / "recording.wav"
        source.write_bytes(audio)
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-v",
                    "error",
                    "-y",
                    "-i",
                    str(source),
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    str(target),
                ],
                check=True,
                capture_output=True,
                timeout=15,
            )
        except FileNotFoundError:
            raise APIError(
                503, "VOICE_TRANSCRIPTION_UNAVAILABLE", "语音转写需要安装 FFmpeg"
            ) from None
        except subprocess.CalledProcessError:
            raise APIError(422, "INVALID_AUDIO", "录音格式无效，请重新录制") from None
        except subprocess.TimeoutExpired:
            raise APIError(
                503, "VOICE_TRANSCRIPTION_FAILED", "录音处理超时，请缩短录音后重试"
            ) from None
        data = base64.b64encode(target.read_bytes()).decode("ascii")
    result = OpenAI(
        api_key=settings.transcription_api_key.get_secret_value(),
        base_url=settings.transcription_base_url,
        max_retries=0,
    ).chat.completions.create(
        model=settings.transcription_model,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": f"data:audio/wav;base64,{data}",
                        },
                    }
                ],
            }
        ],
        extra_body={"asr_options": {"enable_itn": True}},
        timeout=25,
    )
    return (result.choices[0].message.content or "").strip() if result.choices else ""
