from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from backend.api.schemas import AssistantReply
from backend.features.assistant import replies


@pytest.mark.parametrize("kind", ["result", "confirm", "success", "clarify"])
def test_personalization_preserves_business_reply(monkeypatch, kind):
    captured = []

    def create(**kwargs):
        captured.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content='{"prefix":"爹，"}'))
            ]
        )

    monkeypatch.setattr(replies.settings, "llm_api_key", SecretStr("test-key"))
    monkeypatch.setattr(
        replies,
        "OpenAI",
        lambda **kwargs: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        ),
    )
    original = AssistantReply(
        kind=kind, message="后端原始结果", action_token="test-token"
    )
    result = replies.personalize(original, "爹", ["我是程序员"])
    assert result.message == "爹，后端原始结果"
    assert result.model_dump(exclude={"message"}) == original.model_dump(
        exclude={"message"}
    )
    assert original.message == "后端原始结果"
    assert "我是程序员" in captured[0]["messages"][1]["content"]


def test_invalid_model_output_falls_back(monkeypatch):
    monkeypatch.setattr(replies.settings, "llm_api_key", SecretStr("test-key"))
    monkeypatch.setattr(
        replies,
        "OpenAI",
        lambda **kwargs: SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **kwargs: SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                message=SimpleNamespace(
                                    content='{"prefix":"已创建成功"}'
                                )
                            )
                        ]
                    )
                )
            )
        ),
    )
    original = AssistantReply(kind="confirm", message="确认创建吗？")
    assert replies.personalize(original, "爹", []) is original
