from sqlalchemy import select

from backend.db.document_models import DocumentReviewItem
from backend.db.life_models import ShoppingList
from backend.features.sharing.access import RESOURCE_MODELS


def linked_resources(session, kind, row):
    """Workflow-generated children share their source item's visibility."""
    links = []
    if kind in ("meal", "appointment") and row.event_id:
        links.append(("event", row.event_id))
    if kind == "appointment" and row.todo_id:
        links.append(("todo", row.todo_id))
    if kind == "voice_memo" and row.target_id:
        links.append((row.target_type, row.target_id))
    if kind == "material":
        links.extend(
            session.execute(
                select(
                    DocumentReviewItem.target_type, DocumentReviewItem.target_id
                ).where(
                    DocumentReviewItem.material_id == row.id,
                    DocumentReviewItem.change_kind == "new",
                    DocumentReviewItem.status == "accepted",
                    DocumentReviewItem.target_id.is_not(None),
                )
            )
        )
    if kind == "meal":
        shopping = session.scalar(
            select(ShoppingList).where(ShoppingList.meal_id == row.id)
        )
        if shopping and shopping.owner_id == row.owner_id:
            links.append(("shopping", shopping.id))
            if shopping.unified_checklist_id:
                links.append(("checklist", shopping.unified_checklist_id))
    for target_kind, target_id in links:
        target = session.get(RESOURCE_MODELS[target_kind], target_id)
        if target is not None and target.owner_id == row.owner_id:
            yield target_kind, target_id
