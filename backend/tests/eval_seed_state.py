"""只读取本条用例账号及其子对象，保存可复核的业务前后状态。"""

import hashlib
from datetime import date, datetime, time
from uuid import UUID

from sqlalchemy import inspect, select

from backend.db.cross_system_models import VoiceMemo
from backend.db.document_models import DocumentFolder, DocumentMaterial
from backend.db.household_models import Household, HouseholdParticipant
from backend.db.life_models import LifePreference, MealPlan, PantryItem, ShoppingList
from backend.db.models import (
    AssistantMemory,
    AssistantProfile,
    CalendarEvent,
    Checklist,
    ChecklistItem,
    Reminder,
    Todo,
    User,
)
from backend.db.parity_models import DailyDump
from backend.db.sharing_models import ItemSharing, ItemSharingMember

MODELS = [
    Todo,
    CalendarEvent,
    Checklist,
    ChecklistItem,
    ShoppingList,
    MealPlan,
    LifePreference,
    PantryItem,
    DocumentFolder,
    DocumentMaterial,
    VoiceMemo,
    AssistantMemory,
    AssistantProfile,
    DailyDump,
    Reminder,
    Household,
    HouseholdParticipant,
    ItemSharing,
    ItemSharingMember,
    User,
]


def scalar(value):
    if isinstance(value, bytes):
        return {"bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
    if isinstance(value, (UUID, datetime, date, time)):
        return str(value)
    return value


def snapshot(db, users):
    ids = [u.id for u in users.values()]
    homes = select(Household.id).where(Household.owner_id.in_(ids))
    lists = select(Checklist.id).where(Checklist.owner_id.in_(ids))
    result = {}
    resource_ids = []
    for model in MODELS:
        query = select(model)
        if hasattr(model, "owner_id"):
            query = query.where(model.owner_id.in_(ids))
        elif model is User:
            query = query.where(User.id.in_(ids))
        elif model is ChecklistItem:
            query = query.where(ChecklistItem.checklist_id.in_(lists))
        elif model is HouseholdParticipant:
            query = query.where(HouseholdParticipant.household_id.in_(homes))
        elif model in {ItemSharing, ItemSharingMember}:
            query = query.where(model.resource_id.in_(resource_ids))
        else:
            raise ValueError(model)
        rows = {}
        for row in db.scalars(query):
            value = {
                col.key: scalar(getattr(row, col.key))
                for col in inspect(model).columns
                if col.key
                not in {"password_hash", "created_at", "updated_at", "auth_version"}
            }
            key = str(
                getattr(row, "id", None)
                or getattr(row, "owner_id", None)
                or (
                    value.get("kind"),
                    value.get("resource_id"),
                    value.get("account_id"),
                )
            )
            rows[key] = value
            if getattr(row, "id", None) and model is not User:
                resource_ids.append(row.id)
        result[model.__tablename__] = rows
    return result


def delta(before, after):
    changes = []
    for table in before.keys() | after.keys():
        old, new = before.get(table, {}), after.get(table, {})
        for key in old.keys() | new.keys():
            if old.get(key) != new.get(key):
                changes.append(
                    {
                        "table": table,
                        "id": key,
                        "before": old.get(key),
                        "after": new.get(key),
                    }
                )
    return changes


def cleanup_sharing(record):
    """共享策略没有资源外键，只按本条记录的精确ID清理。"""
    from sqlalchemy import delete
    from sqlalchemy.orm import Session

    from backend.db.session import engine

    ids = {item["id"] for item in record.get("setup", {}).get("objects", [])}
    ids.update(
        change["id"]
        for step in record["steps"]
        for change in step.get("business_delta", [])
        if change.get("id")
    )
    valid = []
    for value in ids:
        try:
            valid.append(UUID(value))
        except ValueError:
            continue
    if valid:
        with Session(engine) as db:
            db.execute(delete(ItemSharing).where(ItemSharing.resource_id.in_(valid)))
            db.commit()
