import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from sqlalchemy import select

from backend.api.life_schemas import AppointmentCreate, AppointmentList, AppointmentOut
from backend.api.schemas import ERROR_RESPONSES
from backend.core.security import DB, APIError, Principal
from backend.db.life_models import MedicalAppointment
from backend.db.models import CalendarEvent, Todo
from backend.features.sharing.access import (
    accessible,
    inherit_sharing,
    visible_condition,
)

router = APIRouter(
    prefix="/api/life/appointments", tags=["医疗安排"], responses=ERROR_RESPONSES
)


def preferred_at(row, timezone):
    return datetime.combine(row.scheduled_date, row.scheduled_time, ZoneInfo(timezone))


def output(row, timezone):
    return AppointmentOut(
        id=row.id,
        patient_name=row.patient_name,
        institution=row.provider_name,
        service_type=row.service_type,
        preferred_at=preferred_at(row, timezone),
        status=row.status,
        fee_note=row.notes,
        external_receipt=None,
        calendar_url=f"/calendar/{row.event_id}/edit" if row.event_id else None,
        todo_url=f"/todos/{row.todo_id}" if row.todo_id else None,
    )


def owned(session, user, appointment_id, lock=False):
    statement = select(MedicalAppointment).where(
        MedicalAppointment.id == appointment_id,
        visible_condition(MedicalAppointment, user.id),
    )
    row = session.scalar(statement.with_for_update() if lock else statement)
    if row is None:
        raise APIError(404, "APPOINTMENT_NOT_FOUND", "医疗安排不存在或无法访问")
    return row


@router.get("", response_model=AppointmentList)
def listing(user: Principal, session: DB):
    rows = session.scalars(
        select(MedicalAppointment)
        .where(visible_condition(MedicalAppointment, user.id))
        .order_by(MedicalAppointment.scheduled_date, MedicalAppointment.id)
    )
    return AppointmentList(items=[output(row, user.timezone) for row in rows])


@router.post("", response_model=AppointmentOut, status_code=201)
def create(body: AppointmentCreate, user: Principal, session: DB):
    local = body.preferred_at.astimezone(ZoneInfo(user.timezone))
    row = MedicalAppointment(
        owner_id=user.id,
        patient_name=body.patient_name,
        provider_name=body.institution,
        service_type=body.service_type,
        scheduled_date=local.date(),
        scheduled_time=local.time().replace(tzinfo=None),
        notes=body.fee_note,
        status="planned",
    )
    session.add(row)
    session.commit()
    return output(row, user.timezone)


@router.post("/{appointment_id}/confirm", response_model=AppointmentOut)
def confirm(appointment_id: UUID, user: Principal, session: DB):
    row = owned(session, user, appointment_id, lock=True)
    starts_at = preferred_at(row, user.timezone).astimezone(UTC)
    if row.event_id is None:
        event = CalendarEvent(
            owner_id=row.owner_id,
            todo_id=None,
            series_id=None,
            title=f"医疗安排：{row.service_type}"[:15],
            description=f"就诊人：{row.patient_name}",
            location=row.provider_name,
            source="life",
            status="scheduled",
            timezone=user.timezone,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=1),
        )
        session.add(event)
        session.flush()
        row.event_id = event.id
        inherit_sharing(session, "appointment", row.id, "event", event.id)
    if row.todo_id is None:
        key = uuid4()
        todo = Todo(
            owner_id=row.owner_id,
            title=f"准备{row.patient_name}的就诊材料"[:15],
            description=f"机构：{row.provider_name}",
            due_date=row.scheduled_date,
            due_time=None,
            timezone=user.timezone,
            due_at=None,
            status="ongoing",
            completed_at=None,
            create_key=key,
            create_fingerprint=hashlib.sha256(str(key).encode()).hexdigest(),
        )
        session.add(todo)
        session.flush()
        row.todo_id = todo.id
        inherit_sharing(session, "appointment", row.id, "todo", todo.id)
    session.commit()
    return output(row, user.timezone)


@router.put("/{appointment_id}", response_model=AppointmentOut)
def update(
    appointment_id: UUID,
    body: AppointmentCreate,
    user: Principal,
    session: DB,
):
    row = owned(session, user, appointment_id, lock=True)
    local = body.preferred_at.astimezone(ZoneInfo(user.timezone))
    row.patient_name = body.patient_name
    row.provider_name = body.institution
    row.service_type = body.service_type
    row.scheduled_date = local.date()
    row.scheduled_time = local.time().replace(tzinfo=None)
    row.notes = body.fee_note
    starts_at = local.astimezone(UTC)
    if row.event_id:
        event = accessible(session, user, CalendarEvent, row.event_id, lock=True)
        event.title = f"医疗安排：{row.service_type}"
        event.description = f"就诊人：{row.patient_name}"
        event.location = row.provider_name
        event.starts_at = starts_at
        event.ends_at = starts_at + timedelta(hours=1)
    if row.todo_id:
        todo = accessible(session, user, Todo, row.todo_id, lock=True)
        todo.title = f"准备{row.patient_name}的就诊材料"
        todo.description = f"机构：{row.provider_name}"
        todo.due_date = row.scheduled_date
    session.commit()
    return output(row, user.timezone)


@router.delete("/{appointment_id}", status_code=204)
def cancel(appointment_id: UUID, user: Principal, session: DB):
    row = owned(session, user, appointment_id, lock=True)
    row.status = "cancelled"
    if row.event_id:
        accessible(
            session, user, CalendarEvent, row.event_id, lock=True
        ).status = "cancelled"
    session.commit()
