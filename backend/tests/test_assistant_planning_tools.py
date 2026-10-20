"""Agent coverage for enabled planning tools and server-owned write identity."""

import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest

from backend.api.calendar_schemas import EventBatchDelete
from backend.api.hub_schemas import SearchItem, SearchResult
from backend.api.routes import assistant_features as features
from backend.api.routes import assistant_read_steps as read_steps
from backend.api.routes import assistant_tool_adapters as adapters
from backend.api.schemas import AssistantReply, TodoDailyCreate
from backend.core.security import APIError
from backend.features.assistant.capabilities import CAPABILITIES
from backend.features.assistant.feature_replies import result_reply
from backend.features.assistant.feature_targets import bind_targets
from backend.features.assistant.feature_tools import contract, feature_tools
from backend.features.assistant.prompts import TOOLS
from backend.features.assistant.tool_registry import describe, search


def test_planning_tools_are_discoverable_with_bounded_contracts():
    names = {
        "search_business",
        "open_connections",
        "list_todos",
        "get_todo",
        "create_todo",
        "create_daily_todos",
        "delete_todo",
        "delete_event",
        "delete_events",
        "create_checklist",
        "rename_checklist",
        "delete_checklist",
        "list_shopping",
        "get_shopping_detail",
        "create_shopping",
        "add_shopping_item",
        "check_shopping_item",
        "confirm_shopping",
        "delete_shopping",
        "delete_shopping_item",
        "list_preferences",
        "list_pantry",
    }
    assert names <= CAPABILITIES.keys()
    assert "list_todos" in {item["name"] for item in search("今天待办")}
    assert "list_events" in {
        item["name"] for item in search("查询11月所有日程", mode="read")
    }
    for name in names:
        handler, model = contract(name)
        assert callable(handler)
        assert model.model_json_schema()["additionalProperties"] is False
        assert describe(name)["mode"] == ("read" if CAPABILITIES[name][2] else "write")
    assert set(contract("create_todo")[1].model_fields) == {"body"}
    assert set(contract("create_daily_todos")[1].model_fields) == {"body"}
    assert set(contract("delete_events")[1].model_fields) == {"body"}
    assert set(contract("delete_shopping_item")[1].model_fields) == {
        "list_id",
        "item_id",
    }
    assert contract("list_todos")[1].model_validate({"query": {"due": "today"}})
    with pytest.raises(APIError):
        features.validate(
            "create_todo", {"body": {"title": "事项"}, "idempotency_key": str(uuid4())}
        )


def test_today_todos_reuses_authenticated_listing_without_confirmation(monkeypatch):
    handler = Mock(return_value=SimpleNamespace(items=[], next_cursor=None))
    _, model = contract("list_todos")
    monkeypatch.setattr(features, "contract", lambda _: (handler, model))
    monkeypatch.setattr(
        features,
        "result_reply",
        lambda *_: AssistantReply(kind="result", message="没有待办"),
    )
    store, user, session = Mock(), SimpleNamespace(id=uuid4()), Mock()
    result = features.feature_reply(
        "list_todos", {"query": {"due": "today"}}, store, user, session, uuid4()
    )
    assert result.kind == "result"
    assert handler.call_args.kwargs["query"].due == "today"
    assert handler.call_args.kwargs["user"] is user
    store.set.assert_not_called()


def test_todo_create_waits_for_confirmation_and_uses_stable_server_key(monkeypatch):
    handler = Mock(return_value=SimpleNamespace(id=uuid4(), title="买菜"))
    _, model = contract("create_todo")
    monkeypatch.setattr(features, "contract", lambda _: (handler, model))
    monkeypatch.setattr(
        features,
        "result_reply",
        lambda *_: AssistantReply(kind="success", message="待办已创建"),
    )
    store, user, session = Mock(), SimpleNamespace(id=uuid4()), Mock()
    draft = features.feature_reply(
        "create_todo", {"body": {"title": "买菜"}}, store, user, session, uuid4()
    )
    assert draft.kind == "confirm"
    handler.assert_not_called()
    token = uuid4()
    features.invoke(
        "create_todo",
        {"body": {"title": "买菜"}},
        user,
        session,
        idempotency_token=token,
    )
    assert handler.call_args.kwargs["idempotency_key"] == uuid5(
        NAMESPACE_URL, str(token)
    )
    assert handler.call_args.kwargs["user"] is user
    with pytest.raises(APIError):
        features.invoke("create_todo", {"body": {"title": "买菜"}}, user, session)


def test_daily_todo_range_expands_every_date_once():
    dates = adapters.daily_dates(
        TodoDailyCreate(
            title="每日待办",
            date_from="2026-09-25",
            date_to="2026-10-16",
            due_time="09:00",
        )
    )

    assert len(dates) == 22
    assert dates[0].isoformat() == "2026-09-25"
    assert dates[-1].isoformat() == "2026-10-16"


