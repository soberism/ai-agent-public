from datetime import UTC, datetime, time, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.api.life_schemas import (
    LifeCapabilities,
    MealCreate,
    MealList,
    MealOut,
    PantryCreate,
    PantryOut,
    PreferenceCreate,
    PreferenceOut,
)
from backend.api.schemas import ERROR_RESPONSES
from backend.core.security import DB, APIError, Principal
from backend.db.life_models import LifePreference, MealPlan, PantryItem, ShoppingList
from backend.db.models import CalendarEvent, Checklist
from backend.features.sharing.access import inherit_sharing, visible_condition
from backend.features.sharing.cleanup import delete_resource

router = APIRouter(prefix="/api/life", tags=["生活规划"], responses=ERROR_RESPONSES)


def meal_out(row):
    return MealOut(
        id=row.id,
        title=row.title or row.dish[:15],
        schedule_text=row.schedule_text,
        date=row.meal_date,
        meal_type=row.meal_type,
        diners=row.diners,
        dish=row.dish,
        notes=row.notes,
        preferences=row.preferences,
        status=row.status,
        calendar_url=f"/calendar/{row.event_id}/edit" if row.event_id else None,
        shopping_url=f"/checklists/{row.shopping_list.unified_checklist_id}"
        if row.shopping_list and row.shopping_list.unified_checklist_id
        else None,
    )


def pantry_out(row):
    return PantryOut(id=row.id, name=row.name, quantity=row.quantity, unit=row.unit)


def preference_out(row):
    return PreferenceOut(id=row.id, label=row.label, kind=row.kind)


@router.get("/capabilities", response_model=LifeCapabilities)
def capabilities():
    return LifeCapabilities()


@router.get("/meal-plans", response_model=MealList)
def meals(user: Principal, session: DB):
    items = session.scalars(
        select(MealPlan)
        .options(selectinload(MealPlan.shopping_list))
        .where(visible_condition(MealPlan, user.id))
        .order_by(MealPlan.meal_date, MealPlan.id)
    )
    preferences = session.scalars(
        select(LifePreference)
        .where(visible_condition(LifePreference, user.id))
        .order_by(LifePreference.created_at, LifePreference.id)
    )
    pantry = session.scalars(
        select(PantryItem)
        .where(visible_condition(PantryItem, user.id))
        .order_by(PantryItem.name, PantryItem.id)
    )
    return MealList(
        items=[meal_out(row) for row in items],
        preferences=[preference_out(row) for row in preferences],
        pantry=[pantry_out(row) for row in pantry],
    )


@router.get("/meal-plans/{meal_id}", response_model=MealOut)
def get_meal(meal_id: UUID, user: Principal, session: DB):
    row = session.scalar(
        select(MealPlan)
        .options(selectinload(MealPlan.shopping_list))
        .where(MealPlan.id == meal_id, visible_condition(MealPlan, user.id))
    )
    if row is None:
        raise APIError(404, "MEAL_NOT_FOUND", "餐食计划不存在或无法访问")
    return meal_out(row)


@router.post("/meal-plans", response_model=MealOut, status_code=201)
def create_meal(body: MealCreate, user: Principal, session: DB):
    row = MealPlan(
        owner_id=user.id,
        title=(body.schedule_text or "").strip() or "餐食计划",
        schedule_text=body.schedule_text,
        meal_date=body.date,
        meal_type=body.meal_type,
        diners=body.diners,
        dish=body.dish.strip(),
        ingredients=[],
        preferences=[
            {"id": str(uuid4()), **item.model_dump()} for item in body.preferences
        ],
        notes=body.notes,
        status="draft",
    )
    if body.checklist_id:
        checklist = session.scalar(
            select(Checklist)
            .where(
                Checklist.id == body.checklist_id, visible_condition(Checklist, user.id)
            )
            .with_for_update()
        )
        if checklist is None:
            raise APIError(404, "CHECKLIST_NOT_FOUND", "清单不存在或无法访问")
        linked = session.scalar(
            select(ShoppingList).where(
                ShoppingList.unified_checklist_id == checklist.id
            )
        )
        if linked is not None and linked.meal_id is not None:
            raise APIError(409, "CHECKLIST_LINKED", "该清单已关联其他餐食")
        row.shopping_list = (
            linked
            if linked is not None
            else ShoppingList(
                owner_id=user.id,
                title=checklist.title,
                items=[],
                status="draft",
                unified_checklist=checklist,
            )
        )
    elif body.shopping_list_id:
        linked = session.scalar(
            select(ShoppingList)
            .where(
                ShoppingList.id == body.shopping_list_id,
                visible_condition(ShoppingList, user.id),
            )
            .with_for_update()
        )
        if linked is None:
            raise APIError(404, "SHOPPING_LIST_NOT_FOUND", "购物清单不存在或无法访问")
        if linked.meal_id is not None:
            raise APIError(
                409, "SHOPPING_LIST_LINKED", "该购物清单已关联其他餐食，请选择独立清单"
            )
        row.shopping_list = linked
        if linked.unified_checklist is None:
            linked.unified_checklist = Checklist(owner_id=user.id, title=linked.title)
    else:
        row.shopping_list = ShoppingList(
            owner_id=user.id,
            title=row.title,
            items=[],
            status="draft",
            unified_checklist=Checklist(
                owner_id=user.id,
                title=row.title,
            ),
        )
    session.add(row)
    session.commit()
    return meal_out(row)


