from uuid import UUID, uuid4

import pytest
from helpers import register
from sqlalchemy.orm import Session

from backend.api.routes.assistant_features import prepare
from backend.core.security import APIError
from backend.db.models import User
from backend.db.session import engine


def test_unified_checklist_id_resolves_only_to_its_accessible_shopping_list(cloud):
    owner, _ = register(cloud)
    response = cloud.post("/api/life/shopping-lists", json={"title": "早餐补货"})
    assert response.status_code == 201, response.text
    shopping = response.json()
    unified_id = shopping["checklist_url"].rsplit("/", 1)[-1]
    added = cloud.post(
        f"/api/life/shopping-lists/{shopping['id']}/items",
        json={"name": "燕麦", "quantity": 1},
    )
    assert added.status_code == 201, added.text
    with Session(engine) as db:
        user = db.get(User, UUID(owner["id"]))
        args, _ = prepare(
            "delete_shopping_item", {"list_id": unified_id, "item_id": "燕麦"}, user, db
        )
        assert args["list_id"] == shopping["id"]
        assert args["item_id"] == added.json()["items"][0]["id"]
        args, _ = prepare("confirm_shopping", {"list_id": unified_id}, user, db)
        assert args["list_id"] == shopping["id"]
        with pytest.raises(APIError):
            prepare("confirm_shopping", {"list_id": str(uuid4())}, user, db)
    assert (
        len(cloud.get(f"/api/life/shopping-lists/{shopping['id']}").json()["items"])
        == 1
    )
    cloud.cookies.clear()
    reader, _ = register(cloud)
    with Session(engine) as db:
        user = db.get(User, UUID(reader["id"]))
        with pytest.raises(APIError):
            prepare("confirm_shopping", {"list_id": unified_id}, user, db)
