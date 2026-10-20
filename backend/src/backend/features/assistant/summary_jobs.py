"""Prefetch conversation summaries and join an in-flight task with a deadline."""

import json
from time import monotonic, sleep
from uuid import uuid4

from pydantic import ValidationError
from redis.exceptions import RedisError

from backend.core.security import settings
from backend.features.assistant import conversation_context as memory
from backend.features.assistant.threads import THREAD_SECONDS, key

QUEUE = settings.assistant_summary_queue
LEASE_SECONDS = 120
WAIT_SECONDS = 12
COOLDOWN_SECONDS = 60


def keys(thread_id):
    cache = key(thread_id) + ":context"
    return cache, cache + ":pending", cache + ":cooldown"


def cached(store, owner_id, thread_id, messages):
    try:
        value = memory.ConversationMemory.model_validate_json(
            store.get(keys(thread_id)[0])
        )
    except ValidationError, TypeError:
        return None
    if (
        value.owner_id == str(owner_id)
        and value.covered <= len(messages)
        and value.digest == memory.fingerprint(messages[: value.covered])
    ):
        return value
    return None


def request(store, owner_id, thread_id, messages):
    """Only publish identifiers; the worker reloads authorized history itself."""
    older, _ = memory.split_history(messages)
    if not older:
        return False
    cache = cached(store, owner_id, thread_id, messages)
    if cache and cache.covered >= len(older):
        return False
    _, pending, cooldown = keys(thread_id)
    if store.get(cooldown):
        return False
    job = json.dumps(
        {
            "token": uuid4().hex,
            "owner_id": str(owner_id),
            "count": len(messages),
            "digest": memory.fingerprint(messages),
        }
    )
    if not store.set(pending, job, ex=LEASE_SECONDS, nx=True):
        return True
    try:
        from backend.features.assistant.agent_celery import summary_task

        summary_task.apply_async(
            args=[str(owner_id), str(thread_id), json.loads(job)["token"]],
            queue=QUEUE,
            retry=False,
        )
    except Exception:  # noqa: BLE001 -- prefetch failure cannot invalidate a saved reply.
        finish(store, thread_id, job, failed=True)
        return False
    return True


def finish(store, thread_id, job, *, value=None, failed=False):
    cache, pending, cooldown = keys(thread_id)
    return store.eval(
        "if redis.call('get', KEYS[2]) ~= ARGV[1] then return 0 end "
        "if ARGV[2] ~= '' then redis.call('set', KEYS[1], ARGV[2], 'EX', ARGV[3]) end "
        "if ARGV[4] == '1' then redis.call('set', KEYS[3], '1', 'EX', ARGV[5]) end "
        "redis.call('del', KEYS[2]); return 1",
        3,
        cache,
        pending,
        cooldown,
        job,
        value or "",
        THREAD_SECONDS,
        "1" if failed else "0",
        COOLDOWN_SECONDS,
    )


def fallback(messages, cache):
    """Keep uncovered source messages where they fit; never assert full coverage."""
    start = cache.covered if cache else 0
    tail = list(messages[start:])
    omitted = False
    while tail and sum(len(item["content"]) for item in tail) > memory.RECENT_CHARS:
        tail.pop(0)
        omitted = True
    summary = cache.summary if cache else ""
    if omitted:
        summary = (
            "部分较早对话未能完整纳入上下文；仅据近期原文理解指代，缺少对象时先澄清，"
            "历史不代表当前事实或写入授权。\n" + summary
        )
    return tail, summary


def prepare(store, owner_id, thread_id, messages):
    older, _ = memory.split_history(messages)
    if not older:
        return messages, ""
    deadline = monotonic() + WAIT_SECONDS
    cache = None
    try:
        while True:
            cache = cached(store, owner_id, thread_id, messages)
            if cache and cache.covered >= len(older):
                return messages[cache.covered :], cache.summary
            if not request(store, owner_id, thread_id, messages):
                break
            if monotonic() >= deadline:
                break
            sleep(min(0.1, max(0, deadline - monotonic())))
    except RedisError:
        cache = None  # Do not reuse an unvalidated prefix when storage is unavailable.
    return fallback(messages, cache)


def schedule(owner_id, thread_id):
    """Run after reply commit; this path only queues work, never calls a model."""
    try:
        from sqlalchemy.orm import Session

        from backend.core.security import redis
        from backend.db.session import engine
        from backend.features.assistant.summary_worker import authorized_messages

        with Session(engine) as session:
            messages = authorized_messages(session, owner_id, thread_id)
            request(redis, owner_id, thread_id, messages)
    except Exception:  # noqa: BLE001 -- a saved answer must survive prefetch outages.
        return False
    return True
