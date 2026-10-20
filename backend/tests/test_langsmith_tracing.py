import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

import httpx2
import pytest
from langgraph.graph import END, START, StateGraph
from langsmith import get_tracing_context
from langsmith.run_helpers import get_current_run_tree
from openai import OpenAI
from pydantic import SecretStr

from backend.core import langsmith_tracing as tracing
from backend.core.config import Settings


@pytest.mark.parametrize("name", ["LANGSMITH_API_KEY", "LANG_SMITH_API_KEY"])
def test_key_names_and_secret_representation(monkeypatch, name):
    for key in ("LANGSMITH_API_KEY", "LANG_SMITH_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv(name, "private-test-key")
    configured = Settings(_env_file=None)
    assert configured.langsmith_api_key.get_secret_value() == "private-test-key"
    assert "private-test-key" not in repr(configured)


def test_explicit_off_does_not_construct_client(monkeypatch):
    monkeypatch.setattr(tracing.settings, "langsmith_tracing", False)
    monkeypatch.setattr(tracing.settings, "langsmith_api_key", SecretStr("test-only"))
    assert tracing.get_client() is None


def test_unconfigured_disables_even_inherited_tracing(monkeypatch):
    monkeypatch.setattr(tracing.settings, "langsmith_api_key", SecretStr(""))
    monkeypatch.setenv("LANGSMITH_TRACING", "true")

    @tracing.observed
    def business():
        assert get_tracing_context()["enabled"] is False
        return "原有结果"

    assert business() == "原有结果"
    assert tracing.traced_model(object()) is not None


@pytest.fixture
def captured_client(monkeypatch):
    # 使用真实 SDK 到 HTTP 发送前的边界；不向外部上传测试数据。
    captured = []

    def request(self, method, pathname, **kwargs):
        captured.append((method, pathname, kwargs))
        from requests import Response

        response = Response()
        response.status_code = 200
        response._content = b"{}"
        return response

    client_class = tracing.Client
    monkeypatch.setattr(client_class, "request_with_retries", request)
    monkeypatch.setattr(
        tracing,
        "Client",
        lambda **kwargs: client_class(
            **kwargs,
            auto_batch_tracing=False,
            info={},
        ),
    )

    def flush_buffer(self):
        from langsmith._internal._background_thread import (
            _process_buffered_run_ops_batch,
        )

        batch = list(self._run_ops_buffer)
        self._run_ops_buffer.clear()
        _process_buffered_run_ops_batch(self, batch)

    # 仅把后台批处理同步执行，便于在断言前检查完整 HTTP 载荷。
    monkeypatch.setattr(client_class, "_flush_run_ops_buffer", flush_buffer)
    client = tracing._client(999999, "test-only-key", "https://example.test", "")
    monkeypatch.setattr(tracing, "get_client", lambda: client)
    yield client, captured
    client.flush(timeout=3)
    tracing._client.cache_clear()


def test_graph_and_deepseek_sdk_share_safe_trace(captured_client, monkeypatch):
    client, captured = captured_client
    monkeypatch.setattr(tracing.settings, "app_env", "production")
    monkeypatch.setattr(tracing.settings, "langsmith_project", "")
    secret = "debug-visible private@example.test 手机13800138000 密码sk-private"
    sent = []

    def model_response(request):
        sent.append(json.loads(request.content))
        return httpx2.Response(
            200,
            json={
                "id": "chat-test",
                "object": "chat.completion",
                "created": 1,
                "model": "deepseek-chat",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": secret},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 3,
                    "completion_tokens": 4,
                    "total_tokens": 7,
                },
            },
        )

    model = tracing.traced_model(
        OpenAI(
            api_key="deepseek-test-only",
            base_url="https://deepseek.example.test",
            http_client=httpx2.Client(transport=httpx2.MockTransport(model_response)),
        )
    )
    graph = StateGraph(dict)

    def reason(state):
        response = model.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": secret}],
        )
        assert response.choices[0].message.content == secret
        return state

    graph.add_node("reason", reason)
    graph.add_edge(START, "reason")
    graph.add_edge("reason", END)
    runnable = graph.compile()
    roots = []

    @tracing.observed
    def execute_run(run_id, owner_id):
        roots.append(get_current_run_tree())
        return runnable.invoke(
            {"prompt": secret},
            config={
                "configurable": {"thread_id": "private-business-thread"},
                "metadata": {"owner_id": owner_id},
            },
        )

    assert execute_run("business-run", "private-owner")["prompt"] == secret
    client.flush(timeout=3)
    assert roots[0].session_name == "ai-agent-production"
    assert roots[0].metadata["run_ref"] == hashlib.sha256(b"business-run").hexdigest()
    assert sent[0]["messages"][0]["content"] == secret
    assert captured
    wire = repr(captured)
    for value in (
        "private@example",
        "13800138000",
        "sk-private",
        "private-owner",
        "private-business-thread",
        "business-run",
        "deepseek-test-only",
    ):
        assert value not in wire
    assert "ChatOpenAI" in wire
    assert "reason" in wire
    assert "debug-visible" in wire
    model.close()


def test_final_batch_boundary_drops_all_sensitive_fields(captured_client):
    client, captured = captured_client
    identifier = uuid4()
    client.batch_ingest_runs(
        create=[
            {
                "id": identifier,
                "trace_id": identifier,
                "dotted_order": f"20261015T000000000000Z{identifier}",
                "name": "read_api",
                "run_type": "tool",
                "start_time": datetime.now(UTC),
                "inputs": {"password": "private-input"},
                "outputs": {"contact": "private-output"},
                "error": "private-exception",
                "events": [
                    {"name": "private-event", "kwargs": {"token": "private-token"}}
                ],
                "serialized": {
                    "id": ["private-path"],
                    "kwargs": {"api_key": "private-key"},
                },
                "extra": {
                    "metadata": {
                        "owner_id": "private-owner",
                        "environment": "production",
                    }
                },
                "tags": ["private-tag"],
                "attachments": {"private-file": ("text/plain", b"private-attachment")},
            }
        ]
    )
    client.flush(timeout=3)
    assert captured
    assert "private-" not in repr(captured)


def test_business_exception_and_disabled_results_are_preserved(captured_client):
    client, captured = captured_client

    @tracing.observed
    def business():
        raise ValueError("private-error@example.test sk-private")

    with pytest.raises(ValueError, match="private-error"):
        business()
    client.flush(timeout=3)
    assert captured
    assert "private-error" not in repr(captured)
    assert "sk-private" not in repr(captured)


def test_resume_uses_same_hashed_run_reference(captured_client):
    references = []

    @tracing.observed
    def execute_run(run_id, owner_id):
        references.append(get_current_run_tree().metadata["run_ref"])

    @tracing.observed
    def execute_plan(run_id, owner_id):
        references.append(get_current_run_tree().metadata["run_ref"])

    execute_run("business-run", "private-owner")
    execute_plan(run_id="business-run", owner_id="private-owner")
    assert references == [hashlib.sha256(b"business-run").hexdigest()] * 2


def test_client_setup_failure_does_not_change_business(monkeypatch):
    monkeypatch.setattr(tracing.settings, "langsmith_tracing", True)
    monkeypatch.setattr(tracing.settings, "langsmith_api_key", SecretStr("test-only"))

    def fail(*args):
        raise RuntimeError("private-configuration")

    monkeypatch.setattr(tracing, "_client", fail)
    assert tracing.observed(lambda: 42)() == 42
