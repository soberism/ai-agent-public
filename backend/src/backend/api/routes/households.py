from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import func, select

from backend.api.household_access import participant
from backend.api.household_schemas import (
    HouseholdCreate,
    HouseholdDetail,
    HouseholdList,
    HouseholdOut,
    InvitationOut,
    MemberOut,
    MemberPatch,
    PetOut,
    ProfileOut,
)
from backend.api.schemas import ERROR_RESPONSES
from backend.core.security import DB, APIError, Principal
from backend.db.household_models import (
    Household,
    HouseholdParticipant,
    HouseholdProfile,
    Notification,
    Pet,
)
from backend.db.models import Todo, utcnow
from backend.db.parity_models import HouseholdAudit

router = APIRouter(prefix="/api/households", tags=["家庭"], responses=ERROR_RESPONSES)


def summary(session, household, member):
    count = session.scalar(
        select(func.count()).where(
            HouseholdParticipant.household_id == household.id,
            HouseholdParticipant.status == "active",
            HouseholdParticipant.role.in_(("owner", "admin", "member")),
        )
    )
    return HouseholdOut(
        id=household.id, name=household.name, role=member.role, member_count=count
    )


def invitation_out(row):
    return InvitationOut(
        id=row.id,
        email=row.email,
        role=row.role,
        status=row.status,
        expires_at=row.expires_at,
    )


@router.get("", response_model=HouseholdList)
def listing(user: Principal, session: DB):
    rows = session.execute(
        select(Household, HouseholdParticipant)
        .join(HouseholdParticipant, HouseholdParticipant.household_id == Household.id)
        .where(
            HouseholdParticipant.account_id == user.id,
            HouseholdParticipant.status == "active",
            HouseholdParticipant.role.in_(("owner", "admin", "member")),
        )
        .order_by(Household.created_at, Household.id)
    )
    return HouseholdList(
        items=[summary(session, home, member) for home, member in rows]
    )


@router.post("", response_model=HouseholdOut, status_code=201)
def create(body: HouseholdCreate, user: Principal, session: DB):
    home = Household(owner_id=user.id, name=body.name)
    session.add(home)
    session.flush()
    member = HouseholdParticipant(
        household_id=home.id,
        account_id=user.id,
        display_name=user.nickname or user.email.split("@")[0],
        email=user.email,
        role="owner",
        status="active",
        permissions=[],
        invited_by=user.id,
        accepted_at=utcnow(),
    )
    session.add(member)
    session.commit()
    return summary(session, home, member)


@router.get("/invitations/incoming")
def incoming_invitations(user: Principal, session: DB):
    rows = session.execute(
        select(HouseholdParticipant, Household.name)
        .join(Household, Household.id == HouseholdParticipant.household_id)
        .where(
            HouseholdParticipant.email == user.email,
            HouseholdParticipant.status == "pending",
            HouseholdParticipant.role == "member",
            HouseholdParticipant.expires_at > utcnow(),
        )
    )
    return {
        "items": [
            {
                "id": row.id,
                "household_name": name,
                "role": row.role,
                "expires_at": row.expires_at,
            }
            for row, name in rows
        ]
    }


@router.get("/{household_id}", response_model=HouseholdDetail)
def detail(household_id: UUID, user: Principal, session: DB):
    current = participant(session, user, household_id)
    home = session.get(Household, household_id)
    rows = list(
        session.scalars(
            select(HouseholdParticipant)
            .where(HouseholdParticipant.household_id == household_id)
            .order_by(HouseholdParticipant.created_at, HouseholdParticipant.id)
        )
    )
    visible_members = [
        row
        for row in rows
        if row.status == "active" and row.role in ("owner", "admin", "member")
    ]
    profiles = list(
        session.scalars(
            select(HouseholdProfile).where(
                HouseholdProfile.household_id == household_id
            )
        )
    )
    pets = list(session.scalars(select(Pet).where(Pet.household_id == household_id)))
    base = summary(session, home, current)
    return HouseholdDetail(
        **base.model_dump(),
        members=[
            MemberOut(
                id=row.id,
                account_id=row.account_id,
                display_name=row.display_name,
                email=row.email,
                role=row.role,
                status=row.status,
                permissions=row.permissions,
            )
            for row in visible_members
        ],
        invitations=[
            invitation_out(row)
            for row in rows
            if row.status == "pending" and row.role == "member"
        ],
        profiles=[
            ProfileOut.model_validate(row, from_attributes=True) for row in profiles
        ],
        pets=[PetOut.model_validate(row, from_attributes=True) for row in pets],
    )


