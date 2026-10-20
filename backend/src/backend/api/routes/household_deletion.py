from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import select, update

from backend.core.security import DB, APIError, Principal
from backend.db.household_models import Household, HouseholdParticipant
from backend.db.models import Todo
from backend.db.parity_models import HouseholdAudit

router = APIRouter(tags=["家庭"])


@router.delete("/{household_id}", status_code=204)
def delete_household(household_id: UUID, user: Principal, session: DB):
    home = session.scalar(
        select(Household)
        .where(Household.id == household_id, Household.owner_id == user.id)
        .with_for_update()
    )
    if home is None:
        raise APIError(404, "HOUSEHOLD_NOT_FOUND", "家庭不存在或无法管理")
    # Business items survive; family-specific relationships cascade in the DB.
    session.execute(
        update(Todo)
        .where(Todo.household_id == home.id)
        .values(
            household_id=None,
            assignee_id=None,
            assignment_status="personal",
            assignment_note=None,
        )
    )
    session.delete(home)
    session.commit()


@router.post("/{household_id}/leave", status_code=204)
def leave_household(household_id: UUID, user: Principal, session: DB):
    home = session.scalar(
        select(Household).where(Household.id == household_id).with_for_update()
    )
    if home is None:
        raise APIError(404, "HOUSEHOLD_NOT_FOUND", "家庭不存在或无法访问")
    member = session.scalar(
        select(HouseholdParticipant)
        .where(
            HouseholdParticipant.household_id == household_id,
            HouseholdParticipant.account_id == user.id,
            HouseholdParticipant.status == "active",
            HouseholdParticipant.role.in_(("owner", "admin", "member")),
        )
        .with_for_update()
    )
    if member is None:
        raise APIError(404, "HOUSEHOLD_NOT_FOUND", "家庭不存在或无法访问")
    if home.owner_id == user.id:
        raise APIError(
            409, "HOUSEHOLD_OWNER_CANNOT_LEAVE", "家庭创建者不能退出，请使用删除家庭"
        )
    member.status = "removed"
    session.add(
        HouseholdAudit(
            household_id=household_id,
            actor_id=user.id,
            action="member_left",
            detail={"member_id": str(member.id)},
        )
    )
    session.commit()
