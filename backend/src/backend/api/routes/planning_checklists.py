from sqlalchemy import select

from backend.api.planning_schemas import ChecklistItemOut, ChecklistOut
from backend.core.security import APIError
from backend.db.life_models import ShoppingList
from backend.db.models import Checklist, ChecklistItem
from backend.db.sharing_models import ItemSharing
from backend.features.sharing.access import visible_condition


def owned_checklist(session, user, checklist_id, lock=False):
    query = select(Checklist).where(
        Checklist.id == checklist_id, visible_condition(Checklist, user.id)
    )
    value = session.scalar(query.with_for_update() if lock else query)
    if value is None:
        raise APIError(404, "CHECKLIST_NOT_FOUND", "该清单不存在或无法访问")
    return value


def checklist_output(session, checklist):
    items = list(
        session.scalars(
            select(ChecklistItem)
            .where(ChecklistItem.checklist_id == checklist.id)
            .order_by(ChecklistItem.position, ChecklistItem.id)
        )
    )
    return ChecklistOut(
        meal_id=session.scalar(
            select(ShoppingList.meal_id).where(
                ShoppingList.unified_checklist_id == checklist.id,
                ShoppingList.owner_id == checklist.owner_id,
            )
        ),
        id=checklist.id,
        title=checklist.title,
        items=[
            ChecklistItemOut(
                id=item.id,
                title=item.title,
                completed=item.completed,
                position=item.position,
            )
            for item in items
        ],
        completed_count=sum(item.completed for item in items),
        total_count=len(items),
        created_at=checklist.created_at,
        updated_at=checklist.updated_at,
        assignee_id=checklist.owner_id,
        pinned=checklist.pinned,
        shared_household_ids=list(
            session.scalars(
                select(ItemSharing.household_id).where(
                    ItemSharing.kind == "checklist",
                    ItemSharing.resource_id == checklist.id,
                    ItemSharing.scope != "private",
                )
            )
        ),
    )


def owned_item(session, user, checklist_id, item_id):
    checklist = owned_checklist(session, user, checklist_id, True)
    item = session.scalar(
        select(ChecklistItem).where(
            ChecklistItem.id == item_id, ChecklistItem.checklist_id == checklist.id
        )
    )
    if item is None:
        raise APIError(404, "CHECKLIST_ITEM_NOT_FOUND", "该清单项不存在或无法访问")
    return checklist, item
