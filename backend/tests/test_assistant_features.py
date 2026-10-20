"""Bounded tool contracts, deferred writes and existing-route execution."""

from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from backend.api.routes import assistant_features as features
from backend.api.schemas import AssistantReply
from backend.core.security import APIError
from backend.features.assistant.capabilities import CAPABILITIES, ENTRIES
from backend.features.assistant.feature_replies import result_reply
from backend.features.assistant.feature_targets import bind_targets
from backend.features.assistant.feature_tools import contract, feature_tools


def test_allowlist_tools_use_existing_schemas_and_exclude_closed_features():
    tools = feature_tools()
    assert len(tools) == len(CAPABILITIES)
    assert "feature_create_checklist" not in {
        tool["function"]["name"] for tool in tools
    }
    for name in CAPABILITIES:
        handler, model = contract(name)
        assert callable(handler)
        assert model.model_json_schema()["additionalProperties"] is False
    assert not set(ENTRIES.values()) & {
        ("实时语音", "/voice-live"),
        ("医疗安排", "/appointments"),
    }
    assert not any(
        "appointments" in spec[0] or "document_review" in spec[0]
        for spec in CAPABILITIES.values()
    )


@pytest.mark.parametrize(
    "name,payload",
    [
        ("create_meal", {"body": {"dish": "番茄炒蛋", "diners": 0}}),
        ("create_folder", {"body": {"name": "  "}}),
        (
            "check_item",
            {
                "checklist_id": "清单",
                "item_id": "护照",
                "body": {"completed": True, "sql": "delete"},
            },
        ),
        ("edit_todo", {"id": "待办", "body": {"title": "x"}, "user_id": str(uuid4())}),
        (
            "commit_dump",
            {
                "dump_id": "原文",
                "body": {"candidates": [{"title": "事项", "type": "event"}]},
            },
        ),
        (
            "edit_event",
            {
                "event_id": "日程",
                "body": {
                    "title": "x",
                    "start_date": "2026-09-18",
                    "end_date": "2026-09-18",
                    "start_time": "18:00",
                    "end_time": "25:00",
                },
            },
        ),
    ],
)
def test_invalid_or_unbounded_parameters_fail_closed(name, payload):
    with pytest.raises(APIError):
        features.validate(name, payload)
    with pytest.raises(APIError):
        features.validate("execute_sql", {})


def test_create_meal_waits_for_confirmation_then_calls_existing_route(monkeypatch):

    user = SimpleNamespace(id=uuid4())
    store, session = Mock(), Mock()
    create = Mock(return_value=SimpleNamespace())
    _, model = contract("create_meal")
    monkeypatch.setattr(features, "contract", lambda _: (create, model))
    monkeypatch.setattr(
        features,
        "result_reply",
        lambda name, value: AssistantReply(kind="success", message="餐食已创建"),
    )
    draft = features.feature_reply(
        "create_meal",
        {
            "body": {
                "dish": "番茄炒蛋",
                "date": "2026-09-19",
                "meal_type": "dinner",
                "diners": 2,
            }
        },
        store,
        user,
        session,
        uuid4(),
    )
    assert draft.kind == "confirm" and draft.action_token
    assert "番茄炒蛋" in draft.message and "2026-09-19" in draft.message
    assert "晚餐" in draft.message and "用餐人数：2" in draft.message
    create.assert_not_called()
    assert store.set.call_args.kwargs["ex"] == 300
    result = features.invoke(
        "create_meal", {"body": {"dish": "番茄炒蛋"}}, user, session
    )
    assert result.kind == "success"
    assert create.call_args.kwargs["body"].dish == "番茄炒蛋"
    assert create.call_args.kwargs["user"] is user
    contract.cache_clear()


def test_readonly_review_calls_real_route_without_confirmation(monkeypatch):

    review = Mock(return_value={"summary": {"completed_todos": 3, "events": 2}})
    _, model = contract("review_plan")
    monkeypatch.setattr(features, "contract", lambda _: (review, model))
    store, session = Mock(), Mock()
    reply = features.feature_reply(
        "review_plan",
        {"query": {"date_from": "2026-09-14", "date_to": "2026-09-20"}},
        store,
        SimpleNamespace(id=uuid4()),
        session,
        uuid4(),
    )
    assert reply.kind == "result"
    assert "已完成待办：3" in reply.message
    assert "日程：2" in reply.message
    store.set.assert_not_called()
    review.assert_called_once()
    contract.cache_clear()


def test_duplicate_targets_never_generate_confirmation():
    session, store = Mock(), Mock()
    session.scalars.return_value = [
        SimpleNamespace(id=uuid4()),
        SimpleNamespace(id=uuid4()),
    ]
    reply = features.feature_reply(
        "delete_meal",
        {"meal_id": "晚餐"},
        store,
        SimpleNamespace(id=uuid4()),
        session,
        uuid4(),
    )
    assert reply.kind == "clarify"
    store.set.assert_not_called()


