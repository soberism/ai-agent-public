from uuid import UUID

from fastapi import APIRouter, Response
from sqlalchemy import func, select
from sqlalchemy.orm import object_session

from backend.api.life_schemas import (
    ShoppingItemCreate,
    ShoppingItemPatch,
    ShoppingListCreate,
    ShoppingListOut,
    ShoppingListsOut,
)
from backend.api.schemas import ERROR_RESPONSES
from backend.core.security import DB, APIError, Principal
from backend.db.life_models import MealPlan, ShoppingList
from backend.db.models import Checklist, ChecklistItem, utcnow
from backend.features.sharing.access import (
    accessible,
    inherit_sharing,
    visible_condition,
)
from backend.features.sharing.cleanup import delete_resource

router = APIRouter(prefix="/api/life", tags=["生活规划"], responses=ERROR_RESPONSES)


def shopping(session, user, create=False, meal_id=None, list_id=None):
    if list_id is not None:
        row = session.scalar(
            select(ShoppingList)
            .where(ShoppingList.id == list_id, visible_condition(ShoppingList, user.id))
            .with_for_update()
        )
        if row is None:
            raise APIError(404, "SHOPPING_LIST_NOT_FOUND", "购物清单不存在或无法访问")
        if row.unified_checklist is None:
            raise APIError(404, "CHECKLIST_NOT_FOUND", "清单不存在或无法访问")
        accessible(session, user, Checklist, row.unified_checklist_id)
        return row
    meal = None
    if meal_id is not None:
        meal = session.scalar(
            select(MealPlan)
            .where(MealPlan.id == meal_id, visible_condition(MealPlan, user.id))
            .with_for_update()
        )
        if meal is None:
            raise APIError(404, "MEAL_NOT_FOUND", "餐食计划不存在或无法访问")
    row = session.scalar(
        select(ShoppingList)
        .where(
            visible_condition(ShoppingList, user.id), ShoppingList.meal_id == meal_id
        )
        .order_by(ShoppingList.created_at)
        .limit(1)
    )
    if row is None and create:
        row = ShoppingList(
            owner_id=meal.owner_id if meal else user.id,
            meal_id=meal_id,
            title=((meal.title or meal.dish)[:15]) if meal else "购物清单",
            items=[],
            status="draft",
        )
        session.add(row)
        session.flush()
        if meal:
            inherit_sharing(session, "meal", meal.id, "shopping", row.id)
    if row is not None and create and row.unified_checklist is None:
        row.unified_checklist = Checklist(owner_id=row.owner_id, title=row.title)
        session.flush()
        inherit_sharing(
            session, "shopping", row.id, "checklist", row.unified_checklist_id
        )
    if row is not None and row.unified_checklist is None:
        return None
    if row is not None:
        accessible(session, user, Checklist, row.unified_checklist_id)
    return row


def shopping_out(row):
    return ShoppingListOut(
        id=row.id,
        title=row.unified_checklist.title,
        meal_id=row.meal_id,
        items=[
            {
                "id": str(item.id),
                "name": item.title,
                "quantity": 1,
                "unit": "",
                "category": "",
                "origin": "manual",
                "purchased": item.completed,
            }
            for item in object_session(row).scalars(
                select(ChecklistItem)
                .where(ChecklistItem.checklist_id == row.unified_checklist_id)
                .order_by(ChecklistItem.position, ChecklistItem.id)
            )
        ],
        status=row.status,
        checklist_url=f"/checklists/{row.unified_checklist_id}",
    )


@router.get("/shopping-lists/overview", response_model=ShoppingListsOut)
def list_shopping(user: Principal, session: DB):
    rows = session.scalars(
        select(ShoppingList)
        .where(visible_condition(ShoppingList, user.id))
        .order_by(ShoppingList.created_at.desc(), ShoppingList.id)
    )
    return ShoppingListsOut(
        items=[
            shopping_out(row)
            for row in rows
            if row.unified_checklist is not None
            and session.scalar(
                select(Checklist.id).where(
                    Checklist.id == row.unified_checklist_id,
                    visible_condition(Checklist, user.id),
                )
            )
            is not None
        ]
    )


