from backend.features.assistant.autonomous_guards import preflight
from backend.features.assistant.capabilities import ENTRIES
from backend.features.assistant.life_capabilities import LIFE_CAPABILITIES
from backend.features.assistant.tool_registry import search


def test_hidden_meal_settings_is_not_an_assistant_page_entry():
    assert "meal_settings" not in ENTRIES
    assert preflight("库存里有胡萝卜，这个在哪里看的？") is None
    assert not any(
        capability[4] == "/meals/settings" for capability in LIFE_CAPABILITIES.values()
    )


def test_current_menu_discovers_meal_reader():
    assert any(
        item["name"] == "list_meals" for item in search("现在有什么菜单", mode="read")
    )


def test_ai_search_excludes_hidden_inventory_page(monkeypatch):
    from uuid import uuid4

    from backend.api.hub_schemas import SearchItem, SearchResult
    from backend.api.routes import assistant_tool_adapters as adapters

    monkeypatch.setattr(
        adapters,
        "search",
        lambda *_: SearchResult(
            items=[
                SearchItem(
                    id=uuid4(), kind="pantry", url="/meals/settings", title="胡萝卜"
                ),
                SearchItem(id=uuid4(), kind="meal", url="/meals", title="餐食计划"),
            ]
        ),
    )
    result = adapters.search_business("胡萝卜", None, None)
    assert [item.title for item in result.items] == ["餐食计划"]
