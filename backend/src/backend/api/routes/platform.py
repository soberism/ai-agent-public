from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from sqlalchemy import DateTime, cast, func, select, text, update
from sqlalchemy.exc import SQLAlchemyError

from backend.api.platform_schemas import (
    PlatformHome,
    PlatformSettings,
    PlatformSettingsPatch,
    TodoSummary,
)
from backend.api.routes.calendar_events import output as event_output
from backend.api.routes.todos import output
from backend.api.schemas import ERROR_RESPONSES
from backend.core.security import DB, Principal
from backend.db.household_models import HouseholdParticipant
from backend.db.models import CalendarEvent, Todo, utcnow
from backend.features.sharing.access import visible_condition

router = APIRouter(prefix="/api/platform", tags=["平台"], responses=ERROR_RESPONSES)
SUMMARY_LIMIT = 5


def settings_output(user, has_todos):
    return PlatformSettings(
        id=user.id,
        email=user.email,
        nickname=user.nickname,
        timezone=user.timezone,
        has_todos=has_todos,
    )


@router.get("/settings", response_model=PlatformSettings)
def get_settings(user: Principal, session: DB):
    has_todos = (
        session.scalar(select(Todo.id).where(Todo.owner_id == user.id).limit(1))
        is not None
    )
    return settings_output(user, has_todos)


@router.patch("/settings", response_model=PlatformSettings)
def update_settings(body: PlatformSettingsPatch, user: Principal, session: DB):
    try:
        if body.nickname is not None and body.nickname != user.nickname:
            user.nickname = body.nickname
            session.execute(
                update(HouseholdParticipant)
                .where(HouseholdParticipant.account_id == user.id)
                .values(display_name=body.nickname)
            )
        if body.timezone is not None and body.timezone != user.timezone:
            todos = session.scalars(
                select(Todo).where(Todo.owner_id == user.id).with_for_update()
            )
            for todo in todos:
                todo.timezone = body.timezone
                if todo.due_time is not None:
                    todo.due_at = datetime.combine(
                        todo.due_date, todo.due_time, ZoneInfo(body.timezone)
                    ).astimezone(UTC)
            user.timezone = body.timezone
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise
    return get_settings(user, session)


@router.get("/home", response_model=PlatformHome)
def home(user: Principal, session: DB):
    now = utcnow()
    day = now.astimezone(ZoneInfo(user.timezone)).date()
    effective = func.coalesce(
        Todo.due_at,
        func.timezone(
            user.timezone, cast(Todo.due_date, DateTime) + text("interval '1 day'")
        ),
    )
    base = (visible_condition(Todo, user.id), Todo.status == "ongoing")
    today_filter = (*base, Todo.due_date == day)
    overdue_filter = (*base, effective <= now)

    def summary(filters):
        count = session.scalar(select(func.count()).select_from(Todo).where(*filters))
        items = session.scalars(
            select(Todo)
            .where(*filters)
            .order_by(effective.asc(), Todo.created_at.desc(), Todo.id.asc())
            .limit(SUMMARY_LIMIT)
        )
        return TodoSummary(
            count=count or 0, items=[output(todo, now) for todo in items]
        )

    recent = session.scalars(
        select(Todo)
        .where(visible_condition(Todo, user.id))
        .order_by(Todo.updated_at.desc(), Todo.id.asc())
        .limit(SUMMARY_LIMIT)
    )
    recent_events = session.scalars(
        select(CalendarEvent)
        .where(visible_condition(CalendarEvent, user.id))
        .order_by(CalendarEvent.updated_at.desc(), CalendarEvent.id.asc())
        .limit(SUMMARY_LIMIT)
    )
    return PlatformHome(
        timezone=user.timezone,
        server_time=now,
        today=summary(today_filter),
        overdue=summary(overdue_filter),
        recent=[output(todo, now) for todo in recent],
        recent_events=[event_output(event) for event in recent_events],
    )
