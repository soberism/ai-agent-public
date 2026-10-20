import json
from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import ValidationError

from backend.features.assistant.autonomous_model import parse_decision
from backend.features.assistant.autonomous_types import (
    AutonomousContext,
    Decision,
    initial_state,
)
from backend.features.assistant.autonomous_workflow import run
from backend.features.assistant.tool_registry import describe


def state():
    value = initial_state("把这个日程改到12点")
    value["described_tools"] = [describe("edit_event")]
    return value


def arguments():
    return {
        "event_id": str(uuid4()),
        "body": {
            "title": "回归日程",
            "start_date": "2026-11-12",
            "start_time": "12:00",
            "end_date": "2026-11-12",
            "end_time": "15:00",
        },
    }


def test_single_flat_proposal_is_normalized_without_losing_semantic_context():
    args = arguments()
    decision = parse_decision(
        json.dumps(
            {
                "action": "propose_actions",
                "tool_name": "edit_event",
                "arguments": args,
                "resolved_request": "把当前日程开始时间调整到12点",
                "requires_current_data": True,
            }
        ),
        state(),
    )
    assert decision.actions == [{"tool_name": "edit_event", "arguments": args}]
    assert decision.requires_current_data
    assert "12点" in decision.resolved_request
    assert decision.action == "propose_actions"


@pytest.mark.parametrize("name", ["get_event", "unknown_write"])
def test_read_or_unknown_tool_cannot_be_reinterpreted_as_write_proposal(name):
    value = state()
    value["described_tools"].append(describe("get_event"))
    with pytest.raises(ValidationError):
        parse_decision(
            json.dumps(
                {"action": "propose_actions", "tool_name": name, "arguments": {}}
            ),
            value,
        )


def test_registered_write_can_normalize_before_schema_expansion():
    value = initial_state("调整日程时间")
    decision = parse_decision(
        json.dumps(
            {
                "action": "propose_actions",
                "tool_name": "edit_event",
                "arguments": arguments(),
            }
        ),
        value,
    )
    assert decision.actions[0]["tool_name"] == "edit_event"


def test_conflicting_or_malformed_flat_proposals_remain_invalid():
    for fields in (
        {"actions": [{"tool_name": "edit_event", "arguments": arguments()}]},
        {"arguments": []},
    ):
        data = {
            "action": "propose_actions",
            "tool_name": "edit_event",
            "arguments": arguments(),
            **fields,
        }
        with pytest.raises(ValueError):
            parse_decision(json.dumps(data), state())


def test_action_schema_describes_required_nested_fields_and_rejects_missing_parameters():
    schema = Decision.model_json_schema()
    reference = schema["properties"]["actions"]["items"]["$ref"].rsplit("/", 1)[-1]
    assert set(schema["$defs"][reference]["required"]) == {"tool_name", "arguments"}
    for action in ({"tool_name": "edit_event"}, {"arguments": {}}, "edit_event"):
        with pytest.raises(ValidationError):
            Decision(action="propose_actions", actions=[action])


def test_normalized_proposal_still_interrupts_for_confirmation_without_executing():
    decision = parse_decision(
        json.dumps(
            {
                "action": "propose_actions",
                "tool_name": "edit_event",
                "arguments": arguments(),
            }
        ),
        state(),
    )
    reads = []
    result = run(
        "调整日程时间",
        AutonomousContext(lambda _: decision, lambda *args: reads.append(args)),
        checkpointer=InMemorySaver(),
        config={"configurable": {"thread_id": str(uuid4())}},
    )
    assert result["__interrupt__"][0].value["actions"][0]["tool_name"] == "edit_event"
    assert not reads
    assert not result["approval"]


def test_partial_single_proposal_returns_schema_feedback_then_waits_for_approval():
    value = initial_state("调整日程到12点")
    value["described_tools"] = [describe("get_event")]
    args = arguments()
    first = parse_decision(
        json.dumps(
            {
                "action": "propose_actions",
                "tool_name": "edit_event",
                "arguments": {"event_id": args["event_id"], "start_time": "12:00"},
            }
        ),
        value,
    )
    seen = []

    def decide(state):
        seen.append(state.copy())
        if len(seen) == 1:
            return first
        assert state["stalled_on"].startswith("invalid-plan:edit_event")
        assert any(item["name"] == "edit_event" for item in state["described_tools"])
        return Decision(
            action="propose_actions",
            actions=[{"tool_name": "edit_event", "arguments": args}],
        )

    result = run(
        value["prompt"],
        AutonomousContext(decide, lambda *_: pytest.fail("不得执行写工具")),
        checkpointer=InMemorySaver(),
        config={"configurable": {"thread_id": str(uuid4())}},
    )
    assert result["__interrupt__"]
    assert not result["approval"]