@router.patch("/{household_id}/members/{member_id}", response_model=MemberOut)
def update_member(
    household_id: UUID,
    member_id: UUID,
    body: MemberPatch,
    user: Principal,
    session: DB,
):
    current = participant(session, user, household_id, members=True)
    if current.role != "owner" and body.model_dump(exclude_unset=True) != {
        "status": "removed"
    }:
        raise APIError(404, "HOUSEHOLD_NOT_FOUND", "仅家庭创建者可以修改角色或权限")
    row = session.scalar(
        select(HouseholdParticipant)
        .where(
            HouseholdParticipant.id == member_id,
            HouseholdParticipant.household_id == household_id,
            HouseholdParticipant.role != "owner",
        )
        .with_for_update()
    )
    if row is None:
        raise APIError(404, "MEMBER_NOT_FOUND", "成员不存在或无法修改")
    before = {"role": row.role, "status": row.status, "permissions": row.permissions}
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    if row.account_id:
        session.add(
            Notification(
                recipient_id=row.account_id,
                household_id=household_id,
                invitation_id=None,
                kind="permission_changed",
                title="家庭权限已更新",
                message="你的家庭角色或权限已发生变化",
            )
        )
    session.add(
        HouseholdAudit(
            household_id=household_id,
            actor_id=user.id,
            action="member_updated",
            detail={
                "member_id": str(row.id),
                "before": before,
                "after": body.model_dump(exclude_unset=True),
            },
        )
    )
    session.commit()
    return MemberOut(
        id=row.id,
        account_id=row.account_id,
        display_name=row.display_name,
        email=row.email,
        role=row.role,
        status=row.status,
        permissions=row.permissions,
    )


@router.get("/{household_id}/members/{member_id}/removal-impact")
def removal_impact(household_id: UUID, member_id: UUID, user: Principal, session: DB):
    participant(session, user, household_id, members=True)
    row = session.scalar(
        select(HouseholdParticipant).where(
            HouseholdParticipant.id == member_id,
            HouseholdParticipant.household_id == household_id,
            HouseholdParticipant.role != "owner",
        )
    )
    if row is None:
        raise APIError(404, "MEMBER_NOT_FOUND", "成员不存在或无法修改")
    assigned = (
        session.scalar(
            select(func.count()).where(
                Todo.household_id == household_id,
                Todo.assignee_id == row.account_id,
                Todo.status == "ongoing",
            )
        )
        if row.account_id
        else 0
    )
    return {
        "member_id": row.id,
        "assigned_todos": assigned,
        "message": f"移出后将失去家庭访问权；{assigned} 项未完成指派会保留并等待重新分配。",
    }


@router.get("/{household_id}/audit")
def audit(household_id: UUID, user: Principal, session: DB):
    participant(session, user, household_id, manage=True)
    return [
        {
            "id": row.id,
            "action": row.action,
            "detail": row.detail,
            "created_at": row.created_at,
        }
        for row in session.scalars(
            select(HouseholdAudit)
            .where(HouseholdAudit.household_id == household_id)
            .order_by(HouseholdAudit.created_at.desc())
            .limit(50)
        )
    ]


from backend.api.routes.household_invitations import router as invitation_router

router.include_router(invitation_router)

from backend.api.routes.household_summary import router as summary_router

router.include_router(summary_router)
