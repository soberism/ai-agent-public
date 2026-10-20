"""Atomic creation of one household-visible event after assistant confirmation."""

from uuid import UUID

from sqlalchemy import select

from backend.api.calendar_schemas import EventCreate, EventOut
from backend.api.planning_schemas import ChecklistOut, ChecklistWithItemsCreate
from backend.api.routes.calendar_events import output, values
from backend.api.routes.planning_checklists import checklist_output
from backend.api.routes.sharing import SharingSettings, save_settings
from backend.core.security import DB, APIError, Principal
from backend.db.household_models import HouseholdParticipant
from backend.db.models import CalendarEvent, Checklist, ChecklistItem


def create_shared_event(
    household_id: UUID, body: EventCreate, user: Principal, session: DB
) -> EventOut:
    if body.recurrence != "none" or body.todo_id is not None:
        raise APIError(422, "INVALID_ACTION", "请单独处理重复日程或关联待办")
    member = session.scalar(
        select(HouseholdParticipant.id).where(
            HouseholdParticipant.household_id == household_id,
            HouseholdParticipant.account_id == user.id,
            HouseholdParticipant.status == "active",
            HouseholdParticipant.role.in_(("owner", "admin", "member")),
        )
    )
    if member is None:
        raise APIError(422, "INVALID_HOUSEHOLD", "家庭不存在或已无法访问")
    try:
        event = CalendarEvent(
            owner_id=user.id,
            household_id=household_id,
            source="app",
            **values(body, user.timezone),
        )
        session.add(event)
        session.flush()
        save_settings(
            session,
            "event",
            event.id,
            SharingSettings(scope="household", household_id=household_id),
        )
        session.commit()
        return output(event)
    except Exception:
        session.rollback()
        raise


def create_shared_checklist(
    household_id: UUID, body: ChecklistWithItemsCreate, user: Principal, session: DB
) -> ChecklistOut:
    member = session.scalar(
        select(HouseholdParticipant.id).where(
            HouseholdParticipant.household_id == household_id,
            HouseholdParticipant.account_id == user.id,
            HouseholdParticipant.status == "active",
            HouseholdParticipant.role.in_(("owner", "admin", "member")),
        )
    )
    if member is None:
        raise APIError(422, "INVALID_HOUSEHOLD", "家庭不存在或已无法访问")
    try:
        checklist = Checklist(owner_id=user.id, title=body.title)
        session.add(checklist)
        session.flush()
        session.add_all(
            [
                ChecklistItem(checklist_id=checklist.id, title=title, position=index)
                for index, title in enumerate(body.items)
            ]
        )
        save_settings(
            session,
            "checklist",
            checklist.id,
            SharingSettings(scope="household", household_id=household_id),
        )
        session.commit()
        return checklist_output(session, checklist)
    except Exception:
        session.rollback()
        raise
