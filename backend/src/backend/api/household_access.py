from sqlalchemy import select

from backend.core.security import APIError
from backend.db.household_models import Household, HouseholdParticipant


def participant(session, user, household_id, manage=False, members=False):
    row = session.scalar(
        select(HouseholdParticipant).where(
            HouseholdParticipant.household_id == household_id,
            HouseholdParticipant.account_id == user.id,
            HouseholdParticipant.status == "active",
            HouseholdParticipant.role.in_(("owner", "admin", "member")),
        )
    )
    if row is None or (
        (manage and session.get(Household, household_id).owner_id != user.id)
        or (members and row.role not in ("owner", "admin"))
    ):
        raise APIError(404, "HOUSEHOLD_NOT_FOUND", "该家庭不存在或无法访问")
    return row
