from unittest.mock import MagicMock

from celery import Task
from queue_isolation import isolate_default_queue

from backend.features.assistant.agent_celery import celery


def test_fixture_redirects_shared_queue_and_preserves_explicit_test_queue(monkeypatch):
    calls = []
    monkeypatch.setattr(
        Task, "apply_async", lambda *args, **kwargs: calls.append(kwargs)
    )
    connection = MagicMock()
    monkeypatch.setattr(celery, "connection_for_write", lambda: connection)
    cleanup = isolate_default_queue(monkeypatch)
    task = Task()
    task.apply_async(args=["synthetic"])
    task.apply_async(args=["synthetic"], queue="assistant-summary")
    task.apply_async(args=["synthetic"], queue="ai-agent-explicit-test")
    assert calls[0]["queue"].startswith("ai-agent-test-")
    assert calls[0]["queue"] == calls[1]["queue"]
    assert calls[2]["queue"] == "ai-agent-explicit-test"
    cleanup()
    connection.__enter__.return_value.default_channel.queue_delete.assert_called_once_with(
        queue=calls[0]["queue"]
    )
