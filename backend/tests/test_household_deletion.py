from uuid import UUID

from helpers import create
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_sharing_integration import family_accounts, login_as

from backend.db.household_models import HouseholdParticipant, Notification
from backend.db.session import engine
from backend.db.sharing_models import ItemSharing


def test_only_creator_can_delete_family_and_business_items_survive(cloud):
    _, owner_cookie, home, _, member_cookie, _, helper_cookie = family_accounts(cloud)
    login_as(cloud, owner_cookie)
    todo = create(cloud, title="删除家庭保留待办")
    shared = cloud.put(
        f"/api/sharing/todo/{todo['id']}",
        json={"scope": "household", "household_id": home["id"]},
    )
    assert shared.status_code == 200
    login_as(cloud, member_cookie)
    assert cloud.delete(f"/api/households/{home['id']}").status_code == 404
    assert cloud.get(f"/api/todos/{todo['id']}").status_code == 200
    login_as(cloud, helper_cookie)
    assert cloud.delete(f"/api/households/{home['id']}").status_code == 404
    login_as(cloud, owner_cookie)
    assert cloud.delete(f"/api/households/{home['id']}").status_code == 204
    assert cloud.get("/api/households").json()["items"] == []
    assert cloud.get(f"/api/todos/{todo['id']}").status_code == 200
    assert cloud.get(f"/api/sharing/todo/{todo['id']}").json()["scope"] == "private"
    assert cloud.delete(f"/api/households/{home['id']}").status_code == 404
    login_as(cloud, member_cookie)
    assert cloud.get(f"/api/todos/{todo['id']}").status_code == 404
    assert cloud.get("/api/households").json()["items"] == []
    with Session(engine) as db:
        for model in (HouseholdParticipant, ItemSharing, Notification):
            assert (
                db.scalar(select(model).where(model.household_id == UUID(home["id"])))
                is None
            )
