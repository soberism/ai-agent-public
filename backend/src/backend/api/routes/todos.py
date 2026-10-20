import hashlib
import json
from datetime import UTC, datetime, time, timedelta
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, Query, Response
from sqlalchemy import DateTime, and_, cast, func, or_, select, text
from sqlalchemy.exc import IntegrityError

from backend.api.schemas import (
    ERROR_RESPONSES,
    TodoCreate,
    TodoList,
    TodoOut,
    TodoPatch,
    TodoQuery,
)
from backend.core.security import DB, APIError, Principal
from backend.db.models import Todo, utcnow
from backend.features.sharing.access import visible_condition
from backend.features.sharing.cleanup import delete_resource
from backend.features.todos.cursor import decode_cursor, encode_cursor

router = APIRouter(prefix="/api/todos", tags=["个人待办"], responses=ERROR_RESPONSES)


def effective_due(todo):
    if todo.due_at:
        return todo.due_at
    if todo.due_date:
        return datetime.combine(
            todo.due_date + timedelta(days=1), time(), ZoneInfo(todo.timezone)
        ).astimezone(UTC)
    return None


def output(todo, now=None):
    now = now or utcnow()
    due = effective_due(todo)
    return TodoOut(
        id=todo.id,
        title=todo.title,
        description=todo.description,
        due_date=todo.due_date,
        due_time=todo.due_time.strftime("%H:%M") if todo.due_time else None,
        timezone=todo.timezone,
        due_at=todo.due_at,
        status=todo.status,
        completed_at=todo.completed_at,
        created_at=todo.created_at,
        updated_at=todo.updated_at,
        is_overdue=todo.status == "ongoing" and due is not None and due <= now,
        assignee_id=todo.assignee_id or todo.owner_id,
    )


def set_due(todo):
    todo.due_at = (
        datetime.combine(
            todo.due_date, todo.due_time, ZoneInfo(todo.timezone)
        ).astimezone(UTC)
        if todo.due_time
        else None
    )


def owned(session, user, id, lock=False):
    query = select(Todo).where(visible_condition(Todo, user.id), Todo.id == id)
    todo = session.scalar(query.with_for_update() if lock else query)
    if todo is None:
        raise APIError(404, "TODO_NOT_FOUND", "该待办不存在或无法访问")
    return todo


@router.post(
    "",
    response_model=TodoOut,
    status_code=201,
    responses={200: {"model": TodoOut, "description": "幂等重放"}},
)
def create(
    body: TodoCreate,
    user: Principal,
    session: DB,
    response: Response,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
):
    payload = body.model_dump(mode="json")
    fingerprint = hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
    ).hexdigest()
    todo = Todo(
        owner_id=user.id,
        title=body.title,
        description=body.description,
        due_date=body.due_date,
        due_time=time.fromisoformat(body.due_time) if body.due_time else None,
        timezone=user.timezone,
        create_key=idempotency_key,
        create_fingerprint=fingerprint,
    )
    set_due(todo)
    session.add(todo)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        todo = session.scalar(
            select(Todo).where(
                Todo.owner_id == user.id, Todo.create_key == idempotency_key
            )
        )
        if todo is None:
            raise
        if todo.create_fingerprint != fingerprint:
            raise APIError(
                409, "IDEMPOTENCY_CONFLICT", "请求标识已用于其他内容，请重新发起新建"
            ) from None
        response.status_code = 200
    return output(todo)


@router.get("/{id}", response_model=TodoOut)
def detail(id: UUID, user: Principal, session: DB):
    return output(owned(session, user, id))


