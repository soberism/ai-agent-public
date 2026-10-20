import json
from types import SimpleNamespace
from unittest.mock import Mock

from backend.features.assistant import autonomous_model
from backend.features.assistant.autonomous_types import AutonomousContext, Decision
from backend.features.assistant.autonomous_workflow import initial_state, run
from backend.features.assistant.tool_registry import search


def test_todo_title_judgement_uses_task_meaning(monkeypatch):
    calls = []

    def create(**kwargs):
        calls.append(kwargs["messages"][-1]["content"])
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="是"))]
        )

    monkeypatch.setattr(
        autonomous_model,
        "client",
        lambda: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        ),
    )
    assert autonomous_model.same_todo_target("洗牙", "去洗牙")
    assert '"用户所指": "洗牙"' in calls[0]


def test_checklist_item_judgement_rejects_other_item(monkeypatch):
    calls = []

    def create(**kwargs):
        calls.append(kwargs["messages"][-1]["content"])
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="否"))]
        )

    monkeypatch.setattr(
        autonomous_model,
        "client",
        lambda: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        ),
    )
    assert autonomous_model.same_checklist_item("关燃气我做过了", "关燃气")
    assert not autonomous_model.same_checklist_item("删除检查窗帘", "关燃气")
    assert '"候选清单项": "关燃气"' in calls[0]


def test_colloquial_tool_search_ranks_the_requested_operation_first():
    assert search("把购物清单里的牛奶删掉")[0]["name"] == "delete_shopping_item"
    assert search("我家还有多少牛奶")[0]["name"] == "list_pantry"
    assert search("我有哪些餐食禁忌")[0]["name"] == "list_preferences"
    assert search("把明天的日程改到下午三点")[0]["name"] == "edit_event"
    deletion = search("删除 偏好与限制吧 删除偏好与限制 餐食偏好设置")
    assert deletion[0]["name"] == "delete_preference"
    assert any(item["name"] == "list_preferences" for item in deletion)


def test_habit_query_discovers_saved_memories():
    assert search("我的习惯有啥")[0]["name"] == "list_memories"


def test_habit_query_reads_memories_then_answers_without_knowledge_search(monkeypatch):
    state = initial_state("我的习惯有啥")
    state["observations"] = [
        {
            "tool_name": "list_memories",
            "result": {"items": [{"id": "memory-1", "content": "早起"}]},
        }
    ]
    create = Mock(
        return_value=SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        tool_calls=[
                            SimpleNamespace(
                                function=SimpleNamespace(
                                    name="agent_decision",
                                    arguments=json.dumps(
                                        {
                                            "action": "final_answer",
                                            "answer_kind": "business",
                                            "claims": [
                                                {
                                                    "kind": "field",
                                                    "domain": "memory",
                                                    "subject_id": "memory-1",
                                                    "path": "/items/0/content",
                                                    "scope": {},
                                                    "value": "早起",
                                                    "evidence_ids": ["read-1"],
                                                }
                                            ],
                                            "answer": "记着你习惯早起。",
                                        }
                                    ),
                                )
                            )
                        ]
                    )
                )
            ]
        )
    )
    monkeypatch.setattr(
        autonomous_model,
        "settings",
        SimpleNamespace(
            llm_base_url="https://example.com",
            llm_model="test-model",
            llm_api_key=SimpleNamespace(get_secret_value=lambda: "test-key"),
        ),
    )
    monkeypatch.setattr(
        autonomous_model,
        "client",
        lambda: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        ),
    )
    assert "早起" in autonomous_model.decide(state).answer
    offered = create.call_args.kwargs["tools"]
    actions = offered[0]["function"]["parameters"]["properties"]["action"]["enum"]
    assert "final_answer" in actions and "read_api" in actions
    assert "get_preferences" in autonomous_model.SYSTEM


