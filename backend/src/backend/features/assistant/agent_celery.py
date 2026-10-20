"""Celery application and retry policy for autonomous agent work."""

from celery import Celery
from celery.signals import worker_process_shutdown

from backend.core.langsmith_tracing import flush_traces
from backend.core.security import APIError, settings
from backend.features.assistant.agent_index import execute_index, execute_reindex
from backend.features.assistant.agent_tasks import (
    LEASE,
    execute_plan,
    execute_run,
)

celery = Celery("ai-agent", broker=settings.celery_broker_url)


@worker_process_shutdown.connect
def flush_worker_traces(**kwargs):
    flush_traces()


celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    task_time_limit=1500,
    worker_enable_remote_control=False,
    task_publish_retry=True,
    task_publish_retry_policy={
        "max_retries": 3,
        "interval_start": 0,
        "interval_step": 1,
    },
)


@celery.task(bind=True, name="assistant.run", acks_late=True, max_retries=2)
def run_task(self, run_id: str, owner_id: str):
    if execute_run(run_id, owner_id):
        raise self.retry(countdown=int(LEASE.total_seconds()) + 5)


@celery.task(bind=True, name="assistant.resume", acks_late=True, max_retries=2)
def resume_task(self, run_id: str, owner_id: str):
    if execute_plan(run_id, owner_id):
        raise self.retry(countdown=int(LEASE.total_seconds()) + 5)


@celery.task(
    name="assistant.index_material",
    autoretry_for=(APIError,),
    retry_backoff=True,
    max_retries=3,
)
def index_material_task(material_id: str, owner_id: str):
    execute_index(material_id, owner_id)


@celery.task(
    bind=True,
    name="assistant.reindex_materials",
    autoretry_for=(APIError,),
    retry_backoff=True,
    max_retries=3,
)
def reindex_materials_task(self, owner_id: str, token: str):
    from backend.core.security import redis
    from backend.features.assistant.index_queue import key, release

    if redis.get(key(owner_id)) != token:
        return
    try:
        execute_reindex(owner_id)
    except APIError:
        if self.request.retries >= self.max_retries:
            release(owner_id, token)
        raise
    except Exception:
        release(owner_id, token)
        raise
    else:
        release(owner_id, token)


@celery.task(name="assistant.summarize", acks_late=True, time_limit=90)
def summary_task(owner_id: str, thread_id: str, token: str):
    from backend.features.assistant.summary_worker import generate

    try:
        generate(owner_id, thread_id, token)
    except Exception:  # noqa: BLE001 -- do not log private history or block future answers.
        return False
    return True