@router.patch("/{id}", response_model=TodoOut)
def update(id: UUID, body: TodoPatch, user: Principal, session: DB):
    todo = owned(session, user, id, lock=True)
    values = body.model_dump(exclude_unset=True)
    if "due_time" in values:
        values["due_time"] = (
            time.fromisoformat(values["due_time"]) if values["due_time"] else None
        )
    if "due_date" in values and values["due_date"] is None:
        values["due_time"] = None
    if values.get("due_time") and not values.get("due_date", todo.due_date):
        raise APIError(
            422,
            "VALIDATION_ERROR",
            "请选择有效的日期和时间",
            {"due_time": "设置截止时间前请选择日期"},
        )
    changed = any(getattr(todo, key) != value for key, value in values.items())
    if changed:
        now = utcnow()
        if "status" in values and values["status"] != todo.status:
            todo.completed_at = now if values["status"] == "completed" else None
        for key, value in values.items():
            setattr(todo, key, value)
        set_due(todo)
        todo.updated_at = now
        session.commit()
    return output(todo)


@router.delete("/{id}", status_code=204)
def remove(id: UUID, user: Principal, session: DB):
    todo = owned(session, user, id, lock=True)
    delete_resource(session, todo)
    session.commit()


@router.get("", response_model=TodoList)
def listing(query: Annotated[TodoQuery, Query()], user: Principal, session: DB):
    scope = {
        "v": 1,
        "user": str(user.id),
        "status": query.status,
        "filter": query.due,
        "due_time": query.due_time,
        "date_from": query.date_from.isoformat() if query.date_from else None,
        "date_to": query.date_to.isoformat() if query.date_to else None,
        "tz": user.timezone,
    }
    anchor, now = (
        decode_cursor(query.cursor, scope) if query.cursor else (None, utcnow())
    )
    day = now.astimezone(ZoneInfo(user.timezone)).date()
    effective = func.coalesce(
        Todo.due_at,
        func.timezone(
            user.timezone, cast(Todo.due_date, DateTime) + text("interval '1 day'")
        ),
    )
    statement = select(Todo).where(
        visible_condition(Todo, user.id), Todo.status == query.status
    )
    if query.date_from:
        statement = statement.where(
            Todo.due_date.between(query.date_from, query.date_to)
        )
    elif query.due == "none":
        statement = statement.where(Todo.due_date.is_(None))
    elif query.due == "overdue":
        statement = statement.where(effective <= now)
    elif query.due == "future":
        statement = statement.where(effective > now)
    elif query.due in ("today", "tomorrow", "next7"):
        start = day + timedelta(days=query.due == "tomorrow")
        end = start + timedelta(days=6 if query.due == "next7" else 0)
        statement = statement.where(Todo.due_date.between(start, end))
    if query.due_time:
        statement = statement.where(Todo.due_time == time.fromisoformat(query.due_time))
    if query.status == "completed":
        statement = statement.order_by(Todo.completed_at.desc(), Todo.id.asc())
        if anchor:
            boundary = datetime.fromisoformat(anchor["due"])
            statement = statement.where(
                or_(
                    Todo.completed_at < boundary,
                    and_(Todo.completed_at == boundary, Todo.id > UUID(anchor["id"])),
                )
            )
    else:
        statement = statement.order_by(
            effective.asc().nulls_last(), Todo.created_at.desc(), Todo.id.asc()
        )
        if anchor:
            tie = or_(
                Todo.created_at < datetime.fromisoformat(anchor["created"]),
                and_(
                    Todo.created_at == datetime.fromisoformat(anchor["created"]),
                    Todo.id > UUID(anchor["id"]),
                ),
            )
            if anchor["due"] is None:
                statement = statement.where(effective.is_(None), tie)
            else:
                boundary = datetime.fromisoformat(anchor["due"])
                statement = statement.where(
                    or_(
                        effective > boundary,
                        effective.is_(None),
                        and_(effective == boundary, tie),
                    )
                )
    rows = list(session.scalars(statement.limit(query.limit + 1)))
    more = len(rows) > query.limit
    rows = rows[: query.limit]
    cursor = None
    if more:
        last = rows[-1]
        due = last.completed_at if query.status == "completed" else effective_due(last)
        cursor = encode_cursor(
            scope
            | {
                "now": now.isoformat(),
                "day": day.isoformat(),
                "id": str(last.id),
                "created": last.created_at.isoformat(),
                "due": due.isoformat() if due else None,
            }
        )
    return TodoList(
        items=[output(row, now) for row in rows], next_cursor=cursor, server_time=now
    )
