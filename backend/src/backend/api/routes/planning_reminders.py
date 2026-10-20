from datetime import UTC, datetime, time
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from sqlalchemy import select

from backend.api.planning_schemas import ReminderCreate, ReminderOut, ReminderPatch
from backend.api.schemas import ERROR_RESPONSES
from backend.core.security import DB, APIError, Principal
from backend.db.models import CalendarEvent, Reminder, Todo
from backend.features.sharing.access import visible_condition
from backend.features.sharing.cleanup import delete_resource

router = APIRouter(responses=ERROR_RESPONSES)


def reminder_output(reminder):
    return ReminderOut(
        id=reminder.id,
        todo_id=reminder.todo_id,
        event_id=reminder.event_id,
        remind_at=reminder.remind_at,
        timezone=reminder.timezone,
        status=reminder.status,
    )


@router.get("/reminders", response_model=list[ReminderOut])
def list_reminders(user: Principal, session: DB):
    rows = session.scalars(
        select(Reminder)
        .where(visible_condition(Reminder, user.id))
        .order_by(Reminder.remind_at, Reminder.id)
    )
    return [reminder_output(row) for row in rows]


@router.post("/reminders", response_model=ReminderOut, status_code=201)
def create_reminder(body: ReminderCreate, user: Principal, session: DB):
    model, subject_id = (
        (Todo, body.todo_id) if body.todo_id else (CalendarEvent, body.event_id)
    )
    if (
        session.scalar(
            select(model.id).where(
                model.id == subject_id, visible_condition(model, user.id)
            )
        )
        is None
    ):
        raise APIError(404, "SUBJECT_NOT_FOUND", "关联事项不存在或无法访问")
    reminder = Reminder(
        owner_id=user.id,
        todo_id=body.todo_id,
        event_id=body.event_id,
        remind_at=datetime.combine(
            body.remind_date,
            time.fromisoformat(body.remind_time),
            ZoneInfo(user.timezone),
        ).astimezone(UTC),
        timezone=user.timezone,
        status="scheduled",
    )
    session.add(reminder)
    session.commit()
    return reminder_output(reminder)


def owned_reminder(session, user, reminder_id):
    value = session.scalar(
        select(Reminder).where(
            Reminder.id == reminder_id, visible_condition(Reminder, user.id)
        )
    )
    if value is None:
        raise APIError(404, "REMINDER_NOT_FOUND", "该提醒不存在或无法访问")
    return value


@router.patch("/reminders/{reminder_id}", response_model=ReminderOut)
def update_reminder(
    reminder_id: UUID, body: ReminderPatch, user: Principal, session: DB
):
    reminder = owned_reminder(session, user, reminder_id)
    reminder.status = body.status
    session.commit()
    return reminder_output(reminder)


@router.delete("/reminders/{reminder_id}", status_code=204)
def delete_reminder(reminder_id: UUID, user: Principal, session: DB):
    delete_resource(session, owned_reminder(session, user, reminder_id))
    session.commit()
