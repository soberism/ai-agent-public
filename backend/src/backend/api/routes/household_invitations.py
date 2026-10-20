from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import select

from backend.api.household_schemas import InvitationCreate, InvitationOut
from backend.api.routes.households import invitation_out, participant
from backend.core.security import DB, APIError, Principal
from backend.db.household_models import HouseholdParticipant, Notification
from backend.db.models import User, utcnow

router = APIRouter(tags=["家庭邀请"])


@router.post(
    "/{household_id}/invitations", response_model=InvitationOut, status_code=201
)
def invite(household_id: UUID, body: InvitationCreate, user: Principal, session: DB):
    participant(session, user, household_id, members=True)
    existing = session.scalar(
        select(HouseholdParticipant)
        .where(
            HouseholdParticipant.household_id == household_id,
            HouseholdParticipant.email == body.email,
        )
        .with_for_update()
    )
    if existing and existing.status in ("pending", "active"):
        raise APIError(409, "INVITATION_EXISTS", "该邮箱已在家庭中或已有待接受邀请")
    account = session.scalar(select(User).where(User.email == body.email, User.active))
    row = existing or HouseholdParticipant(household_id=household_id, email=body.email)
    row.account_id = account.id if account else None
    row.display_name = (
        account.nickname if account and account.nickname else body.email.split("@")[0]
    )
    row.role = body.role
    row.status = "pending"
    row.permissions = []
    row.invited_by = user.id
    row.expires_at = utcnow() + timedelta(days=7)
    row.accepted_at = None
    session.add(row)
    session.flush()
    if account:
        session.add(
            Notification(
                recipient_id=account.id,
                household_id=household_id,
                invitation_id=row.id,
                kind="invitation",
                title="家庭邀请",
                message="你收到一个待处理的家庭邀请",
            )
        )
    session.commit()
    return invitation_out(row)


@router.post("/invitations/{invitation_id}/{decision}", response_model=InvitationOut)
def decide(
    invitation_id: UUID,
    decision: str,
    user: Principal,
    session: DB,
):
    if decision not in ("accept", "reject"):
        raise APIError(404, "INVITATION_ACTION_NOT_FOUND", "不支持的邀请操作")
    row = session.scalar(
        select(HouseholdParticipant)
        .where(
            HouseholdParticipant.id == invitation_id,
            HouseholdParticipant.email == user.email,
            HouseholdParticipant.status == "pending",
            HouseholdParticipant.role.in_(("owner", "admin", "member")),
        )
        .with_for_update()
    )
    if row is None or row.expires_at <= utcnow():
        raise APIError(404, "INVITATION_NOT_FOUND", "邀请不存在、已处理或已失效")
    row.status = "active" if decision == "accept" else "rejected"
    row.account_id = user.id if decision == "accept" else row.account_id
    if decision == "accept" and user.nickname:
        row.display_name = user.nickname
    row.accepted_at = utcnow() if decision == "accept" else None
    for notification in session.scalars(
        select(Notification).where(
            Notification.recipient_id == user.id,
            Notification.invitation_id == row.id,
            Notification.kind == "invitation",
        )
    ):
        notification.read_at = notification.read_at or utcnow()
    session.add(
        Notification(
            recipient_id=row.invited_by,
            household_id=row.household_id,
            invitation_id=row.id,
            kind="invitation_result",
            title="家庭邀请已处理",
            message=f"{row.email}已{'接受' if decision == 'accept' else '拒绝'}邀请",
        )
    )
    session.commit()
    return invitation_out(row)
