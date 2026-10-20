"""Agent plan persistence and graph dispatch coverage."""

from collections import deque
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from backend.api.routes import assistant_features as features
from backend.api.routes import assistant_read_steps as read_steps
from backend.core.security import APIError
from backend.features.assistant.agent_plan_persistence import persist_plan
from backend.features.assistant.autonomous_types import AutonomousContext, Decision
from backend.features.assistant.autonomous_workflow import run
from backend.features.assistant.feature_tools import parse_arguments


def test_single_body_tool_accepts_flat_model_arguments():
    parsed = features.validate(
        "delete_events",
        {
            "date_from": "2026-11-01",
            "date_to": "2026-11-30",
            "event_ids": [str(uuid4())],
        },
    )
    assert parsed.body.date_from.isoformat() == "2026-11-01"


def test_flat_batch_delete_reaches_action_plan(monkeypatch):
    from backend.features.assistant import autonomous_plan
    from backend.features.assistant.autonomous_types import initial_state
    from backend.features.assistant.tool_registry import describe

    event_ids = [str(uuid4()) for _ in range(30)]
    state = initial_state("删除11月份的所有日程")
    state["described_tools"] = [describe("delete_events")]
    state["observations"] = [
        {
            "tool_name": "list_events",
            "arguments": {
                "query": {"date_from": "2026-11-01", "date_to": "2026-11-30"}
            },
            "result": {
                "complete": True,
                "total_count": len(event_ids),
                "items": [{"id": value} for value in event_ids],
            },
        }
    ]
    state["decision"] = {
        "action": "propose_actions",
        "actions": [
            {
                "tool_name": "delete_events",
                "arguments": {
                    "date_from": "2026-11-01",
                    "date_to": "2026-11-30",
                    "event_ids": event_ids,
                },
            }
        ],
    }
    monkeypatch.setattr(autonomous_plan, "interrupt", lambda value: value)

    result = autonomous_plan.propose(state)

    action = result["proposed_actions"][0]
    assert action["arguments"]["body"]["event_ids"] == event_ids


@pytest.mark.parametrize(
    "alias", ["toggle_checklist_item", "check_checklist_item", "mark_checklist_item"]
)
def test_checklist_toggle_alias_reaches_confirmable_plan(monkeypatch, alias):
    from backend.features.assistant import autonomous_plan
    from backend.features.assistant.autonomous_types import initial_state

    state = initial_state("关燃气我做过了")
    state["decision"] = {
        "action": "propose_actions",
        "actions": [
            {
                "tool_name": alias,
                "arguments": {
                    "checklist_id": str(uuid4()),
                    "item_id": str(uuid4()),
                    "completed": True,
                },
            }
        ],
    }
    monkeypatch.setattr(autonomous_plan, "interrupt", lambda value: value)

    action = autonomous_plan.propose(state)["proposed_actions"][0]

    assert action["tool_name"] == "check_item"
    assert action["arguments"]["body"] == {"completed": True}


def test_sharing_plan_without_household_never_reaches_confirmation():
    from backend.features.assistant import autonomous_plan
    from backend.features.assistant.autonomous_types import initial_state
    from backend.features.assistant.tool_registry import describe

    state = initial_state("把刚创建的日程改成家人可见")
    state["described_tools"] = [describe("set_sharing")]
    state["decision"] = {
        "action": "propose_actions",
        "actions": [
            {
                "tool_name": "set_sharing",
                "arguments": {
                    "kind": "event",
                    "resource_id": str(uuid4()),
                    "body": {"scope": "household"},
                },
            }
        ],
    }

    result = autonomous_plan.propose(state)

    assert result["stalled_on"].startswith("invalid-plan:set_sharing:")
    assert "必须选择家庭" in result["stalled_on"]


def test_sharing_plan_accepts_full_household_name_before_target_binding():
    parsed = parse_arguments(
        "set_sharing",
        {
            "kind": "event",
            "resource_id": "今晚打王者",
            "body": {"scope": "household", "household_id": "我爱我家"},
        },
    )

    assert parsed.body.household_id == "我爱我家"


