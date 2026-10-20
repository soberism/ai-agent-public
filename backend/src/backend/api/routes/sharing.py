from typing import Literal
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete, select

from backend.api.routes.sharing_states import router as states_router
from backend.core.security import DB, APIError, Principal
from backend.db.household_models import Household, HouseholdParticipant
from backend.db.life_models import ShoppingList
from backend.db.models import Checklist
from backend.db.sharing_models import ItemSharing, ItemSharingMember
from backend.features.sharing.access import RESOURCE_MODELS, accessible
from backend.features.sharing.linked import linked_resources

router = APIRouter(prefix="/api/sharing", tags=["成员权限"])
router.include_router(states_router)


class SharingSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: Literal["private", "household", "members"] = "private"
    household_id: UUID | None = None
    member_ids: list[UUID] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def valid_target(self):
        if self.scope != "private" and self.household_id is None:
            raise ValueError("家庭可见或指定成员可见时必须选择家庭")
        if self.scope == "members" and not self.member_ids:
            raise ValueError("指定成员可见时必须选择至少一位家庭成员")
        return self


def resource(session, user, kind, resource_id, lock=False):
    model = RESOURCE_MODELS.get(kind)
    if model is None or kind == "folder":
        raise APIError(404, "RESOURCE_NOT_FOUND", "不支持的内容类型")
    return accessible(session, user, model, resource_id, lock=lock)


def settings_out(session, kind, resource_id):
    row = session.get(ItemSharing, (kind, resource_id))
    if row is None or row.scope == "helpers":
        return SharingSettings()
    ids = list(
        session.scalars(
            select(ItemSharingMember.account_id).where(
                ItemSharingMember.kind == kind,
                ItemSharingMember.resource_id == resource_id,
            )
        )
    )
    return SharingSettings(
        scope=row.scope, household_id=row.household_id, member_ids=ids
    )


@router.get("/options")
def options(user: Principal, session: DB):
    homes = session.execute(
        select(Household, HouseholdParticipant)
        .join(HouseholdParticipant, HouseholdParticipant.household_id == Household.id)
        .where(
            HouseholdParticipant.account_id == user.id,
            HouseholdParticipant.status == "active",
            HouseholdParticipant.role.in_(("owner", "admin", "member")),
        )
    )
    result = []
    for home, current in homes:
        members = session.scalars(
            select(HouseholdParticipant).where(
                HouseholdParticipant.household_id == home.id,
                HouseholdParticipant.status == "active",
                HouseholdParticipant.role.in_(("owner", "admin", "member")),
                HouseholdParticipant.account_id.is_not(None),
            )
        )
        result.append(
            {
                "id": home.id,
                "name": home.name,
                "role": current.role,
                "members": [
                    {
                        "account_id": m.account_id,
                        "display_name": m.display_name,
                        "role": m.role,
                    }
                    for m in members
                ],
            }
        )
    return {"households": result}


@router.get("/{kind}/{resource_id}", response_model=SharingSettings)
def get_settings(kind: str, resource_id: UUID, user: Principal, session: DB):
    row = resource(session, user, kind, resource_id)
    if kind == "reminder":
        return settings_out(
            session, "todo" if row.todo_id else "event", row.todo_id or row.event_id
        )
    return settings_out(session, kind, resource_id)


def save_settings(session, kind, resource_id, body):
    session.execute(
        delete(ItemSharingMember).where(
            ItemSharingMember.kind == kind, ItemSharingMember.resource_id == resource_id
        )
    )
    row = session.get(ItemSharing, (kind, resource_id))
    if row is None:
        row = ItemSharing(kind=kind, resource_id=resource_id)
        session.add(row)
    row.scope = body.scope
    row.household_id = body.household_id
    session.flush()
    for account_id in set(body.member_ids):
        session.add(
            ItemSharingMember(kind=kind, resource_id=resource_id, account_id=account_id)
        )


@router.put("/{kind}/{resource_id}", response_model=SharingSettings)
def put_settings(
    kind: str, resource_id: UUID, body: SharingSettings, user: Principal, session: DB
):
    row = resource(session, user, kind, resource_id, lock=True)
    if kind == "reminder":
        return put_settings(
            "todo" if row.todo_id else "event",
            row.todo_id or row.event_id,
            body,
            user,
            session,
        )
    if row.owner_id != user.id:
        raise APIError(403, "SHARING_FORBIDDEN", "只有内容创建者可以修改可见范围")
    if body.scope == "private":
        body = SharingSettings()
    else:
        owner = session.scalar(
            select(HouseholdParticipant).where(
                HouseholdParticipant.household_id == body.household_id,
                HouseholdParticipant.account_id == row.owner_id,
                HouseholdParticipant.status == "active",
                HouseholdParticipant.role.in_(("owner", "admin", "member")),
            )
        )
        actor = session.scalar(
            select(HouseholdParticipant).where(
                HouseholdParticipant.household_id == body.household_id,
                HouseholdParticipant.account_id == user.id,
                HouseholdParticipant.status == "active",
                HouseholdParticipant.role.in_(("owner", "admin", "member")),
            )
        )
        if owner is None or actor is None:
            raise APIError(422, "INVALID_SHARING", "请选择内容创建者和你所在的家庭")
        if body.scope == "household":
            body.member_ids = []
        else:
            ids = set(body.member_ids)
            valid = set(
                session.scalars(
                    select(HouseholdParticipant.account_id).where(
                        HouseholdParticipant.household_id == body.household_id,
                        HouseholdParticipant.status == "active",
                        HouseholdParticipant.role.in_(("owner", "admin", "member")),
                        HouseholdParticipant.account_id.in_(ids),
                    )
                )
            )
            if not ids or valid != ids:
                raise APIError(422, "INVALID_SHARING", "请选择有效的家庭成员")
    save_settings(session, kind, resource_id, body)
    if kind == "shopping" and row.unified_checklist_id:
        checklist = session.get(Checklist, row.unified_checklist_id)
        if checklist and checklist.owner_id == row.owner_id:
            save_settings(session, "checklist", row.unified_checklist_id, body)
    elif kind == "checklist":
        shopping = session.scalar(
            select(ShoppingList).where(ShoppingList.unified_checklist_id == row.id)
        )
        if shopping and shopping.owner_id == row.owner_id:
            save_settings(session, "shopping", shopping.id, body)
    for linked_kind, linked_id in linked_resources(session, kind, row):
        save_settings(session, linked_kind, linked_id, body)
    session.commit()
    return body
