from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.core.security import APIError
from backend.features.assistant import answer_suggestions


def result(kind, target_id, status="ongoing"):
    return {
        "kind": "result",
        "items": [
            {
                "id": str(target_id),
                "kind": kind,
                "title": "买牛奶",
                "status": status,
            }
        ],
    }


@pytest.mark.parametrize("kind", ["todo", "event", "reminder", "checklist"])
def test_single_verified_object_gets_supported_next_steps(kind):
    run_id, target_id = uuid4(), uuid4()
    suggestions = answer_suggestions.from_result(run_id, result(kind, target_id))

    assert len(suggestions) == (1 if kind in {"todo", "event"} else 2)
    assert all(item["intent"] != "create_reminder" for item in suggestions)
    assert all(item["source_run_id"] == str(run_id) for item in suggestions)
    assert all(item["target_id"] == str(target_id) for item in suggestions)
    assert all(item["target_kind"] == kind for item in suggestions)


def test_ambiguous_or_failed_results_have_no_suggestions():
    run_id, target_id = uuid4(), uuid4()
    ambiguous = result("todo", target_id)
    ambiguous["items"].append({**ambiguous["items"][0], "id": str(uuid4())})
    assert answer_suggestions.from_result(run_id, ambiguous) == []
    assert (
        answer_suggestions.from_result(
            run_id, {"kind": "clarify", "items": ambiguous["items"]}
        )
        == []
    )
    assert (
        answer_suggestions.from_actions(
            run_id,
            [
                SimpleNamespace(
                    status="failed",
                    tool_name="edit_todo",
                    result=result("todo", target_id),
                )
            ],
        )
        == []
    )


def test_checklist_item_id_is_not_used_as_checklist_target():
    action = SimpleNamespace(
        status="completed",
        tool_name="add_checklist_item",
        result=result("checklist", uuid4()),
    )
    assert answer_suggestions.from_actions(uuid4(), [action]) == []

    event_id = uuid4()
    event = SimpleNamespace(
        status="completed", tool_name="create_event", result=result("event", event_id)
    )
    assert answer_suggestions.from_actions(uuid4(), [event])[0]["target_id"] == str(
        event_id
    )


def test_selection_rechecks_target_and_rejects_stale_object(monkeypatch):
    run_id, target_id = uuid4(), uuid4()
    suggestion = answer_suggestions.from_result(run_id, result("todo", target_id))[0]
    source = SimpleNamespace(id=run_id, status="completed", suggestions=[suggestion])
    calls = []

    def read(name, arguments, *_):
        calls.append((name, arguments))
        return SimpleNamespace(
            items=[SimpleNamespace(id=target_id, title="买牛奶", status="ongoing")]
        )

    monkeypatch.setattr(answer_suggestions, "invoke", read)
    context = answer_suggestions.resolve(
        object(), object(), source, suggestion["id"], suggestion["draft"] + "明天 14:00"
    )
    assert calls == [("get_todo", {"id": str(target_id)})]
    assert context["target_id"] == str(target_id)
    assert context["intent"] == "edit_todo"

    monkeypatch.setattr(
        answer_suggestions, "invoke", lambda *_: SimpleNamespace(items=[])
    )
    with pytest.raises(APIError, match="已不可访问"):
        answer_suggestions.resolve(
            object(), object(), source, suggestion["id"], suggestion["draft"]
        )


def test_history_restores_answer_linked_suggestions():
    from backend.features.assistant.history import output

    suggestion = answer_suggestions.from_result(uuid4(), result("event", uuid4()))[0]
    saved = [
        SimpleNamespace(
            id=uuid4(),
            role="assistant",
            kind="result",
            content="已创建日程",
            items=None,
            suggestions=[suggestion],
        )
    ]
    assert output(saved)[0]["reply"]["suggestions"] == [suggestion]


def test_suggestion_plan_can_only_change_its_bound_object():
    target_id = str(uuid4())
    context = {
        "kind": "suggestion",
        "intent": "create_reminder",
        "target_kind": "event",
        "target_id": target_id,
    }
    answer_suggestions.verify_plan(
        context, "create_reminder", {"body": {"event_id": target_id}}
    )
    with pytest.raises(APIError, match="目标事项不一致"):
        answer_suggestions.verify_plan(
            context, "create_reminder", {"body": {"event_id": str(uuid4())}}
        )
    with pytest.raises(APIError, match="待确认计划不一致"):
        answer_suggestions.verify_plan(context, "edit_event", {"event_id": target_id})


def test_plan_persistence_rejects_other_target_before_saving(monkeypatch):
    from unittest.mock import Mock

    from backend.features.assistant import agent_plan_persistence

    target_id = str(uuid4())
    monkeypatch.setattr(
        agent_plan_persistence,
        "prepare",
        lambda *_: ({"body": {"event_id": str(uuid4())}}, {}),
    )
    session = Mock()
    run = SimpleNamespace(
        id=uuid4(),
        parent_plan_id=None,
        task_context={
            "kind": "suggestion",
            "intent": "create_reminder",
            "target_kind": "event",
            "target_id": target_id,
        },
    )
    with pytest.raises(APIError, match="目标事项不一致"):
        agent_plan_persistence.persist_plan(
            session,
            run,
            SimpleNamespace(id=uuid4()),
            [{"tool_name": "create_reminder", "arguments": {}}],
        )
    session.add.assert_not_called()
