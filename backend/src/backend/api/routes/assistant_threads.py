from datetime import UTC, timedelta

from fastapi import APIRouter
from sqlalchemy import select

from backend.api.schemas import AssistantItem, AssistantThread, AssistantThreadStart
from backend.core.security import DB, Principal, Store
from backend.db.models import AssistantThread as SavedThread
from backend.features.assistant import history
from backend.features.assistant.threads import key

router = APIRouter()


def item(todo) -> AssistantItem:
    return AssistantItem(
        **todo.model_dump(include={"id", "title", "due_date", "due_time", "status"})
    )


def generic_item(value):
    return AssistantItem(
        id=value.id,
        title=value.title,
        status="available",
        kind=value.kind,
        url=value.url,
    )


def query_message(items: list[AssistantItem], status: str) -> str:
    if not items:
        return "没有找到符合条件的待办。"
    label = "已完成事项" if status == "completed" else "待办"
    titles = "、".join(f"“{value.title}”" for value in items[:5])
    suffix = "等" if len(items) > 5 else ""
    return f"找到 {len(items)} 条{label}：{titles}{suffix}。"


@router.post("/threads", response_model=AssistantThread)
def start_thread(
    body: AssistantThreadStart, user: Principal, session: DB, store: Store
):
    old_ids = (
        list(
            session.scalars(
                select(SavedThread.id).where(SavedThread.owner_id == user.id)
            )
        )
        if body.fresh
        else []
    )
    thread, saved = history.start(session, user.id, body.fresh, store)
    if old_ids:
        store.delete(*(key(value) for value in old_ids))
    history.cache(store, user.id, thread.id, saved)
    created_at = thread.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return AssistantThread(
        thread_id=thread.id,
        expires_at=created_at + timedelta(hours=history.HISTORY_HOURS),
        entries=history.output(saved),
    )


def search_reply(intent, user, session):
    from backend.api.routes.hub import search
    from backend.api.schemas import AssistantReply

    if not intent.query:
        return AssistantReply(kind="clarify", message="请告诉我要搜索的内容。")
    closed = (
        "/contacts",
        "/appointments",
        "/archive-search",
        "/document-review",
        "/notifications",
        "/voice-live",
        "/meals/settings",
    )
    items = [
        generic_item(value)
        for value in search(user, session, intent.query).items
        if not value.url.startswith(closed)
        and (
            not intent.target_type
            or value.kind
            == ("document" if intent.target_type == "material" else intent.target_type)
        )
    ]
    return AssistantReply(
        kind="result", message=f"找到 {len(items)} 条相关结果。", items=items
    )
