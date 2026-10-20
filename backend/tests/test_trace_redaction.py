import copy
import json

import pytest
from pydantic import SecretStr

from backend.core import trace_redaction as redaction


def test_readable_content_and_structured_identities_are_redacted_without_mutation():
    original = {
        "messages": [
            {
                "role": "user",
                "content": "请邀请张三，邮箱 zhangsan@example.test，电话13800138000",
            }
        ],
        "person": {
            "name": "张三",
            "address": "示例省测试路1号",
            "owner_id": "private-owner",
        },
        "tools": [
            {"function": {"name": "invite_member", "parameters": {"type": "object"}}}
        ],
        "summary": "张三的邀请失败，接下来核对权限。",
    }
    saved = copy.deepcopy(original)
    safe = redaction.redact_payload(original)
    text = json.dumps(safe, ensure_ascii=False)
    for private in (
        "张三",
        "zhangsan@example.test",
        "13800138000",
        "测试路",
        "private-owner",
    ):
        assert private not in text
    assert "邀请失败，接下来核对权限" in text
    assert safe["tools"] == original["tools"]
    assert safe["person"]["name"] in safe["summary"]
    assert original == saved
    assert redaction.redact_payload(safe) == safe


@pytest.mark.parametrize(
    "private",
    [
        "test@example.test",
        "13800138000",
        "+86 13800138000",
        "+1 (415) 555-0100",
        "110101199001011234",
        "6222021234567890123",
        "sk-testsecret",
        "lsv2_pt_testsecret",
        "Bearer private-token",
        "密码：hunter2",
        "password=hunter2",
        "地址：示例省测试路1号",
        "姓名：张三",
        "我确诊了某种疾病",
        "127.0.0.1",
        "https://example.test?token=private",
    ],
)
def test_common_private_text_patterns(private):
    text = redaction.redact_payload({"content": f"请排查：{private}。保留排查步骤。"})[
        "content"
    ]
    assert private not in text
    assert "保留排查步骤" in text


def test_embedded_tool_json_and_known_credentials(monkeypatch):
    monkeypatch.setattr(
        redaction.settings, "llm_api_key", SecretStr("custom-provider-key")
    )
    arguments = json.dumps(
        {
            "body": {"email": "test@example.test", "name": "张三"},
            "household_id": "private-household",
        },
        ensure_ascii=False,
    )
    safe = redaction.redact_payload(
        {
            "tool_calls": [
                {
                    "id": "private-call",
                    "function": {"name": "invite_member", "arguments": arguments},
                }
            ],
            "text": "调用失败 custom-provider-key，继续排查。",
            "headers": {
                "Authorization": {"nested": "arbitrary-secret"},
                "Cookie": "session=secret",
            },
            "apiKey": "arbitrary-provider-key",
        }
    )
    text = json.dumps(safe, ensure_ascii=False)
    for private in (
        "test@example.test",
        "张三",
        "private-household",
        "private-call",
        "custom-provider-key",
        "arbitrary-secret",
        "session=secret",
        "arbitrary-provider-key",
    ):
        assert private not in text
    assert safe["tool_calls"][0]["function"]["name"] == "invite_member"
    assert json.loads(safe["tool_calls"][0]["function"]["arguments"])["body"][
        "name"
    ].startswith("[姓名_")
    assert "继续排查" in text


def test_fail_closed_for_unsupported_deep_and_failed_payloads(monkeypatch):
    value = {"content": b"private-binary"}
    assert "private-binary" not in repr(redaction.redact_payload(value))
    for _ in range(25):
        value = {"nested": value}
    assert "private-binary" not in repr(redaction.redact_payload(value))

    def broken(self, value):
        raise RuntimeError("private-error")

    monkeypatch.setattr(redaction.Redactor, "text", broken)
    assert redaction.redact_payload({"content": "private-original"}) == {
        "redacted": "[内容脱敏失败，已隐藏]",
    }


def test_system_security_instructions_and_token_usage_are_preserved():
    payload = {
        "messages": [
            {"role": "system", "content": "密码、退出登录由用户操作。不能越过确认。"}
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
    }
    assert redaction.redact_payload(payload) == payload


def test_identity_references_propagate_between_payloads_and_scope_is_reset():
    with redaction.redaction_scope():
        first = redaction.redact_payload({"person": {"name": "Alice Example"}})
        with redaction.redaction_scope():
            answer = redaction.redact_payload({"content": "Alice Example 的邀请失败。"})
        assert first["person"]["name"] in answer["content"]
        assert "Alice Example" not in answer["content"]
    assert redaction.ACTIVE_REDACTOR.get() is None


def test_redaction_is_idempotent_for_labelled_free_text():
    value = {"content": "地址：示例路1号，姓名：张三，密码：hunter2。"}
    safe = redaction.redact_payload(value)
    assert redaction.redact_payload(safe) == safe
