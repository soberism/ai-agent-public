from backend.features.assistant import autonomous_model
from backend.features.assistant.autonomous_types import Decision, initial_state


def test_answer_repair_discovers_missing_domains_and_exposes_read_schemas():
    from backend.features.assistant.autonomous_workflow import revise_answer

    state = initial_state("有什么待办和日程")
    state["described_tools"] = [autonomous_model.tool_registry.describe("list_todos")]
    state["decision"] = Decision(
        action="revise_answer", answer="日程尚未核实", requested_domains=["event"]
    ).model_dump()
    state.update(revise_answer(state))
    offered = {
        item["function"]["name"] for item in autonomous_model.direct_read_tools(state)
    }
    assert "list_events" in offered
    assert "list_todos" not in offered
    assert state["claim_retries"] == 1
    state["stalled_on"] = "read:duplicate"
    assert autonomous_model.direct_read_tools(state) == []
