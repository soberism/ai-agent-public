from backend.features.assistant.answer_guard import guard_decision
from backend.features.assistant.autonomous_types import Decision, initial_state


def test_current_business_request_uses_semantic_metadata_to_read_first():
    state = initial_state("最近有什么安排")
    decision = Decision(
        action="final_answer",
        answer_kind="business",
        requires_current_data=True,
        answer="空的",
    )
    assert guard_decision(state, decision).action == "search_tools"
    state["discovered_tools"] = [{"name": "list_todos"}]
    assert guard_decision(state, decision).action == "revise_answer"
    state["claim_retries"] = 1
    assert "还没能核实" in guard_decision(state, decision).answer


def test_document_missing_evidence_triggers_retrieval_then_bounded_repair():
    state = initial_state("文件写了什么")
    decision = Decision(
        action="final_answer", answer_kind="document", answer="未经核实的内容"
    )
    assert guard_decision(state, decision).action == "retrieve_knowledge"
    state["knowledge_count"] = 1
    assert guard_decision(state, decision).action == "revise_answer"


def test_execution_success_requires_execution_evidence_even_after_approval():
    state = initial_state("创建事项")
    decision = Decision(action="final_answer", answer_kind="execution", answer="已创建")
    for approval in ({}, {"approved": True}):
        state["approval"] = approval
        assert "还没有这项操作已完成的结果" in guard_decision(state, decision).answer


def test_conversation_and_clarification_are_not_filtered_by_keywords():
    for kind, text in (
        ("conversation", "“已创建”是一个表示完成的说法。"),
        ("clarification", "你希望查看待办还是日程？"),
    ):
        state = initial_state("解释一下这句话")
        decision = Decision(action="final_answer", answer_kind=kind, answer=text)
        assert guard_decision(state, decision) == decision


def test_tool_discovery_query_stays_within_contract_limit():
    decision = Decision(
        action="final_answer",
        answer_kind="business",
        requires_current_data=True,
        answer="不清楚",
    )
    result = guard_decision(initial_state("查询安排" * 200), decision)
    assert result.action == "search_tools" and len(result.query) == 300
