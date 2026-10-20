from datetime import UTC, datetime, time, timedelta
from datetime import date as Date
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query
from pydantic import BaseModel, model_validator
from sqlalchemy import select

from backend.api.schemas import ERROR_RESPONSES
from backend.core.security import DB, Principal
from backend.db.models import CalendarEvent, Checklist, ChecklistItem, Todo
from backend.features.sharing.access import visible_condition

router = APIRouter(
    prefix="/api/planning/review", tags=["计划回顾"], responses=ERROR_RESPONSES
)


class ReviewQuery(BaseModel):
    date: Date | None = None
    range: Literal["day", "week"] = "day"
    date_from: Date | None = None
    date_to: Date | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.date_from is not None or self.date_to is not None:
            if self.date is not None or self.date_from is None or self.date_to is None:
                raise ValueError("请提供完整起止日期，不要同时提供旧日期参数")
        elif self.date is not None:
            days = 6 if self.range == "week" else 0
            if self.date > Date.max - timedelta(days=days + 1):
                raise ValueError("结束日期超出支持范围")
            self.date_from = self.date
            self.date_to = self.date + timedelta(days=days)
        else:
            raise ValueError("请选择起止日期")
        if self.date_from > self.date_to or (self.date_to - self.date_from).days > 365:
            raise ValueError("结束日期不能早于开始日期，范围不能超过一年")
        if self.date_to == Date.max:
            raise ValueError("结束日期超出支持范围")
        return self


def todo_item(todo):
    return {"id": str(todo.id), "title": todo.title, "due_date": todo.due_date}


def event_item(event):
    return {
        "id": str(event.id),
        "title": event.title,
        "starts_at": event.starts_at,
        "ends_at": event.ends_at,
    }


@router.get("")
def review(query: Annotated[ReviewQuery, Query()], user: Principal, session: DB):
    zone = ZoneInfo(user.timezone)
    start_date = query.date_from
    start = datetime.combine(start_date, time(), zone).astimezone(UTC)
    end_date = query.date_to + timedelta(days=1)
    end = datetime.combine(end_date, time(), zone).astimezone(UTC)
    todos = list(session.scalars(select(Todo).where(visible_condition(Todo, user.id))))
    events = list(
        session.scalars(
            select(CalendarEvent)
            .where(
                visible_condition(CalendarEvent, user.id),
                CalendarEvent.starts_at < end,
                CalendarEvent.ends_at > start,
            )
            .order_by(CalendarEvent.starts_at, CalendarEvent.id)
        )
    )
    completed = [
        todo for todo in todos if todo.completed_at and start <= todo.completed_at < end
    ]
    ongoing = [
        todo
        for todo in todos
        if todo.status == "ongoing"
        and todo.due_date
        and start_date <= todo.due_date < end_date
    ]
    overdue = [
        todo
        for todo in todos
        if todo.status == "ongoing" and todo.due_date and todo.due_date < start_date
    ]
    unscheduled = [
        todo for todo in todos if todo.status == "ongoing" and not todo.due_date
    ]
    conflicts = []
    # ponytail: O(n²) within a maximum one-year range; use a sweep line if event volume grows.
    for index, left in enumerate(events):
        for right in events[index + 1 :]:
            if right.starts_at >= left.ends_at:
                break
            if left.starts_at < right.ends_at and right.starts_at < left.ends_at:
                conflicts.append({"left": event_item(left), "right": event_item(right)})
    checklist_rows = list(
        session.execute(
            select(Checklist.id, Checklist.title, ChecklistItem.completed)
            .join(
                ChecklistItem, ChecklistItem.checklist_id == Checklist.id, isouter=True
            )
            .where(visible_condition(Checklist, user.id))
        )
    )
    checklist_total = len({row.id for row in checklist_rows})
    checklist_open_items = sum(row.completed is False for row in checklist_rows)
    return {
        "date_from": start_date,
        "date_to": end_date - timedelta(days=1),
        "range": query.range,
        "summary": {
            "completed_todos": len(completed),
            "ongoing_todos": len(ongoing),
            "events": len(events),
            "checklists": checklist_total,
            "open_checklist_items": checklist_open_items,
        },
        "details": {
            "completed": [todo_item(todo) for todo in completed],
            "ongoing": [todo_item(todo) for todo in ongoing],
            "events": [event_item(event) for event in events],
        },
        "organize": {
            "overdue": [todo_item(todo) for todo in overdue],
            "unscheduled": [todo_item(todo) for todo in unscheduled],
            "conflicts": conflicts,
        },
    }