def test_daily_todo_creation_commits_missing_dates_once(monkeypatch):
    existing = SimpleNamespace(due_date=date(2026, 9, 25))

    class BatchSession:
        def __init__(self):
            self.added = []
            self.commits = 0

        def scalars(self, _):
            return [existing]

        def add(self, todo):
            self.added.append(todo)

        def commit(self):
            self.commits += 1

    monkeypatch.setattr(adapters, "set_due", lambda _: None)
    monkeypatch.setattr(adapters, "output", lambda todo: todo)
    session = BatchSession()
    todos = adapters.create_daily_todos(
        TodoDailyCreate(
            title="每日待办",
            date_from="2026-09-25",
            date_to="2026-10-16",
            due_time="09:00",
        ),
        uuid4(),
        SimpleNamespace(id=uuid4(), timezone="Asia/Shanghai"),
        session,
    )

    assert len(todos) == 22
    assert len(session.added) == 21
    assert session.commits == 1


def test_batch_event_delete_uses_only_bound_ids(monkeypatch):
    from backend.api.routes import calendar_events

    event_ids = [uuid4(), uuid4()]
    events = [SimpleNamespace(id=event_id) for event_id in event_ids]

    class BatchSession:
        commits = 0

        def scalars(self, _):
            return events

        def commit(self):
            self.commits += 1

    deleted = []
    monkeypatch.setattr(
        calendar_events, "delete_resource", lambda _, row: deleted.append(row.id)
    )
    session = BatchSession()

    result = calendar_events.remove_batch(
        EventBatchDelete(
            date_from="2026-11-01",
            date_to="2026-11-30",
            event_ids=event_ids,
        ),
        SimpleNamespace(id=uuid4(), timezone="Asia/Shanghai"),
        session,
    )

    assert result == {"count": 2}
    assert deleted == event_ids
    assert session.commits == 1


def test_chat_exposes_only_one_checklist_creation_tool():
    names = [tool["function"]["name"] for tool in [*TOOLS, *feature_tools()]]
    assert names.count("create_checklist") == 1
    assert "feature_create_checklist" not in names


def test_shopping_item_target_requires_accessible_parent():
    list_id, item_id = uuid4(), uuid4()
    session = Mock()
    session.scalars.return_value = [SimpleNamespace(id=list_id, title="采购")]
    session.scalar.return_value = None
    with pytest.raises(APIError) as error:
        bind_targets(
            "check_shopping_item",
            {
                "list_id": str(list_id),
                "item_id": str(item_id),
                "body": {"purchased": True},
            },
            SimpleNamespace(id=uuid4()),
            session,
        )
    assert error.value.code == "INVALID_TARGET"


def test_global_search_keeps_enabled_results_only(monkeypatch):
    monkeypatch.setattr(
        adapters,
        "search",
        lambda *_: SearchResult(
            items=[
                SearchItem(id=uuid4(), kind="todo", title="买菜", url="/todos/one"),
                SearchItem(
                    id=uuid4(), kind="contact", title="联系人", url="/contacts/one"
                ),
            ]
        ),
    )
    result = adapters.search_business("买", SimpleNamespace(id=uuid4()), Mock())
    assert [item.kind for item in result.items] == ["todo"]
    reply = result_reply("search_business", result)
    assert reply.items[0].kind == "todo"
    assert reply.items[0].url == "/todos/one"
    observed = json.loads(
        read_steps.inspect(
            "search_business",
            {"q": "买"},
            Mock(),
            SimpleNamespace(id=uuid4()),
            Mock(),
            uuid4(),
        )
    )
    assert observed["items"][0]["url"] == "/todos/one"


def test_connections_tool_returns_navigation_only():
    store, user, session = Mock(), SimpleNamespace(id=uuid4()), Mock()
    reply = features.feature_reply(
        "open_connections", {}, store, user, session, uuid4()
    )
    assert reply.kind == "message"
    assert reply.items[0].kind == "navigation"
    assert reply.items[0].url == "/connections"
    store.set.assert_not_called()


def test_event_list_summary_keeps_fifty_deletable_ids_under_read_limit():
    items = [
        {
            "id": str(uuid4()),
            "title": "每日9点日程",
            "status": "scheduled",
            "assignee_id": str(uuid4()),
            "start_date": "2026-11-01",
            "start_time": "09:00",
            "end_date": "2026-11-01",
            "end_time": "10:00",
            "description": "不应进入列表摘要" * 100,
        }
        for _ in range(50)
    ]
    result = read_steps.event_summaries({"items": items})

    assert len(result["items"]) == 50
    assert "description" not in result["items"][0]
    assert len(json.dumps(result, ensure_ascii=False)) <= 14000
