"""Generate a versioned summary outside the answer worker and publish atomically."""

import json
from uuid import UUID

from sqlalchemy.orm import Session

from backend.core.security import redis
from backend.db.models import User
from backend.db.session import engine
from backend.features.assistant import conversation_context as memory
from backend.features.assistant import history, summary_jobs
from backend.features.assistant.access import current_context
from backend.features.assistant.threads import load


def authorized_messages(session, owner_id, thread_id):
    owner_id, thread_id = UUID(str(owner_id)), UUID(str(thread_id))
    user = session.get(User, owner_id)
    if user is None or not user.active:
        raise ValueError("账号不可用")
    history.owned(session, thread_id, owner_id)
    history.cache(redis, owner_id, thread_id, history.messages(session, thread_id))
    messages, _ = current_context(
        session, user, load(redis, thread_id, owner_id), thread_id
    )
    while messages and messages[-1]["role"] == "user":
        messages.pop()
    return messages


class StagedStore:
    """Keep generated text private until permissions and revision are rechecked."""

    def __init__(self):
        self.value = None

    def get(self, name):
        return redis.get(name)

    def set(self, name, value, ex):
        self.value = value


def generate(owner_id, thread_id, token):
    job = redis.get(summary_jobs.keys(thread_id)[1])
    if not job:
        return
    spec = json.loads(job)
    if spec["token"] != token or spec["owner_id"] != str(owner_id):
        return
    success = False
    try:
        with Session(engine) as session:
            messages = authorized_messages(session, owner_id, thread_id)
            snapshot = messages[: spec["count"]]
            if memory.fingerprint(snapshot) != spec["digest"]:
                return
            existing = summary_jobs.cached(redis, owner_id, thread_id, snapshot)
            if existing and existing.covered >= len(memory.split_history(snapshot)[0]):
                success = bool(summary_jobs.finish(redis, thread_id, job))
                return
            staged = StagedStore()
            memory.prepare(staged, owner_id, thread_id, snapshot)
            if not staged.value:
                return
            session.expire_all()
            latest = authorized_messages(session, owner_id, thread_id)
            if memory.fingerprint(latest[: spec["count"]]) != spec["digest"]:
                return
            success = bool(
                summary_jobs.finish(redis, thread_id, job, value=staged.value)
            )
    finally:
        if not success:
            summary_jobs.finish(redis, thread_id, job, failed=True)