def test_get_todos_read_uses_registered_list_contract():
    from backend.features.assistant.feature_tools import contract

    decision = autonomous_model.parse_decision(
        '{"action":"read_api","tool_name":"get_todos","arguments":{}}',
        initial_state("查看当前待办"),
    )

    assert decision.tool_name == "list_todos"
    assert (
        contract("list_todos")[1].model_validate(decision.arguments).query.limit == 20
    )


def test_discovered_read_is_a_direct_model_tool_but_write_is_not(monkeypatch):
    state = initial_state("查看库存")
    state["discovered_tools"] = [
        {"name": "list_pantry", "description": "查询食材库存", "mode": "read"},
        {"name": "delete_shopping_item", "description": "删除购物项", "mode": "write"},
    ]
    create = Mock(
        return_value=SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        tool_calls=[
                            SimpleNamespace(
                                function=SimpleNamespace(
                                    name="list_pantry", arguments="{}"
                                )
                            )
                        ]
                    )
                )
            ]
        )
    )
    monkeypatch.setattr(
        autonomous_model,
        "settings",
        SimpleNamespace(
            llm_base_url="https://example.com",
            llm_model="test-model",
            llm_api_key=SimpleNamespace(get_secret_value=lambda: "test-key"),
        ),
    )
    monkeypatch.setattr(
        autonomous_model,
        "client",
        lambda: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        ),
    )

    decision = autonomous_model.decide(state)

    assert decision == Decision(
        action="read_api", tool_name="list_pantry", arguments={}
    )
    offered = {tool["function"]["name"] for tool in create.call_args.kwargs["tools"]}
    assert offered == {"agent_decision", "list_pantry"}
    assert create.call_args.kwargs["tool_choice"] == "auto"
    state["web_results"] = [{"title": "外部网页"}]
    assert autonomous_model.direct_read_tools(state) == []


def test_model_can_return_multiple_read_calls_without_failing(monkeypatch):
    state = initial_state("查今天待办")
    state["discovered_tools"] = [
        {"name": "list_todos", "description": "查询待办", "mode": "read"},
        {"name": "list_reminders", "description": "查询提醒", "mode": "read"},
    ]
    calls = [
        SimpleNamespace(function=SimpleNamespace(name="list_todos", arguments="{")),
        SimpleNamespace(
            function=SimpleNamespace(name="list_reminders", arguments="{}")
        ),
    ]
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=calls))]
    )
    monkeypatch.setattr(
        autonomous_model,
        "settings",
        SimpleNamespace(
            llm_base_url="https://example.com",
            llm_model="test-model",
            llm_api_key=SimpleNamespace(get_secret_value=lambda: "test-key"),
        ),
    )
    create = Mock(return_value=response)
    monkeypatch.setattr(
        autonomous_model,
        "client",
        lambda: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        ),
    )
    decision = autonomous_model.decide(state)
    assert decision.tool_name == "list_reminders"
    create.assert_called_once()

    state["stalled_on"] = "invalid-read:get_household:{}; 缺少字段: household_id"
    create.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    tool_calls=[
                        SimpleNamespace(
                            function=SimpleNamespace(
                                name="agent_decision",
                                arguments=json.dumps(
                                    {
                                        "action": "read_api",
                                        "tool_name": "list_households",
                                    }
                                ),
                            )
                        )
                    ]
                )
            )
        ]
    )
    assert autonomous_model.decide(state).tool_name == "list_households"


def test_legacy_json_read_is_stored_as_data_not_an_escaped_string():
    choices = iter(
        [
            Decision(action="search_tools", query="查询库存"),
            Decision(action="read_api", tool_name="list_pantry", arguments={}),
            Decision(action="final_answer", answer="还剩一瓶牛奶。"),
        ]
    )
    result = run(
        "我家还有多少牛奶",
        AutonomousContext(
            lambda _: next(choices),
            lambda *_: json.dumps({"items": [{"name": "牛奶", "quantity": 1}]}),
        ),
    )
    assert result["observations"][0]["result"] == {
        "items": [{"name": "牛奶", "quantity": 1}]
    }
