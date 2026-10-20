import json
import logging
import secrets
from uuid import UUID

from fastapi import APIRouter, Response
from sqlalchemy.exc import SQLAlchemyError

from backend.api.calendar_schemas import EventCreate
from backend.api.planning_schemas import ChecklistWithItemsCreate
from backend.api.routes.calendar_events import create as create_event
from backend.api.routes.planning import create_checklist
from backend.api.routes.todos import create, update
from backend.api.schemas import AssistantItem, AssistantReply, TodoCreate, TodoPatch
from backend.core.security import DB, APIError, Principal, Store, settings
from backend.db.models import CalendarEvent, Checklist, Todo, utcnow
from backend.features.assistant import history
from backend.features.assistant.web_search import with_sources
from backend.features.sharing.access import accessible
from backend.features.sharing.cleanup import delete_resource

router = APIRouter()
logger = logging.getLogger(__name__)
ACTION_SECONDS = 300
CONSUME_ACTION = """
local value = redis.call('GET', KEYS[1])
if not value or string.sub(value, 1, string.len(ARGV[1])) ~= ARGV[1] then return nil end
redis.call('DEL', KEYS[1])
return string.sub(value, string.len(ARGV[1]) + 1)
"""


def action_key(token):
    return settings.redis_namespace + "assistant:action:" + token


def read_action(raw, user_id):
    prefix = str(user_id) + "|"
    try:
        if not raw.startswith(prefix):
            raise ValueError
        return json.loads(raw[len(prefix) :])
    except AttributeError, TypeError, ValueError, KeyError, json.JSONDecodeError:
        raise APIError(404, "ACTION_NOT_FOUND", "确认操作已失效，请重新发起") from None


def confirmation(store, user, thread_id, action, payload, message, label):
    token = secrets.token_urlsafe(32)
    store.set(
        action_key(token),
        str(user.id)
        + "|"
        + json.dumps(
            {"thread_id": str(thread_id), "action": action, "payload": payload}
        ),
        ex=ACTION_SECONDS,
    )
    return AssistantReply(
        kind="confirm", message=message, action_token=token, action_label=label
    )


def todo_item(todo):
    return AssistantItem(
        **todo.model_dump(include={"id", "title", "due_date", "due_time", "status"})
    )


@router.post("/actions/{token}/confirm", response_model=AssistantReply)
def confirm(token: str, user: Principal, session: DB, store: Store):
    if len(token) > 128:
        raise APIError(404, "ACTION_NOT_FOUND", "确认操作已失效，请重新发起")
    pending = read_action(store.get(action_key(token)), user.id)
    thread = history.owned(session, UUID(pending["thread_id"]), user.id)
    raw = store.eval(CONSUME_ACTION, 1, action_key(token), str(user.id) + "|")
    action = read_action(str(user.id) + "|" + raw if raw else None, user.id)
    if action["action"] == "create":
        payload = action["payload"]
        create_key = UUID(payload.pop("create_key"))
        todo = create(
            TodoCreate(**payload),
            user,
            session,
            Response(),
            create_key,
        )
        message, items = "待办已创建。", [todo_item(todo)]
    elif action["action"] == "complete":
        todo = update(
            UUID(action["payload"]["id"]), TodoPatch(status="completed"), user, session
        )
        message, items = "待办已完成。", [todo_item(todo)]
    elif action["action"] == "create_checklist":
        value = create_checklist(
            ChecklistWithItemsCreate(**action["payload"]), user, session
        )
        message = f"清单已创建，共{value.total_count}项。"
        items = [
            AssistantItem(
                id=value.id,
                title=value.title,
                status="ongoing",
                kind="checklist",
                url=f"/checklists/{value.id}",
            )
        ]
    elif action["action"] == "create_event":
        value = create_event(EventCreate(**action["payload"]), user, session)
        message = "日程已创建。"
        items = [
            AssistantItem(
                id=value.id,
                title=value.title,
                status="scheduled",
                kind="event",
                url=f"/calendar/{value.id}/edit",
            )
        ]
    elif action["action"] == "manage_object":
        payload = action["payload"]
        model = (
            CalendarEvent
            if payload["kind"] == "event"
            else Checklist
            if payload["kind"] == "checklist"
            else Todo
        )
        value = accessible(session, user, model, UUID(payload["id"]))
        title = value.title
        if payload["operation"] == "delete":
            delete_resource(session, value)
            message, items = f"“{title}”已删除。", []
        else:
            value.title, value.updated_at = payload["new_title"], utcnow()
            session.commit()
            message = f"“{title}”已重命名。"
            items = [
                AssistantItem(
                    id=value.id,
                    title=value.title,
                    status="available",
                    kind=payload["kind"],
                    url=f"/calendar/{value.id}/edit"
                    if payload["kind"] == "event"
                    else f"/checklists/{value.id}"
                    if payload["kind"] == "checklist"
                    else f"/todos/{value.id}",
                )
            ]
        session.commit()
    elif action["action"] == "feature":
        from backend.api.routes.assistant_features import invoke

        payload = action["payload"]
        result = invoke(
            payload["name"],
            payload["args"],
            user,
            session,
            idempotency_token=token,
        )
        message, items = result.message, result.items
    else:
        raise APIError(422, "INVALID_ACTION", "确认操作无效")
    from backend.features.assistant.replies import personalize_for_user

    reply = personalize_for_user(
        AssistantReply(kind="success", message=message, items=items), session, user.id
    )
    reply.message = with_sources(reply.message, [])
    message = reply.message
    try:
        history.append(session, thread, "assistant", message, reply)
        history.cache(store, user.id, thread.id, history.messages(session, thread.id))
    except SQLAlchemyError:
        session.rollback()
        logger.exception("操作成功，但AI对话历史保存失败")
    return reply
