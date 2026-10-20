from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, delete, or_, select

from backend.core.security import APIError
from backend.db.models import AssistantMessage, AssistantThread
from backend.features.assistant.history_cleanup import remove_threads
from backend.features.assistant.threads import create as cache_thread

HISTORY_HOURS = 24
MAX_TURNS = 100


def cutoff():
    return datetime.now(UTC) - timedelta(hours=HISTORY_HOURS)


def start(session, owner_id: UUID, fresh: bool = False, store=None):
    purge(session, store)
    thread = None
    if not fresh:
        thread = session.scalar(
            select(AssistantThread)
            .where(
                AssistantThread.owner_id == owner_id,
                AssistantThread.created_at >= cutoff(),
            )
            .order_by(AssistantThread.updated_at.desc())
            .limit(1)
        )
    if thread is None:
        if fresh:
            old_ids = list(
                session.scalars(
                    select(AssistantThread.id).where(
                        AssistantThread.owner_id == owner_id
                    )
                )
            )
            remove_threads(session, old_ids, store)
        thread = AssistantThread(owner_id=owner_id)
        session.add(thread)
        session.commit()
    return thread, messages(session, thread.id)


def purge(session, store=None):
    ids = list(
        session.scalars(
            select(AssistantThread.id).where(AssistantThread.created_at < cutoff())
        )
    )
    remove_threads(session, ids, store)
    session.commit()


def owned(session, thread_id: UUID, owner_id: UUID):
    thread = session.scalar(
        select(AssistantThread).where(
            AssistantThread.id == thread_id,
            AssistantThread.owner_id == owner_id,
            AssistantThread.created_at >= cutoff(),
        )
    )
    if thread is None:
        raise APIError(410, "THREAD_EXPIRED", "对话已过期，请重新开始")
    return thread


def messages(session, thread_id: UUID):
    return list(
        session.scalars(
            select(AssistantMessage)
            .where(
                AssistantMessage.thread_id == thread_id,
            )
            .order_by(AssistantMessage.created_at, AssistantMessage.id)
        )
    )


def cache(store, owner_id: UUID, thread_id: UUID, saved):
    last_result = next(
        (value for value in reversed(saved) if value.kind == "result"), None
    )
    cache_thread(
        store,
        owner_id,
        thread_id,
        [{"role": value.role, "content": value.content} for value in saved],
        (getattr(last_result, "context_refs", None) or last_result.items)
        if last_result
        else None,
    )


def output(saved):
    return [
        {"role": "user", "message": value.content}
        if value.role == "user"
        else {
            "id": str(value.id),
            "role": "assistant",
            "reply": {
                "kind": value.kind,
                "message": value.content,
                "items": value.items or [],
                "action_token": None,
                "action_label": None,
                "suggestions": value.suggestions or [],
            },
        }
        for value in saved
    ]


def append(session, thread, role: str, content: str, reply=None):
    session.add(
        AssistantMessage(
            thread_id=thread.id,
            role=role,
            content=content,
            kind=reply.kind if reply else None,
            items=[item.model_dump(mode="json") for item in reply.items]
            if reply
            else None,
            action_label=reply.action_label if reply else None,
            suggestions=[
                item.model_dump(mode="json")
                for item in getattr(reply, "suggestions", [])
            ]
            if reply
            else None,
        )
    )
    thread.updated_at = datetime.now(UTC)
    session.commit()


def trim(session, thread_id: UUID):
    oldest = session.scalar(
        select(AssistantMessage)
        .where(AssistantMessage.thread_id == thread_id, AssistantMessage.role == "user")
        .order_by(AssistantMessage.created_at.desc(), AssistantMessage.id.desc())
        .offset(MAX_TURNS - 1)
        .limit(1)
    )
    if oldest is None:
        return
    session.execute(
        delete(AssistantMessage).where(
            AssistantMessage.thread_id == thread_id,
            or_(
                AssistantMessage.created_at < oldest.created_at,
                and_(
                    AssistantMessage.created_at == oldest.created_at,
                    AssistantMessage.id < oldest.id,
                ),
            ),
        )
    )
    session.commit()


def append_pair(session, thread, user_message: str, reply):
    session.add(
        AssistantMessage(thread_id=thread.id, role="user", content=user_message)
    )
    append(session, thread, "assistant", reply.message, reply)
    trim(session, thread.id)
