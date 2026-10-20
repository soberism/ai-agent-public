"""Small adapters for authenticated business tools used by AI."""

import hashlib
import json
from datetime import time, timedelta
from typing import Annotated
from uuid import UUID, uuid5

from pydantic import Field
from sqlalchemy import select

from backend.api.hub_schemas import SearchResult
from backend.api.life_schemas import PantryOut, PreferenceOut
from backend.api.routes.hub import search
from backend.api.routes.life import meals
from backend.api.routes.todos import output, set_due
from backend.api.schemas import TodoDailyCreate, TodoOut
from backend.core.security import DB, Principal
from backend.db.models import Todo

_CLOSED = (
    "/contacts",
    "/appointments",
    "/archive-search",
    "/document-review",
    "/notifications",
    "/voice-live",
    "/meals/settings",
)


def search_business(
    q: Annotated[str, Field(min_length=1, max_length=100)],
    user: Principal,
    session: DB,
) -> SearchResult:
    """Reuse the permission-filtered hub search without surfacing disabled pages."""
    result = search(user, session, q)
    return SearchResult(
        items=[item for item in result.items if not item.url.startswith(_CLOSED)]
    )


def open_connections(user: Principal, session: DB):
    """Return only the existing navigation entry; never operate a connection."""
    from backend.features.assistant.feature_replies import entry_reply

    return entry_reply("connections")


def list_preferences(user: Principal, session: DB) -> list[PreferenceOut]:
    return meals(user, session).preferences


def list_pantry(user: Principal, session: DB) -> list[PantryOut]:
    return meals(user, session).pantry


def daily_dates(body: TodoDailyCreate):
    return [
        body.date_from + timedelta(days=offset)
        for offset in range((body.date_to - body.date_from).days + 1)
    ]


def create_daily_todos(
    body: TodoDailyCreate,
    idempotency_key: UUID,
    user: Principal,
    session: DB,
) -> list[TodoOut]:
    dates = daily_dates(body)
    due_time = time.fromisoformat(body.due_time)
    existing = {
        todo.due_date: todo
        for todo in session.scalars(
            select(Todo).where(
                Todo.owner_id == user.id,
                Todo.title == body.title,
                Todo.due_date.in_(dates),
                Todo.due_time == due_time,
            )
        )
    }
    todos = []
    for due_date in dates:
        todo = existing.get(due_date)
        if todo is None:
            payload = {
                "title": body.title,
                "description": body.description,
                "due_date": due_date.isoformat(),
                "due_time": body.due_time,
            }
            todo = Todo(
                owner_id=user.id,
                title=body.title,
                description=body.description,
                due_date=due_date,
                due_time=due_time,
                timezone=user.timezone,
                create_key=uuid5(idempotency_key, due_date.isoformat()),
                create_fingerprint=hashlib.sha256(
                    json.dumps(
                        payload,
                        sort_keys=True,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest(),
            )
            set_due(todo)
            session.add(todo)
        todos.append(todo)
    session.commit()
    return [output(todo) for todo in todos]
