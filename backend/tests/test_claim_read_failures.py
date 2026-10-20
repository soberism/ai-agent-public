from collections import deque

import pytest

from backend.core.security import APIError
from backend.features.assistant.answer_claims import AnswerClaim
from backend.features.assistant.answer_guard import guard_decision
from backend.features.assistant.autonomous_types import AutonomousContext, Decision
from backend.features.assistant.autonomous_workflow import run


def test_service_failure_records_failed_evidence_and_keeps_successful_query():
    scope = {"date_from": "2026-10-15", "date_to": "2026-11-15"}
    claims = [
        AnswerClaim(
            kind="count", domain="event", scope=scope, value=1, evidence_ids=["read-1"]
        ),
        AnswerClaim(
            kind="count",
            domain="todo",
            scope={**scope, "status": "ongoing"},
            value=0,
            evidence_ids=["read-2"],
        ),
    ]
    choices = deque(
        [
            Decision(
                action="read_api", tool_name="list_events", arguments={"query": scope}
            ),
            Decision(
                action="read_api", tool_name="list_todos", arguments={"query": scope}
            ),
            Decision(action="final_answer", answer_kind="business", claims=claims),
            Decision(action="final_answer", answer_kind="business", claims=claims),
        ]
    )

    def reader(tool, _):
        if tool == "list_todos":
            raise APIError(503, "SERVICE_UNAVAILABLE", "内部敏感异常详情")
        return {"items": [{"id": "e"}], "total_count": 1, "complete": True}

    result = run(
        "近期安排",
        AutonomousContext(
            lambda state: guard_decision(state, choices.popleft()), reader
        ),
    )
    assert "日程1项" in result["final_answer"]
    assert "其余结论暂未核实" in result["final_answer"]
    assert "敏感异常" not in str(result)
    assert len(result["decision"]["claims"]) == 1


@pytest.mark.parametrize("status", [401, 403, 422])
def test_auth_and_parameter_errors_still_stop_the_run(status):
    def reader(*_):
        raise APIError(status, "ACCESS_DENIED", "拒绝")

    with pytest.raises(APIError):
        run(
            "查询日程",
            AutonomousContext(
                lambda _: Decision(
                    action="read_api",
                    tool_name="list_events",
                    arguments={
                        "query": {"date_from": "2026-10-15", "date_to": "2026-10-15"}
                    },
                ),
                reader,
            ),
        )


def test_long_verified_fields_are_bounded_without_truncating_a_claim():
    from backend.features.assistant.autonomous_types import initial_state

    state = initial_state("显示详情")
    items = [
        {"id": str(index), "title": "事项", "description": "内容" * 1200}
        for index in range(2)
    ]
    state["observations"] = [
        {"tool_name": "get_todo", "arguments": {}, "result": {"items": items}}
    ]
    claims = [
        AnswerClaim(
            kind="field",
            domain="todo",
            subject_id=str(index),
            path=f"/items/{index}/description",
            value=item["description"],
            evidence_ids=["read-1"],
        )
        for index, item in enumerate(items)
    ]
    result = guard_decision(
        state, Decision(action="final_answer", answer_kind="business", claims=claims)
    )
    assert len(result.answer) < 4000
    assert len(result.claims) == 1
    assert "内容" * 1200 in result.answer
    assert "较长" in result.answer