def test_today_todo_prompt_graph_dispatches_the_new_tool(monkeypatch):
    handler = Mock(
        return_value=SimpleNamespace(
            model_dump=lambda **_: {"items": [], "next_cursor": None},
        )
    )
    monkeypatch.setattr(read_steps, "listing", handler)
    choices = deque(
        [
            Decision(action="search_tools", query="查看我今天的待办"),
            Decision(action="describe_tools", names=["list_todos"]),
            Decision(
                action="read_api",
                tool_name="list_todos",
                arguments={"query": {"due": "today"}},
            ),
            Decision(action="final_answer", answer="今天没有待办。"),
        ]
    )
    store, user, session, thread_id = (
        Mock(),
        SimpleNamespace(id=uuid4()),
        Mock(),
        uuid4(),
    )
    result = run(
        "查看我今天的待办",
        AutonomousContext(
            lambda _: choices.popleft(),
            lambda name, args: read_steps.inspect(
                name, args, store, user, session, thread_id
            ),
        ),
    )
    assert result["final_answer"] == "今天没有待办。"
    assert result["read_count"] == 1
    assert handler.call_args.args[0].due == "today"


def test_persisted_plan_uses_server_preview_not_model_description(monkeypatch):
    from backend.features.assistant import agent_plan_persistence

    target = uuid4()
    monkeypatch.setattr(
        agent_plan_persistence,
        "prepare",
        lambda *_: ({"id": str(target)}, {"id": "买菜"}),
    )
    session = Mock()
    run_row = SimpleNamespace(
        id=uuid4(),
        parent_plan_id=None,
        thread_id=uuid4(),
        plan_version=0,
        final_answer=None,
        status="running",
        progress=None,
        error=None,
        lease_expires_at=None,
        updated_at=None,
    )
    session.scalars.return_value = []
    session.get.return_value = None
    persist_plan(
        session,
        run_row,
        SimpleNamespace(id=uuid4()),
        [
            {
                "tool_name": "delete_todo",
                "arguments": {"id": str(target)},
                "description": "无需确认",
            }
        ],
    )
    action = session.add.call_args_list[0].args[0]
    assert "买菜" in action.description
    assert "无需确认" not in action.description


def test_wrong_checklist_item_cannot_be_confirmed(monkeypatch):
    from backend.features.assistant import agent_plan_persistence

    monkeypatch.setattr(
        agent_plan_persistence,
        "prepare",
        lambda *_: (
            {"checklist_id": str(uuid4()), "item_id": str(uuid4())},
            {"item_id": "关燃气"},
        ),
    )
    monkeypatch.setattr(agent_plan_persistence, "same_checklist_item", lambda *_: False)
    session = Mock()
    session.scalars.return_value = []
    run_row = SimpleNamespace(
        id=uuid4(), thread_id=uuid4(), parent_plan_id=None, prompt="删除检查窗帘"
    )

    with pytest.raises(APIError, match="清单项与请求不一致"):
        persist_plan(
            session,
            run_row,
            SimpleNamespace(id=uuid4()),
            [{"tool_name": "delete_checklist_item", "arguments": {}}],
        )
    session.add.assert_not_called()


def test_checklist_item_preview_uses_readable_label():
    from backend.features.assistant.feature_replies import preview

    assert preview({"item_id": "item-id"}, {"item_id": "关燃气"}) == "清单项：关燃气"


def test_successful_replan_cancels_the_superseded_waiting_plan(monkeypatch):
    from backend.features.assistant import agent_plan_persistence

    monkeypatch.setattr(
        agent_plan_persistence, "prepare", lambda *_: ({"body": {}}, {})
    )
    session = Mock()
    old_run = SimpleNamespace(
        id=uuid4(),
        status="waiting",
        plan_version=1,
        progress=None,
        error=None,
        updated_at=None,
    )
    old_action = SimpleNamespace(status="proposed")
    session.scalar.return_value = old_run
    session.scalars.return_value = [old_action]
    run_row = SimpleNamespace(
        id=uuid4(),
        thread_id=uuid4(),
        parent_plan_id=old_run.id,
        task_context={"plan_version": 1},
        plan_version=0,
        final_answer=None,
        status="running",
        progress=None,
        error=None,
        lease_expires_at=None,
        updated_at=None,
    )
    persist_plan(
        session,
        run_row,
        SimpleNamespace(id=uuid4()),
        [{"tool_name": "create_todo", "arguments": {}}],
    )
    assert old_run.status == "cancelled"
    assert old_action.status == "cancelled"
