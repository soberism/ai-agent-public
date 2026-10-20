from datetime import date
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.api.routes.life_shopping import shopping
from backend.core.security import APIError
from backend.db.household_models import HouseholdParticipant
from backend.db.life_models import MealPlan, ShoppingList
from backend.db.models import Checklist, ChecklistItem
from backend.db.sharing_models import ItemSharing, ItemSharingMember


def test_meal_lists_are_persistent_separate_and_owner_checked():
    engine = create_engine("sqlite://")
    for model in (HouseholdParticipant, ItemSharing, ItemSharingMember):
        model.__table__.create(engine)
    Checklist.__table__.create(engine)
    ChecklistItem.__table__.create(engine)
    MealPlan.__table__.create(engine)
    ShoppingList.__table__.create(engine)
    user = SimpleNamespace(id=uuid4())
    with Session(engine) as session:
        meals = [
            MealPlan(
                owner_id=user.id,
                meal_date=date(2026, 9, 20),
                meal_type="dinner",
                diners=2,
                dish=dish,
                ingredients=[],
            )
            for dish in ("番茄炒蛋", "牛肉面")
        ]
        session.add_all(meals)
        session.commit()
        first = shopping(session, user, create=True, meal_id=meals[0].id)
        second = shopping(session, user, create=True, meal_id=meals[1].id)
        public = shopping(session, user, create=True)
        session.commit()
        assert len({first.id, second.id, public.id}) == 3
        assert shopping(session, user, meal_id=meals[0].id).id == first.id
        item = ChecklistItem(
            checklist_id=first.unified_checklist_id,
            title="番茄",
            completed=True,
            position=0,
        )
        session.add(item)
        session.commit()
        assert (
            shopping(session, user, meal_id=meals[0].id).unified_checklist_id
            == item.checklist_id
        )
        assert session.get(ChecklistItem, item.id).completed
        assert second.items == public.items == []
        with pytest.raises(APIError):
            shopping(session, SimpleNamespace(id=uuid4()), meal_id=meals[0].id)
        with pytest.raises(APIError):
            shopping(session, user, meal_id=uuid4())


def test_meal_shopping_api_in_cloud_test_database(cloud):
    from helpers import register

    register(cloud)
    meals = [
        cloud.post(
            "/api/life/meal-plans",
            json={
                "date": "2026-09-20",
                "meal_type": "dinner",
                "diners": 2,
                "dish": dish,
            },
        ).json()
        for dish in ("番茄炒蛋", "牛肉面")
    ]
    scope = {"meal_id": meals[0]["id"]}
    first = cloud.get("/api/life/shopping-lists", params=scope).json()
    added = cloud.post(
        "/api/life/shopping-lists/items",
        params=scope,
        json={"name": "番茄", "quantity": 2, "unit": "个"},
    )
    assert added.status_code == 201, added.text
    item_id = added.json()["items"][0]["id"]
    checked = cloud.patch(
        f"/api/life/shopping-lists/items/{item_id}",
        params=scope,
        json={"purchased": True},
    )
    assert checked.json()["items"][0]["purchased"] is True
    assert (
        cloud.get("/api/life/shopping-lists", params=scope).json()["id"] == first["id"]
    )
    assert (
        cloud.get(
            "/api/life/shopping-lists", params={"meal_id": meals[1]["id"]}
        ).json()["items"]
        == []
    )
    assert cloud.get("/api/life/shopping-lists").json()["items"] == []
    confirmed = cloud.post("/api/life/shopping-lists/confirm", params=scope, json={})
    assert confirmed.status_code == 200
    assert confirmed.json()["checklist_url"].startswith("/checklists/")
    removed = cloud.delete(f"/api/life/shopping-lists/items/{item_id}", params=scope)
    assert removed.status_code == 200
    assert removed.json()["items"] == []
    assert (
        cloud.get(
            "/api/life/shopping-lists", params={"meal_id": str(uuid4())}
        ).status_code
        == 404
    )


