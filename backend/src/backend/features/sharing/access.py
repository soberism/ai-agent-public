"""Explicit, fresh per-request authorization for shared business items."""

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import aliased

from backend.core.security import APIError
from backend.db.cross_system_models import VoiceMemo
from backend.db.document_models import (
    DocumentFolder,
    DocumentMaterial,
    DocumentReviewItem,
)
from backend.db.household_models import Contact, ContactGroup, HouseholdParticipant
from backend.db.life_models import (
    LifePreference,
    MealPlan,
    MedicalAppointment,
    PantryItem,
    ShoppingList,
)
from backend.db.models import CalendarEvent, Checklist, ChecklistItem, Reminder, Todo
from backend.db.parity_models import DailyDump
from backend.db.sharing_models import ItemSharing, ItemSharingMember

RESOURCE_MODELS = {
    "todo": Todo,
    "event": CalendarEvent,
    "checklist": Checklist,
    "reminder": Reminder,
    "material": DocumentMaterial,
    "folder": DocumentFolder,
    "meal": MealPlan,
    "shopping": ShoppingList,
    "voice_memo": VoiceMemo,
    "daily_dump": DailyDump,
    "contact": Contact,
    "contact_group": ContactGroup,
    "pantry": PantryItem,
    "preference": LifePreference,
    "appointment": MedicalAppointment,
}

MODELS = RESOURCE_MODELS


def _shared(kind, resource_id, owner_id, user_id):
    receiver = aliased(HouseholdParticipant)
    owner = aliased(HouseholdParticipant)
    recipient = exists(
        select(ItemSharingMember.account_id).where(
            ItemSharingMember.kind == kind,
            ItemSharingMember.resource_id == resource_id,
            ItemSharingMember.account_id == user_id,
        )
    ).correlate_except(ItemSharingMember)
    return exists(
        select(ItemSharing.resource_id).where(
            ItemSharing.kind == kind,
            ItemSharing.resource_id == resource_id,
            exists(
                select(owner.id).where(
                    owner.household_id == ItemSharing.household_id,
                    owner.account_id == owner_id,
                    owner.status == "active",
                    owner.role.in_(("owner", "admin", "member")),
                )
            ).correlate_except(owner),
            exists(
                select(receiver.id).where(
                    receiver.household_id == ItemSharing.household_id,
                    receiver.account_id == user_id,
                    receiver.status == "active",
                    or_(
                        and_(
                            ItemSharing.scope == "household",
                            receiver.role.in_(("owner", "admin", "member")),
                        ),
                        and_(
                            ItemSharing.scope == "members",
                            receiver.role.in_(("owner", "admin", "member")),
                            recipient,
                        ),
                    ),
                )
            ).correlate_except(receiver),
        )
    ).correlate_except(ItemSharing)


def visible_condition(model, user_id):
    if model is DocumentFolder:
        return or_(
            model.owner_id == user_id,
            exists(
                select(DocumentMaterial.id).where(
                    DocumentMaterial.folder_id == model.id,
                    visible_condition(DocumentMaterial, user_id),
                )
            ).correlate_except(DocumentMaterial),
        )
    if model is ChecklistItem:
        return exists(
            select(Checklist.id).where(
                Checklist.id == model.checklist_id,
                visible_condition(Checklist, user_id),
            )
        ).correlate_except(Checklist)
    if model is DocumentReviewItem:
        return exists(
            select(DocumentMaterial.id).where(
                DocumentMaterial.id == model.material_id,
                visible_condition(DocumentMaterial, user_id),
            )
        ).correlate_except(DocumentMaterial)
    if model is Reminder:
        return or_(
            exists(
                select(Todo.id).where(
                    Todo.id == model.todo_id, visible_condition(Todo, user_id)
                )
            ).correlate_except(Todo),
            exists(
                select(CalendarEvent.id).where(
                    CalendarEvent.id == model.event_id,
                    visible_condition(CalendarEvent, user_id),
                )
            ).correlate_except(CalendarEvent),
        )
    kind = next((k for k, value in RESOURCE_MODELS.items() if value is model), None)
    if kind is None:
        return model.owner_id == user_id
    own = model.owner_id == user_id
    shared = _shared(kind, model.id, model.owner_id, user_id)
    if model is Checklist:
        linked = exists(
            select(ShoppingList.id).where(
                ShoppingList.unified_checklist_id == Checklist.id,
                ShoppingList.owner_id == Checklist.owner_id,
                or_(
                    ShoppingList.owner_id == user_id,
                    _shared(
                        "shopping", ShoppingList.id, ShoppingList.owner_id, user_id
                    ),
                ),
            )
        ).correlate_except(ShoppingList)
        return or_(own, shared, linked)
    if model is ShoppingList:
        linked = exists(
            select(Checklist.id).where(
                Checklist.id == ShoppingList.unified_checklist_id,
                Checklist.owner_id == ShoppingList.owner_id,
                or_(
                    Checklist.owner_id == user_id,
                    _shared("checklist", Checklist.id, Checklist.owner_id, user_id),
                ),
            )
        ).correlate_except(Checklist)
        return or_(own, shared, linked)
    return or_(own, shared)


def accessible(session, user, model, resource_id, lock=False):
    query = select(model).where(
        model.id == resource_id, visible_condition(model, user.id)
    )
    row = session.scalar(query.with_for_update() if lock else query)
    if row is None:
        raise APIError(404, "RESOURCE_NOT_FOUND", "内容不存在或无法访问")
    return row


def inherit_sharing(session, source_kind, source_id, target_kind, target_id):
    """Copy visibility when a workflow creates a new independently editable item."""
    policy = session.get(ItemSharing, (source_kind, source_id))
    if policy is None:
        return
    session.add(
        ItemSharing(
            kind=target_kind,
            resource_id=target_id,
            scope=policy.scope,
            household_id=policy.household_id,
        )
    )
    session.flush()
    for account_id in session.scalars(
        select(ItemSharingMember.account_id).where(
            ItemSharingMember.kind == source_kind,
            ItemSharingMember.resource_id == source_id,
        )
    ):
        session.add(
            ItemSharingMember(
                kind=target_kind, resource_id=target_id, account_id=account_id
            )
        )