def test_child_title_is_scoped_to_resolved_checklist():
    session = Mock()
    checklist_id, item_id = uuid4(), uuid4()
    session.scalars.side_effect = [
        [SimpleNamespace(id=checklist_id, title="出行")],
        [SimpleNamespace(id=item_id, title="护照")],
    ]
    args, labels = bind_targets(
        "check_item",
        {"checklist_id": "出行", "item_id": "护照", "body": {"completed": True}},
        SimpleNamespace(id=uuid4()),
        session,
    )
    assert args["checklist_id"] == str(checklist_id)
    assert args["item_id"] == str(item_id)
    assert labels["checklist_id"] == "出行" and labels["item_id"] == "护照"
    child_query = str(session.scalars.call_args_list[1].args[0])
    assert "checklist_items.checklist_id" in child_query


def test_checklist_short_name_resolves_only_when_unique():
    session = Mock()
    checklist_id = uuid4()
    session.scalars.side_effect = [
        [],
        [SimpleNamespace(id=checklist_id, title="红烧肉材料")],
    ]
    args, labels = bind_targets(
        "add_checklist_item",
        {"checklist_id": "红烧肉清单", "body": {"title": "冰糖"}},
        SimpleNamespace(id=uuid4()),
        session,
    )
    assert args["checklist_id"] == str(checklist_id)
    assert labels["checklist_id"] == "红烧肉材料"


def test_checklist_short_name_does_not_choose_between_multiple_matches():
    session = Mock()
    session.scalars.side_effect = [
        [],
        [
            SimpleNamespace(id=uuid4(), title="红烧肉材料"),
            SimpleNamespace(id=uuid4(), title="红烧肉备料"),
        ],
    ]
    with pytest.raises(APIError) as error:
        bind_targets(
            "add_checklist_item",
            {"checklist_id": "红烧肉清单", "body": {"title": "冰糖"}},
            SimpleNamespace(id=uuid4()),
            session,
        )
    assert error.value.code == "AMBIGUOUS_TARGET"


def test_feature_result_cards_and_long_excerpts_are_bounded():
    value = {
        "items": [
            {"id": str(uuid4()), "name": "示例.txt", "status": "uploaded"}
            for _ in range(30)
        ]
    }
    reply = result_reply("list_materials", value)
    assert len(reply.items) == 20
    assert all(item.url == "/documents" for item in reply.items)
    assert len(reply.message) < 1000
    assert "完整内容" in reply.message
    assert "None" not in result_reply("delete_meal", None).message


def test_checklist_detail_card_points_to_parent_not_child():
    parent, child = uuid4(), uuid4()
    reply = result_reply(
        "get_checklist",
        {
            "id": str(parent),
            "title": "旅行",
            "items": [{"id": str(child), "title": "护照", "completed": False}],
        },
    )
    assert len(reply.items) == 1
    assert reply.items[0].id == parent
    assert reply.items[0].url == f"/checklists/{parent}"


def test_partial_meal_edit_preserves_existing_fields(monkeypatch):
    from backend.api.routes import life
    from backend.features.assistant.feature_edits import complete_edit

    source = Mock()
    source.model_dump.return_value = {
        "id": str(uuid4()),
        "title": "晚餐",
        "schedule_text": "晚餐",
        "date": "2026-09-19",
        "meal_type": "dinner",
        "diners": 2,
        "dish": "番茄炒蛋",
        "notes": "原备注",
        "preferences": [],
    }
    monkeypatch.setattr(life, "get_meal", lambda *_: source)
    args = complete_edit(
        "edit_meal",
        {"meal_id": str(uuid4()), "body": {"dish": "炒青菜"}},
        Mock(),
        Mock(),
    )
    assert args["body"]["dish"] == "炒青菜"
    assert args["body"]["date"] == "2026-09-19"
    assert args["body"]["diners"] == 2
    assert args["body"]["notes"] == "原备注"


def test_global_search_excludes_closed_entries(monkeypatch):
    from backend.api.routes import hub
    from backend.api.routes.assistant_threads import search_reply

    values = [
        SimpleNamespace(id=uuid4(), kind="contact", title="联系人", url="/contacts"),
        SimpleNamespace(
            id=uuid4(), kind="pantry", title="胡萝卜", url="/meals/settings"
        ),
        SimpleNamespace(
            id=uuid4(), kind="checklist", title="旅行清单", url="/checklists/abc"
        ),
    ]
    monkeypatch.setattr(hub, "search", lambda *_: SimpleNamespace(items=values))
    reply = search_reply(
        SimpleNamespace(query="旅行", target_type=None), Mock(), Mock()
    )
    assert [item.title for item in reply.items] == ["旅行清单"]
