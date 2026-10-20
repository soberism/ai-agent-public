import json
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from backend.api.life_schemas import MealList, PantryOut, PreferenceOut
from backend.api.routes import assistant_features as features
from backend.api.routes import assistant_read_steps as read_steps
from backend.api.routes import assistant_tool_adapters as adapters
from backend.features.assistant.tool_registry import search


def test_life_reads_are_split_and_shopping_delete_requires_confirmation(monkeypatch):
    preference = PreferenceOut(id=uuid4(), label="少盐", kind="preference")
    pantry = PantryOut(id=uuid4(), name="牛奶", quantity=1, unit="瓶")
    monkeypatch.setattr(
        adapters,
        "meals",
        lambda *_: MealList(items=[], preferences=[preference], pantry=[pantry]),
    )
    user, session = SimpleNamespace(id=uuid4()), Mock()
    assert adapters.list_preferences(user, session) == [preference]
    assert adapters.list_pantry(user, session) == [pantry]
    observed = json.loads(
        read_steps.inspect("list_pantry", {}, Mock(), user, session, uuid4())
    )
    assert observed["items"][0]["name"] == "牛奶"
    assert {item["name"] for item in search("查询食材库存", mode="read")} >= {
        "list_pantry"
    }
    assert {item["name"] for item in search("删除购物清单项", mode="write")} >= {
        "delete_shopping_item"
    }
    monkeypatch.setattr(
        features,
        "prepare",
        lambda *_: ({"list_id": str(uuid4()), "item_id": str(uuid4())}, {}),
    )
    store = Mock()
    reply = features.feature_reply(
        "delete_shopping_item",
        {"list_id": str(uuid4()), "item_id": str(uuid4())},
        store,
        user,
        session,
        uuid4(),
    )
    assert reply.kind == "confirm"
    store.set.assert_called_once()
