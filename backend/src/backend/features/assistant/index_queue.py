"""One reindex job per account, with a lease longer than the worker hard timeout."""

from uuid import uuid4

from backend.core.security import APIError, redis, settings
from backend.features.assistant.request_limits import charge

LEASE_SECONDS = 1800


def key(owner_id):
    return f"{settings.redis_namespace}reindex:{owner_id}"


def release(owner_id, token):
    redis.eval(
        "if redis.call('GET',KEYS[1]) == ARGV[1] then "
        "return redis.call('DEL',KEYS[1]) end return 0",
        1,
        key(owner_id),
        token,
    )


def enqueue(owner_id):
    from backend.features.assistant.agent_celery import reindex_materials_task

    token = uuid4().hex
    if not redis.set(key(owner_id), token, nx=True, ex=LEASE_SECONDS):
        raise APIError(409, "REINDEX_RUNNING", "知识库重建已在处理中，请勿重复提交")
    try:
        charge(owner_id, "reindex")
        reindex_materials_task.delay(str(owner_id), token)
    except Exception:
        release(owner_id, token)
        raise
