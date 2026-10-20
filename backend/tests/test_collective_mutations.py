from copy import deepcopy
from uuid import uuid4

import pytest

from backend.features.assistant import autonomous_plan
from backend.features.assistant.autonomous_types import initial_state
from backend.features.assistant.plan_targets import check_target_coverage


def targets(kind="todo"):
    return [
        {
            "kind": kind,
            "id": str(uuid4()),
            "title": f"事项{i}",
            "reference_origin": "last_result",
        }
        for i in range(2)
    ]


@pytest.mark.parametrize(
    "prompt,kind,tool,field,body",
    [
        ("都标记完成吧", "todo", "edit_todo", "id", {"status": "completed"}),
        ("这些待办都取消完成吧", "todo", "edit_todo", "id", {"status": "ongoing"}),
        (
            "这些清单全部勾选吧",
            "checklist",
            "bulk_checklist",
            "checklist_id",
            {"completed": True},
        ),
        (
            "清单都取消勾选吧",
            "checklist",
            "bulk_checklist",
            "checklist_id",
            {"completed": False},
        ),
        (
            "这些提醒都关闭吧",
            "reminder",
            "edit_reminder",
            "reminder_id",
            {"status": "disabled"},
        ),
        (
            "提醒全部开启吧",
            "reminder",
            "edit_reminder",
            "reminder_id",
            {"status": "scheduled"},
        ),
        ("这些待办都改到明天吧", "todo", "edit_todo", "id", {"due_date": "2026-10-17"}),
    ],
)
def test_collective_mutations_reject_missing_duplicate_extra_and_wrong_operation(
    prompt, kind, tool, field, body
):
    rows = targets(kind)
    state = initial_state(prompt, last_results=rows)
    actions = [
        {"tool_name": tool, "arguments": {field: row["id"], "body": body}}
        for row in rows
    ]
    assert check_target_coverage(state, actions) is None
    for wrong in (
        actions[:1],
        actions + actions[:1],
        actions
        + [{"tool_name": tool, "arguments": {field: str(uuid4()), "body": body}}],
    ):
        assert check_target_coverage(state, wrong)["stalled_on"].startswith(
            "invalid-plan:"
        )
    if (
        tool in {"edit_todo", "bulk_checklist", "edit_reminder"}
        and "due_date" not in body
    ):
        wrong = deepcopy(actions)
        wrong[1]["arguments"]["body"] = {}
        assert check_target_coverage(state, wrong)


def test_cross_kind_sharing_covers_every_object_and_same_visibility():
    rows = [targets()[0], targets("event")[0]]
    state = initial_state("都改成仅自己可见吧", last_results=rows)
    actions = [
        {
            "tool_name": "set_sharing",
            "arguments": {
                "kind": row["kind"],
                "resource_id": row["id"],
                "body": {"scope": "private"},
            },
        }
        for row in rows
    ]
    assert check_target_coverage(state, actions) is None
    assert check_target_coverage(state, actions[:1])
    actions[1]["arguments"]["body"] = {
        "scope": "household",
        "household_id": str(uuid4()),
    }
    assert check_target_coverage(state, actions)


def test_sharing_targets_cannot_drift_to_different_households():
    rows = targets()
    state = initial_state("都设为家庭可见吧", last_results=rows)
    actions = [
        {
            "tool_name": "set_sharing",
            "arguments": {
                "kind": "todo",
                "resource_id": row["id"],
                "body": {"scope": "household", "household_id": str(uuid4())},
            },
        }
        for row in rows
    ]
    assert check_target_coverage(state, actions)


def test_explicit_todo_scope_does_not_complete_events_or_old_candidates():
    rows = [
        *targets(),
        targets("event")[0],
        {**targets()[0], "reference_origin": "recent_action"},
    ]
    state = initial_state("这些待办都标记完成吧", last_results=rows)
    actions = [
        {
            "tool_name": "edit_todo",
            "arguments": {"id": row["id"], "body": {"status": "completed"}},
        }
        for row in rows[:2]
    ]
    assert check_target_coverage(state, actions) is None
    state["prompt"] = "都标记完成吧"
    assert "不支持" in check_target_coverage(state, actions)["final_answer"]


def test_complete_plan_reaches_confirmation_without_performing_writes(monkeypatch):
    rows = targets()
    state = initial_state("这些待办都标记完成吧", last_results=rows)
    state["decision"] = {
        "action": "propose_actions",
        "actions": [
            {
                "tool_name": "edit_todo",
                "arguments": {"id": row["id"], "body": {"status": "completed"}},
            }
            for row in rows
        ],
    }
    seen = []
    monkeypatch.setattr(
        autonomous_plan, "interrupt", lambda value: seen.append(value) or {}
    )
    result = autonomous_plan.propose(state)
    assert len(result["proposed_actions"]) == len(seen[0]["actions"]) == 2
    assert result["approval"] == {}


def test_explicit_named_pair_also_requires_both_targets():
    rows = targets()
    state = initial_state("把事项0和事项1标记完成", last_results=rows)
    actions = [
        {
            "tool_name": "edit_todo",
            "arguments": {"id": row["id"], "body": {"status": "completed"}},
        }
        for row in rows
    ]
    assert check_target_coverage(state, actions) is None
    assert check_target_coverage(state, actions[:1])
    state["prompt"] = "把事项0的名字改成事项1"
    assert check_target_coverage(state, actions[:1]) is None
    state["prompt"] = "除了事项0和事项1，其他都完成"
    assert check_target_coverage(state, actions[:1]) is None


def test_compound_named_operations_are_not_rewritten_as_one_operation():
    rows = targets()
    state = initial_state("删除事项0和事项1，再完成另一件事", last_results=rows)
    assert check_target_coverage(state, []) is None


def test_named_target_prefix_does_not_expand_to_another_object():
    rows = [
        {"kind": "todo", "id": str(uuid4()), "title": name}
        for name in ("事项1", "事项10", "事项2")
    ]
    state = initial_state("删除事项10和事项2", last_results=rows)
    actions = [
        {"tool_name": "delete_todo", "arguments": {"id": row["id"]}} for row in rows[1:]
    ]
    assert check_target_coverage(state, actions) is None
    assert check_target_coverage(
        state,
        actions + [{"tool_name": "delete_todo", "arguments": {"id": rows[0]["id"]}}],
    )


def test_named_pair_with_preserved_other_item_does_not_expand_mutation():
    rows = [*targets(), {"kind": "todo", "id": str(uuid4()), "title": "事项3"}]
    state = initial_state("删除事项0和事项1，保留事项3", last_results=rows)
    assert check_target_coverage(state, []) is None
