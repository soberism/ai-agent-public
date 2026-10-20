"""Integration fixtures must never send default tasks to a shared worker queue."""

from uuid import uuid4

from celery import Task

from backend.core.security import settings
from backend.features.assistant.agent_celery import celery


def isolate_default_queue(monkeypatch):
    queue = "ai-agent-test-" + uuid4().hex
    original = Task.apply_async
    published = False

    def publish(task, *args, **options):
        nonlocal published
        requested = options.get("queue")
        redirected = (
            requested is None
            or requested == "celery"
            or (
                requested == settings.assistant_summary_queue
                and not str(requested).startswith("ai-agent-")
            )
        )
        if redirected:
            options["queue"] = queue
        result = original(task, *args, **options)
        published = published or redirected
        return result

    monkeypatch.setattr(Task, "apply_async", publish)

    def cleanup():
        if published:
            with celery.connection_for_write() as connection:
                connection.default_channel.queue_delete(queue=queue)

    return cleanup