@router.post("/shopping-lists", response_model=ShoppingListOut, status_code=201)
def create_shopping(body: ShoppingListCreate, user: Principal, session: DB):
    row = ShoppingList(
        owner_id=user.id,
        title=body.title,
        items=[],
        status="draft",
        unified_checklist=Checklist(owner_id=user.id, title=body.title),
    )
    session.add(row)
    session.commit()
    return shopping_out(row)


@router.get("/shopping-lists/{list_id}", response_model=ShoppingListOut)
def shopping_detail(list_id: UUID, user: Principal, session: DB):
    return shopping_out(shopping(session, user, list_id=list_id))


@router.get("/shopping-lists", response_model=ShoppingListOut)
def get_shopping(user: Principal, session: DB, meal_id: UUID | None = None):
    row = shopping(session, user, create=True, meal_id=meal_id)
    session.commit()
    return shopping_out(row)


@router.post("/shopping-lists/items", response_model=ShoppingListOut, status_code=201)
def add_shopping_item(
    body: ShoppingItemCreate,
    user: Principal,
    session: DB,
    meal_id: UUID | None = None,
    list_id: UUID | None = None,
):
    row = shopping(session, user, create=True, meal_id=meal_id, list_id=list_id)
    extra = (
        ""
        if body.quantity == 1 and not body.unit and not body.category
        else f" {body.quantity:g}{body.unit}"
        + (f" · {body.category}" if body.category else "")
    )
    session.add(
        ChecklistItem(
            checklist_id=row.unified_checklist_id,
            title=body.name + extra,
            completed=False,
            position=(
                session.scalar(
                    select(func.max(ChecklistItem.position)).where(
                        ChecklistItem.checklist_id == row.unified_checklist_id
                    )
                )
                or 0
            )
            + 1,
        )
    )
    row.unified_checklist.updated_at = utcnow()
    session.commit()
    return shopping_out(row)


@router.patch("/shopping-lists/items/{item_id}", response_model=ShoppingListOut)
def patch_shopping_item(
    item_id: UUID,
    body: ShoppingItemPatch,
    user: Principal,
    session: DB,
    meal_id: UUID | None = None,
    list_id: UUID | None = None,
):
    row = shopping(session, user, meal_id=meal_id, list_id=list_id)
    if row is None:
        raise APIError(404, "SHOPPING_ITEM_NOT_FOUND", "购物项不存在或无法访问")
    match = session.scalar(
        select(ChecklistItem).where(
            ChecklistItem.id == item_id,
            ChecklistItem.checklist_id == row.unified_checklist_id,
        )
    )
    if match is None:
        raise APIError(404, "CHECKLIST_ITEM_NOT_FOUND", "清单项不存在或无法访问")
    match.completed = body.purchased
    row.unified_checklist.updated_at = utcnow()
    session.commit()
    return shopping_out(row)


@router.post("/shopping-lists/confirm", response_model=ShoppingListOut)
def confirm_shopping(
    user: Principal,
    session: DB,
    meal_id: UUID | None = None,
    list_id: UUID | None = None,
):
    row = shopping(session, user, meal_id=meal_id, list_id=list_id)
    if row is None:
        raise APIError(404, "SHOPPING_LIST_NOT_FOUND", "购物清单不存在")
    row.status = "planned"
    session.commit()
    return shopping_out(row)


@router.post(
    "/shopping-lists/{list_id}/items", response_model=ShoppingListOut, status_code=201
)
def add_list_item(
    list_id: UUID, body: ShoppingItemCreate, user: Principal, session: DB
):
    return add_shopping_item(body, user, session, list_id=list_id)


@router.patch(
    "/shopping-lists/{list_id}/items/{item_id}", response_model=ShoppingListOut
)
def patch_list_item(
    list_id: UUID, item_id: UUID, body: ShoppingItemPatch, user: Principal, session: DB
):
    return patch_shopping_item(item_id, body, user, session, list_id=list_id)


@router.post("/shopping-lists/{list_id}/confirm", response_model=ShoppingListOut)
def confirm_list(list_id: UUID, user: Principal, session: DB):
    return confirm_shopping(user, session, list_id=list_id)


@router.delete("/shopping-lists/{list_id}", status_code=204)
def delete_shopping(list_id: UUID, user: Principal, session: DB):
    row = shopping(session, user, list_id=list_id)
    delete_resource(session, row.unified_checklist)
    delete_resource(session, row)
    session.commit()
    return Response(status_code=204)
