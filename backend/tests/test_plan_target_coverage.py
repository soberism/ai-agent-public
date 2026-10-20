from collections import deque
from unittest.mock import Mock

import pytest

from backend.features.assistant.autonomous_types import (
    AutonomousContext,
    Decision,
    initial_state,
)
from backend.features.assistant.autonomous_workflow import run
from backend.features.assistant.plan_targets import check_target_coverage

TODO = {
    "kind": "todo",
    "id": "11111111-1111-1111-1111-111111111111",
    "title": "接孩子",
    "reference_origin": "last_result",
}
EVENT = {
    "kind": "event",
    "id": "22222222-2222-2222-2222-222222222222",
    "title": "去乐天玛特",
    "reference_origin": "last_result",
}
ACTIONS = [
    {"tool_name": "delete_todo", "arguments": {"id": TODO["id"]}},
    {"tool_name": "delete_event", "arguments": {"event_id": EVENT["id"]}},
]


def state():
    return initial_state("都删除吧", last_results=[TODO, EVENT])


@pytest.mark.parametrize(
    "actions",
    [
        [ACTIONS[1]],
        [ACTIONS[0]],
        ACTIONS + [ACTIONS[0]],
        [{"tool_name": "delete_event", "arguments": {"event_id": "unrelated"}}],
    ],
)
def test_partial_duplicate_or_unrelated_delete_is_not_offered_for_confirmation(actions):
    result = check_target_coverage(state(), actions)
    assert result["stalled_on"].startswith("invalid-plan:target-coverage")
    assert "接孩子" in result["stalled_on"] and "去乐天玛特" in result["stalled_on"]
    assert {"delete_todo", "delete_event"} <= {
        item["name"] for item in result["described_tools"]
    }


def test_previous_results_exclude_other_recent_action_candidates():
    value = state()
    value["last_results"].append(
        {**TODO, "id": "old", "title": "旧事项", "reference_origin": "recent_action"}
    )
    assert check_target_coverage(value, ACTIONS) is None
    assert check_target_coverage(
        value, ACTIONS + [{"tool_name": "delete_todo", "arguments": {"id": "old"}}]
    )


def test_explicit_narrower_request_does_not_expand_to_other_types():
    value = state()
    value["prompt"] = "只删除去乐天玛特这个日程"
    assert check_target_coverage(value, [ACTIONS[1]]) is None


def test_collective_delete_requires_previous_result_scope():
    value = initial_state("都删除吧")
    assert "明确要操作" in check_target_coverage(value, [ACTIONS[1]])["final_answer"]


def test_batch_events_and_todo_must_cover_exactly_the_previous_objects():
    actions = [
        ACTIONS[0],
        {
            "tool_name": "delete_events",
            "arguments": {
                "body": {
                    "event_ids": [EVENT["id"]],
                    "date_from": "2026-10-01",
                    "date_to": "2026-10-31",
                }
            },
        },
    ]
    assert check_target_coverage(state(), actions) is None


def test_incomplete_plan_repairs_to_two_confirmable_actions_without_deleting():
    choices = deque(
        [
            Decision(action="propose_actions", actions=[ACTIONS[1]]),
            Decision(action="propose_actions", actions=ACTIONS),
        ]
    )
    reader = Mock(side_effect=AssertionError("本测试不得执行删除"))
    result = run(
        "都删除吧",
        AutonomousContext(lambda _: choices.popleft(), reader),
        context_data={"last_results": [TODO, EVENT]},
    )
    actions = result["__interrupt__"][0].value["actions"]
    assert [item["tool_name"] for item in actions] == ["delete_todo", "delete_event"]
    assert not result["approval"]
    reader.assert_not_called()


def test_second_incomplete_plan_stops_instead_of_publishing_partial_plan():
    value = state()
    value["stalled_on"] = "invalid-plan:target-coverage: first failure"
    result = check_target_coverage(value, [ACTIONS[1]])
    assert "没有执行操作" in result["final_answer"]
    assert result["decision"]["action"] == "final_answer"
