from datetime import UTC, datetime, time, timedelta
from typing import Annotated
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query
from sqlalchemy import select

from backend.api.calendar_schemas import (
    EventBatchDelete,
    EventCreate,
    EventList,
    EventOut,
    EventPatch,
    EventQuery,
)
from backend.api.schemas import ERROR_RESPONSES
from backend.core.security import DB, APIError, Principal
from backend.db.models import CalendarEvent, Todo, utcnow
from backend.features.sharing.access import visible_condition
from backend.features.sharing.cleanup import delete_resource

router = APIRouter(
    prefix="/api/calendar/events", tags=["本地日程"], responses=ERROR_RESPONSES
)


def local_fields(event):
    zone = ZoneInfo(event.timezone)
    start = event.starts_at.astimezone(zone)
    end = event.ends_at.astimezone(zone)
    return start.date(), start.strftime("%H:%M"), end.date(), end.strftime("%H:%M")


def output(event):
    start_date, start_time, end_date, end_time = local_fields(event)
    return EventOut(
        id=event.id,
        title=event.title,
        description=event.description,
        location=event.location,
        todo_id=event.todo_id,
        series_id=event.series_id,
        source=event.source,
        status=event.status,
        assignee_id=event.owner_id,
        start_date=start_date,
        start_time=start_time,
        end_date=end_date,
        end_time=end_time,
        timezone=event.timezone,
        starts_at=event.starts_at,
        ends_at=event.ends_at,
        created_at=event.created_at,
        updated_at=event.updated_at,
    )


def owned(session, user, event_id, lock=False):
    statement = select(CalendarEvent).where(
        visible_condition(CalendarEvent, user.id), CalendarEvent.id == event_id
    )
    event = session.scalar(statement.with_for_update() if lock else statement)
    if event is None:
        raise APIError(404, "EVENT_NOT_FOUND", "该日程不存在或无法访问")
    return event


def values(body, timezone):
    zone = ZoneInfo(timezone)
    return {
        "title": body.title,
        "description": body.description,
        "location": body.location,
        "timezone": timezone,
        "status": body.status,
        "starts_at": datetime.combine(
            body.start_date, time.fromisoformat(body.start_time), zone
        ).astimezone(UTC),
        "ends_at": datetime.combine(
            body.end_date, time.fromisoformat(body.end_time), zone
        ).astimezone(UTC),
    }


@router.post("", response_model=EventOut, status_code=201)
def create(body: EventCreate, user: Principal, session: DB):
    if (
        body.todo_id
        and session.scalar(
            select(Todo.id).where(
                Todo.id == body.todo_id, visible_condition(Todo, user.id)
            )
        )
        is None
    ):
        raise APIError(404, "TODO_NOT_FOUND", "关联待办不存在或无法访问")
    interval = timedelta(days=1 if body.recurrence == "daily" else 7)
    dates = [body.start_date]
    while body.recurrence != "none" and dates[-1] + interval <= body.recurrence_until:
        dates.append(dates[-1] + interval)
    series_id = uuid4() if len(dates) > 1 else None
    event = None
    duration = body.end_date - body.start_date
    for start_date in dates:
        copy = body.model_copy(
            update={"start_date": start_date, "end_date": start_date + duration}
        )
        current = CalendarEvent(
            owner_id=user.id,
            todo_id=body.todo_id,
            series_id=series_id,
            source="app",
            **values(copy, user.timezone),
        )
        session.add(current)
        event = event or current
    session.commit()
    return output(event)


@router.get("", response_model=EventList)
def listing(query: Annotated[EventQuery, Query()], user: Principal, session: DB):
    zone = ZoneInfo(user.timezone)
    start = datetime.combine(query.date_from, time(), zone).astimezone(UTC)
    end = datetime.combine(query.date_to + timedelta(days=1), time(), zone).astimezone(
        UTC
    )
    rows = session.scalars(
        select(CalendarEvent)
        .where(
            visible_condition(CalendarEvent, user.id),
            CalendarEvent.starts_at < end,
            CalendarEvent.ends_at > start,
        )
        .order_by(CalendarEvent.starts_at, CalendarEvent.id)
    )
    return EventList(items=[output(row) for row in rows])


def list_all(user: Principal, session: DB):
    rows = list(
        session.scalars(
            select(CalendarEvent)
            .where(visible_condition(CalendarEvent, user.id))
            .order_by(CalendarEvent.starts_at, CalendarEvent.id)
            .limit(51)
        )
    )
    if len(rows) > 50:
        raise APIError(
            422,
            "TOO_MANY_EVENTS",
            "全部时间日程超过50条，请指定日期范围查询，当前未返回完整列表",
        )
    return EventList(items=[output(row) for row in rows])


@router.get("/{event_id}", response_model=EventOut)
def detail(event_id: UUID, user: Principal, session: DB):
    return output(owned(session, user, event_id))


@router.put("/{event_id}", response_model=EventOut)
def update(event_id: UUID, body: EventPatch, user: Principal, session: DB):
    event = owned(session, user, event_id, lock=True)
    for key, value in values(body, user.timezone).items():
        setattr(event, key, value)
    event.updated_at = utcnow()
    session.commit()
    return output(event)


@router.delete("/{event_id}", status_code=204)
def remove(event_id: UUID, user: Principal, session: DB):
    event = owned(session, user, event_id, lock=True)
    delete_resource(session, event)
    session.commit()


def remove_batch(
    body: EventBatchDelete, user: Principal, session: DB
) -> dict[str, int]:
    zone = ZoneInfo(user.timezone)
    start = datetime.combine(body.date_from, time(), zone).astimezone(UTC)
    end = datetime.combine(body.date_to + timedelta(days=1), time(), zone).astimezone(
        UTC
    )
    events = list(
        session.scalars(
            select(CalendarEvent)
            .where(
                visible_condition(CalendarEvent, user.id),
                CalendarEvent.id.in_(body.event_ids),
                CalendarEvent.starts_at < end,
                CalendarEvent.ends_at > start,
            )
            .with_for_update()
        )
    )
    if len(events) != len(set(body.event_ids)):
        raise APIError(404, "EVENT_NOT_FOUND", "部分日程不存在或无法访问")
    for event in events:
        delete_resource(session, event)
    session.commit()
    return {"count": len(events)}
