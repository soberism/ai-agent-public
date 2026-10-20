from backend.features.assistant.answer_claims import AnswerClaim
from backend.features.assistant.autonomous_types import initial_state
from backend.features.assistant.claim_verification import verify
from backend.features.assistant.model_input import selected_evidence


def test_account_scalar_without_object_id_is_bound_to_authorized_root_read():
    state = initial_state("昵称是什么")
    state["observations"] = [
        {"tool_name": "get_settings", "arguments": {}, "result": {"nickname": "小周"}}
    ]
    claim = AnswerClaim(
        kind="field",
        domain="settings",
        path="/nickname",
        value="小周",
        evidence_ids=["read-1"],
    )
    assert "小周" in verify(state, [claim])[0][0]
    assert verify(state, [claim.model_copy(update={"subject_id": "another-account"})])[
        1
    ]


def test_review_object_field_uses_its_actual_business_domain():
    item = {"id": "todo-1", "title": "事项", "status": "completed"}
    state = initial_state("回顾事项")
    state["observations"] = [
        {
            "tool_name": "review_plan",
            "arguments": {},
            "result": {"items": [item], "details": {"completed": [item]}},
        }
    ]
    claim = AnswerClaim(
        kind="field",
        domain="todo",
        path="/items/0/status",
        subject_id="todo-1",
        value="completed",
        evidence_ids=["read-1"],
    )
    assert "已完成" in verify(state, [claim])[0][0]
    assert verify(state, [claim.model_copy(update={"domain": "event"})])[1]


def test_raw_business_objects_are_not_published_as_field_values():
    state = initial_state("详情")
    state["observations"] = [
        {
            "tool_name": "get_todo",
            "arguments": {},
            "result": {"id": "t1", "description": {"internal": "不能输出原始对象"}},
        }
    ]
    claim = AnswerClaim(
        kind="field",
        domain="todo",
        path="/description",
        subject_id="t1",
        value={"internal": "不能输出原始对象"},
        evidence_ids=["read-1"],
    )
    assert verify(state, [claim])[1]


def test_evidence_ids_remain_stable_when_only_recent_records_are_sent_to_model():
    state = initial_state("查询")
    state["observations"] = [
        {
            "tool_name": "list_todos",
            "arguments": {"query": {"due": "all"}},
            "result": {"items": [], "complete": True, "total_count": 0},
        }
        for _ in range(5)
    ]
    state["read_count"] = 8
    evidence = selected_evidence(state)
    assert [item["evidence_id"] for item in evidence] == [
        "read-2",
        "read-3",
        "read-4",
        "read-5",
    ]
    assert all(item["scope"] == {"status": "ongoing"} for item in evidence)


def test_global_review_counter_cannot_be_presented_as_a_date_filtered_count():
    state = initial_state("本周清单数量")
    scope = {"date_from": "2026-10-12", "date_to": "2026-10-18"}
    state["observations"] = [
        {
            "tool_name": "review_plan",
            "arguments": {"query": scope},
            "result": {"complete": True, "summary": {"checklists": 4}},
        }
    ]
    claim = AnswerClaim(
        kind="count", domain="checklist", value=4, scope=scope, evidence_ids=["read-1"]
    )
    assert verify(state, [claim])[1]
    claim.scope = {}
    assert not verify(state, [claim])[1]
