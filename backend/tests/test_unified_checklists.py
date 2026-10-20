import importlib.util
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.life_models import ShoppingList
from backend.db.models import Checklist, ChecklistItem
from backend.db.session import engine


def test_migration_and_shared_checklist_operations_in_cloud(cloud):
    from helpers import register

    register(cloud)
    owner = UUID(cloud.get("/api/auth/me").json()["id"])
    item_id = uuid4()
    with Session(engine) as session:
        legacy = ShoppingList(
            owner_id=owner,
            title="历史采购",
            items=[
                {
                    "id": str(item_id),
                    "name": "鸡蛋",
                    "quantity": 6,
                    "unit": "个",
                    "category": "食材",
                    "purchased": True,
                }
            ],
            status="draft",
        )
        session.add(legacy)
        session.flush()
        row = (
            session.execute(
                select(ShoppingList.__table__).where(ShoppingList.id == legacy.id)
            )
            .mappings()
            .one()
        )
        path = (
            Path(__file__).parents[1]
            / "migrations/versions/b29d05f71c83_unify_checklists.py"
        )
        spec = importlib.util.spec_from_file_location("unify_migration", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.migrate_list(session.connection(), row)
        session.commit()
        session.refresh(legacy)
        alias_id, canonical = legacy.id, legacy.unified_checklist_id
        assert legacy.items[0]["quantity"] == 6
        migrated = session.scalar(
            select(ChecklistItem).where(ChecklistItem.checklist_id == canonical)
        )
        assert migrated.title == "鸡蛋 6个 · 食材"
        assert migrated.completed
        assert session.get(Checklist, canonical).title == legacy.title
    url = f"/api/planning/checklists/{canonical}"
    assert cloud.get(url).json()["completed_count"] == 1
    assert (
        cloud.get(f"/api/life/shopping-lists/{alias_id}").json()["checklist_url"]
        == f"/checklists/{canonical}"
    )
    assert cloud.post(f"{url}/pin", json={}).json()["pinned"]
    copy = cloud.post(f"{url}/duplicate", json={}).json()
    assert copy["id"] != str(canonical)
    assert copy["total_count"] == 1
    assert (
        cloud.post(f"{url}/bulk", json={"completed": False}).json()["completed_count"]
        == 0
    )
    assert not cloud.get(f"/api/life/shopping-lists/{alias_id}").json()["items"][0][
        "purchased"
    ]
    meal = cloud.post(
        "/api/life/meal-plans", json={"dish": "牛肉", "checklist_id": str(canonical)}
    ).json()
    assert meal["shopping_url"] == f"/checklists/{canonical}"
    assert (
        cloud.post(
            "/api/life/meal-plans",
            json={"dish": "牛肉", "checklist_id": str(canonical)},
        ).status_code
        == 409
    )
    assert cloud.delete(url).status_code == 204
    assert (
        cloud.get(f"/api/life/meal-plans/{meal['id']}").json()["shopping_url"] is None
    )
    assert cloud.get(f"/api/life/shopping-lists/{alias_id}").status_code == 404
    recreated = cloud.get(
        "/api/life/shopping-lists", params={"meal_id": meal["id"]}
    ).json()
    assert recreated["checklist_url"] != f"/checklists/{canonical}"
    assert (
        cloud.get(
            f"/api/planning/checklists/{recreated['checklist_url'].split('/')[-1]}"
        ).status_code
        == 200
    )

    register(cloud)
    assert cloud.get(f"/api/planning/checklists/{copy['id']}").status_code == 404
    assert cloud.get(f"/api/life/shopping-lists/{alias_id}").status_code == 404