@router.post("/meal-plans/{meal_id}/confirm", response_model=MealOut)
def confirm_meal(meal_id: UUID, user: Principal, session: DB):
    row = session.scalar(
        select(MealPlan)
        .where(MealPlan.id == meal_id, visible_condition(MealPlan, user.id))
        .with_for_update()
    )
    if row is None:
        raise APIError(404, "MEAL_NOT_FOUND", "餐食计划不存在或无法访问")
    if row.event_id is None:
        if row.meal_date is None:
            raise APIError(422, "MEAL_TIME_REQUIRED", "请先在餐食详情选择日期并保存")
        hours = {"breakfast": 8, "lunch": 12, "dinner": 18, "snack": 15}
        starts_at = datetime.combine(
            row.meal_date, time(hours.get(row.meal_type, 18)), ZoneInfo(user.timezone)
        ).astimezone(UTC)
        event = CalendarEvent(
            owner_id=row.owner_id,
            todo_id=None,
            series_id=None,
            title=(row.title or row.dish)[:15],
            description=row.notes,
            location=None,
            source="life",
            status="scheduled",
            timezone=user.timezone,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=1),
        )
        session.add(event)
        session.flush()
        row.event_id = event.id
        inherit_sharing(session, "meal", row.id, "event", event.id)
    row.status = "planned"
    session.commit()
    return meal_out(row)


@router.delete("/meal-plans/{meal_id}", status_code=204)
def delete_meal(meal_id: UUID, user: Principal, session: DB):
    row = session.scalar(
        select(MealPlan).where(
            MealPlan.id == meal_id, visible_condition(MealPlan, user.id)
        )
    )
    if row is None:
        raise APIError(404, "MEAL_NOT_FOUND", "餐食计划不存在或无法访问")
    delete_resource(session, row)
    session.commit()


@router.post("/preferences", response_model=PreferenceOut, status_code=201)
def create_preference(body: PreferenceCreate, user: Principal, session: DB):
    row = LifePreference(owner_id=user.id, label=body.label.strip(), kind=body.kind)
    session.add(row)
    session.commit()
    return preference_out(row)


@router.delete("/preferences/{preference_id}", status_code=204)
def delete_preference(preference_id: UUID, user: Principal, session: DB):
    row = session.scalar(
        select(LifePreference).where(
            LifePreference.id == preference_id,
            visible_condition(LifePreference, user.id),
        )
    )
    if row is None:
        raise APIError(404, "PREFERENCE_NOT_FOUND", "偏好不存在或无法访问")
    delete_resource(session, row)
    session.commit()


@router.post("/pantry", response_model=PantryOut, status_code=201)
def create_pantry(body: PantryCreate, user: Principal, session: DB):
    row = PantryItem(owner_id=user.id, expires_on=None, **body.model_dump())
    session.add(row)
    session.commit()
    return pantry_out(row)


@router.put("/pantry/{item_id}", response_model=PantryOut)
def update_pantry(item_id: UUID, body: PantryCreate, user: Principal, session: DB):
    row = session.scalar(
        select(PantryItem).where(
            PantryItem.id == item_id, visible_condition(PantryItem, user.id)
        )
    )
    if row is None:
        raise APIError(404, "PANTRY_ITEM_NOT_FOUND", "库存项不存在或无法访问")
    for key, value in body.model_dump().items():
        setattr(row, key, value)
    session.commit()
    return pantry_out(row)