def test_auto_created_shopping_lists_and_specific_list_permissions(cloud):
    from helpers import register

    register(cloud)
    created = cloud.post(
        "/api/life/meal-plans",
        json={
            "date": "2026-09-20",
            "meal_type": "dinner",
            "diners": 2,
            "dish": "番茄炒蛋",
        },
    )
    assert created.status_code == 201, created.text
    meal = created.json()
    detail = cloud.get(f"/api/life/meal-plans/{meal['id']}")
    assert detail.status_code == 200
    assert detail.json() == meal
    overview = cloud.get("/api/life/shopping-lists/overview").json()["items"]
    assert len(overview) == 1
    assert overview[0]["meal_id"] == meal["id"]
    assert meal["shopping_url"] == overview[0]["checklist_url"]
    assert overview[0]["items"] == []
    linked_path = f"/api/life/shopping-lists/{overview[0]['id']}"
    standalone = cloud.post("/api/life/shopping-lists", json={"title": "周末采购"})
    assert standalone.status_code == 201
    assert standalone.json()["meal_id"] is None
    other_path = f"/api/life/shopping-lists/{standalone.json()['id']}"
    assert (
        cloud.post("/api/life/shopping-lists", json={"title": "  "}).status_code == 422
    )
    added = cloud.post(
        f"{linked_path}/items", json={"name": "鸡蛋", "quantity": 2, "unit": "个"}
    )
    assert added.status_code == 201
    item_id = added.json()["items"][0]["id"]
    assert cloud.patch(
        f"{linked_path}/items/{item_id}", json={"purchased": True}
    ).json()["items"][0]["purchased"]
    assert cloud.get(other_path).json()["items"] == []
    assert (
        cloud.patch(
            f"{other_path}/items/{item_id}", json={"purchased": True}
        ).status_code
        == 404
    )
    assert cloud.get(linked_path).json()["id"] == overview[0]["id"]
    assert len(cloud.get("/api/life/shopping-lists/overview").json()["items"]) == 2
    assert cloud.post(f"{linked_path}/confirm", json={}).status_code == 200
    assert cloud.delete(f"{linked_path}/items/{item_id}").json()["items"] == []
    register(cloud)
    assert cloud.get(f"/api/life/meal-plans/{meal['id']}").status_code == 404
    assert cloud.get(f"/api/life/meal-plans/{uuid4()}").status_code == 404
    assert cloud.get("/api/life/shopping-lists/overview").json()["items"] == []
    assert cloud.get(linked_path).status_code == 404
    assert (
        cloud.post(
            f"{linked_path}/items", json={"name": "鸡蛋", "quantity": 2, "unit": "个"}
        ).status_code
        == 404
    )
    assert (
        cloud.patch(
            f"{linked_path}/items/{item_id}", json={"purchased": True}
        ).status_code
        == 404
    )
    assert cloud.delete(f"{linked_path}/items/{item_id}").status_code == 404
    assert cloud.post(f"{linked_path}/confirm", json={}).status_code == 404


def test_shopping_creation_failure_rolls_back_meal(cloud):
    from helpers import register
    from sqlalchemy import event

    register(cloud)

    def fail_creation(*args):
        raise RuntimeError("simulated shopping insert failure")

    event.listen(ShoppingList, "before_insert", fail_creation)
    try:
        response = cloud.post(
            "/api/life/meal-plans",
            json={
                "date": "2026-09-20",
                "meal_type": "dinner",
                "diners": 2,
                "dish": "牛肉面",
            },
        )
        assert response.status_code == 500
    finally:
        event.remove(ShoppingList, "before_insert", fail_creation)
    assert cloud.get("/api/life/meal-plans").json()["items"] == []
    assert cloud.get("/api/life/shopping-lists/overview").json()["items"] == []


def test_backfill_keeps_existing_items_and_is_repeatable(cloud):
    from runpy import run_path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from helpers import register
    from sqlalchemy import select

    from backend.db.session import engine as cloud_engine

    account, _ = register(cloud)
    with Session(cloud_engine) as session:
        meals = [
            MealPlan(
                owner_id=UUID(account["id"]),
                meal_date=date(2026, 9, 20),
                meal_type="dinner",
                diners=2,
                dish=dish,
                ingredients=[],
            )
            for dish in ("旧餐食", "已有清单的餐食")
        ]
        session.add_all(meals)
        session.flush()
        existing = ShoppingList(
            owner_id=meals[0].owner_id,
            meal_id=meals[1].id,
            title="保留采购",
            items=[{"name": "鸡蛋"}],
            status="draft",
        )
        session.add(existing)
        session.commit()
        existing_id = existing.id
        migrate = run_path(
            "migrations/versions/6c8f2b014d53_backfill_meal_shopping.py"
        )["upgrade"]
        with Operations.context(MigrationContext.configure(session.connection())):
            migrate()
            migrate()
        session.commit()
        rows = session.scalars(
            select(ShoppingList).where(ShoppingList.owner_id == meals[0].owner_id)
        ).all()
        assert len(rows) == 2
        assert session.get(ShoppingList, existing_id).items == [{"name": "鸡蛋"}]
        assert {row.meal_id for row in rows} == {meal.id for meal in meals}
