from datetime import UTC, datetime, time, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from sqlalchemy import select

from backend.api.life_schemas import (
    MealCreate,
    MealOut,
    PreferenceCreate,
    ShoppingListOut,
)
from backend.api.routes.life import meal_out
from backend.api.routes.life_shopping import shopping, shopping_out
from backend.api.schemas import ERROR_RESPONSES
from backend.core.security import DB, APIError, Principal
from backend.db.life_models import MealPlan, PantryItem, ShoppingList
from backend.db.models import CalendarEvent, Checklist, ChecklistItem, utcnow
from backend.features.sharing.access import accessible, visible_condition
from backend.features.sharing.cleanup import delete_resource

router = APIRouter(prefix="/api/life", tags=["生活规划"], responses=ERROR_RESPONSES)


@router.put("/meal-plans/{meal_id}", response_model=MealOut)
def update_meal(meal_id: UUID, body: MealCreate, user: Principal, session: DB):
    row = session.scalar(
        select(MealPlan)
        .where(MealPlan.id == meal_id, visible_condition(MealPlan, user.id))
        .with_for_update()
    )
    if row is None:
        raise APIError(404, "MEAL_NOT_FOUND", "餐食计划不存在或无法访问")
    if "schedule_text" in body.model_fields_set:
        row.title = (body.schedule_text or "").strip() or "餐食计划"
    row.schedule_text = body.schedule_text
    row.meal_date = body.date
    row.meal_type = body.meal_type
    row.diners = body.diners
    row.dish = body.dish.strip()
    row.notes = body.notes
    if "preferences" in body.model_fields_set:
        row.preferences = [
            {"id": str(uuid4()), **item.model_dump()} for item in body.preferences
        ]
    if row.shopping_list:
        accessible(session, user, ShoppingList, row.shopping_list.id, lock=True)
        row.shopping_list.title = (row.title or row.dish)[:15]
    if row.shopping_list and row.shopping_list.unified_checklist:
        accessible(
            session, user, Checklist, row.shopping_list.unified_checklist_id, lock=True
        )
        row.shopping_list.unified_checklist.title = row.shopping_list.title
    if row.event_id:
        event = accessible(session, user, CalendarEvent, row.event_id, lock=True)
        hours = {"breakfast": 8, "lunch": 12, "dinner": 18, "snack": 15}
        if row.meal_date is not None:
            starts_at = datetime.combine(
                row.meal_date,
                time(hours.get(row.meal_type, 18)),
                ZoneInfo(user.timezone),
            ).astimezone(UTC)
            event.starts_at = starts_at
            event.ends_at = starts_at + timedelta(hours=1)
        event.title = (row.title or row.dish)[:15]
        event.description = row.notes
    session.commit()
    return meal_out(row)


@router.delete("/pantry/{item_id}", status_code=204)
def delete_pantry(item_id: UUID, user: Principal, session: DB):
    row = session.scalar(
        select(PantryItem).where(
            PantryItem.id == item_id, visible_condition(PantryItem, user.id)
        )
    )
    if row is None:
        raise APIError(404, "PANTRY_ITEM_NOT_FOUND", "库存项不存在或无法访问")
    delete_resource(session, row)
    session.commit()


@router.delete("/shopping-lists/items/{item_id}", response_model=ShoppingListOut)
def delete_shopping_item(
    item_id: UUID,
    user: Principal,
    session: DB,
    meal_id: UUID | None = None,
    list_id: UUID | None = None,
):
    row = shopping(session, user, meal_id=meal_id, list_id=list_id)
    if row is None:
        raise APIError(404, "CHECKLIST_ITEM_NOT_FOUND", "清单项不存在或无法访问")
    item = session.scalar(
        select(ChecklistItem).where(
            ChecklistItem.id == item_id,
            ChecklistItem.checklist_id == row.unified_checklist_id,
        )
    )
    if item is None:
        raise APIError(404, "CHECKLIST_ITEM_NOT_FOUND", "清单项不存在或无法访问")
    delete_resource(session, item)
    row.unified_checklist.updated_at = utcnow()
    session.commit()
    return shopping_out(row)


@router.delete(
    "/shopping-lists/{list_id}/items/{item_id}", response_model=ShoppingListOut
)
def delete_list_item(list_id: UUID, item_id: UUID, user: Principal, session: DB):
    return delete_shopping_item(item_id, user, session, list_id=list_id)


@router.post(
    "/meal-plans/{meal_id}/preferences", response_model=MealOut, status_code=201
)
def add_meal_preference(
    meal_id: UUID, body: PreferenceCreate, user: Principal, session: DB
):
    row = session.scalar(
        select(MealPlan)
        .where(MealPlan.id == meal_id, visible_condition(MealPlan, user.id))
        .with_for_update()
    )
    if row is None:
        raise APIError(404, "MEAL_NOT_FOUND", "餐食计划不存在或无法访问")
    if len(row.preferences) >= 20:
        raise APIError(422, "PREFERENCE_LIMIT", "每餐最多添加20条偏好与限制")
    if any(
        item["label"] == body.label and item["kind"] == body.kind
        for item in row.preferences
    ):
        raise APIError(409, "PREFERENCE_EXISTS", "本餐已有相同偏好或限制")
    row.preferences = [*row.preferences, {"id": str(uuid4()), **body.model_dump()}]
    session.commit()
    return meal_out(row)


@router.delete(
    "/meal-plans/{meal_id}/preferences/{preference_id}", response_model=MealOut
)
def delete_meal_preference(
    meal_id: UUID, preference_id: UUID, user: Principal, session: DB
):
    row = session.scalar(
        select(MealPlan)
        .where(MealPlan.id == meal_id, visible_condition(MealPlan, user.id))
        .with_for_update()
    )
    if row is None:
        raise APIError(404, "MEAL_NOT_FOUND", "餐食计划不存在或无法访问")
    if not any(item["id"] == str(preference_id) for item in row.preferences):
        raise APIError(404, "PREFERENCE_NOT_FOUND", "本餐偏好或限制不存在")
    row.preferences = [
        item for item in row.preferences if item["id"] != str(preference_id)
    ]
    session.commit()
    return meal_out(row)
