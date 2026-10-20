from backend.features.assistant.answer_claims import AnswerClaim
from backend.features.assistant.answer_guard import guard_decision
from backend.features.assistant.autonomous_types import Decision, initial_state
from backend.features.assistant.claim_verification import verify

SCOPE = {"date_from": "2026-10-15", "date_to": "2026-11-15"}


def read(tool, items, query=None, **extra):
    return {
        "tool_name": tool,
        "arguments": {"query": query or SCOPE},
        "result": {
            "items": items,
            "complete": True,
            "total_count": len(items),
            **extra,
        },
    }


def count(domain, value, ids, scope=None):
    return AnswerClaim(
        kind="count",
        domain=domain,
        value=value,
        evidence_ids=ids,
        scope=scope or {**SCOPE, **({"status": "ongoing"} if domain == "todo" else {})},
    )


def test_two_events_and_zero_todos_merge_without_discarding_either_result():
    state = initial_state("最近有什么日程/待办")
    state["observations"] = [
        read("list_events", [{"id": "a"}, {"id": "b"}]),
        read("list_todos", []),
    ]
    decision = Decision(
        action="final_answer",
        answer_kind="business",
        answer="模型额外编造的数量999不应发布",
        claims=[count("event", 2, ["read-1"]), count("todo", 0, ["read-2"])],
    )
    result = guard_decision(state, decision)
    assert result.action == "final_answer"
    assert "日程2项" in result.answer and "进行中待办0项" in result.answer
    assert "999" not in result.answer


def test_failed_or_partial_query_does_not_hide_other_verified_conclusion():
    state = initial_state("日程和待办")
    state["observations"] = [
        read("list_events", [{"id": "a"}]),
        read("list_todos", [], complete=False, error="timeout"),
    ]
    decision = Decision(
        action="final_answer",
        answer_kind="business",
        claims=[count("event", 1, ["read-1"]), count("todo", 0, ["read-2"])],
    )
    assert guard_decision(state, decision).action == "revise_answer"
    state["claim_retries"] = 1
    result = guard_decision(state, decision)
    assert "日程1项" in result.answer and "其余结论暂未核实" in result.answer
    assert "待办0项" not in result.answer


def test_duplicate_same_scope_reads_are_not_added_and_conflicts_fail():
    state = initial_state("待办数量")
    state["observations"] = [
        read("list_todos", [{"id": "a"}]),
        read("list_todos", [{"id": "a"}]),
    ]
    claim = count("todo", 1, ["read-1", "read-2"])
    assert not verify(state, [claim])[1]
    claim.value = 2
    assert verify(state, [claim])[1]
    state["observations"][1]["result"]["items"] = [{"id": "b"}]
    claim.value = 1
    assert verify(state, [claim])[1]


def test_adjacent_ranges_union_by_object_id_and_gaps_cannot_prove_total():
    state = initial_state("本月日程")
    state["observations"] = [
        read(
            "list_events",
            [{"id": "a"}],
            {"date_from": "2026-10-15", "date_to": "2026-10-31"},
        ),
        read(
            "list_events",
            [{"id": "a"}, {"id": "b"}],
            {"date_from": "2026-11-01", "date_to": "2026-11-15"},
        ),
    ]
    claim = count("event", 2, ["read-1", "read-2"])
    assert not verify(state, [claim])[1]
    state["observations"][1]["arguments"]["query"]["date_from"] = "2026-11-02"
    assert verify(state, [claim])[1]


def test_domain_scope_values_and_evidence_ids_are_all_checked():
    state = initial_state("今天待办")
    state["observations"] = [read("list_todos", [])]
    for claim in (
        count("event", 0, ["read-1"]),
        count("todo", 0, ["history-1"]),
        count("todo", 1, ["read-1"]),
        count("todo", False, ["read-1"]),
        count("todo", 0, ["read-1"], {**SCOPE, "status": "completed"}),
        count(
            "todo",
            0,
            ["read-1"],
            {"date_from": "2026-10-16", "date_to": "2026-11-15", "status": "ongoing"},
        ),
    ):
        assert verify(state, [claim])[1]


def test_review_statistics_match_each_status_separately():
    state = initial_state("回顾计划")
    state["observations"] = [
        read(
            "review_plan",
            [],
            summary={"completed_todos": 2, "ongoing_todos": 0, "events": 1},
        )
    ]
    claims = [
        count("todo", 2, ["read-1"], {**SCOPE, "status": "completed"}),
        count("todo", 0, ["read-1"]),
        count("event", 1, ["read-1"]),
    ]
    assert not verify(state, claims)[1]
    claims[0].value = 0
    assert verify(state, claims)[1]


def test_fields_require_matching_object_path_value_and_source():
    state = initial_state("查看日程")
    state["observations"] = [
        read(
            "get_event",
            [
                {
                    "id": "e1",
                    "title": "会议",
                    "start_time": "12:00",
                    "status": "scheduled",
                }
            ],
            {},
        )
    ]
    # This fixture has an explicit query scope; detail reads normally use {}.
    claim = AnswerClaim(
        kind="field",
        domain="event",
        scope=SCOPE,
        subject_id="e1",
        path="/items/0/start_time",
        value="12:00",
        evidence_ids=["read-1"],
    )
    assert "12:00" in verify(state, [claim])[0][0]
    for field, wrong in (
        ("subject_id", "e2"),
        ("value", "13:00"),
        ("path", "/items/1/start_time"),
    ):
        assert verify(state, [claim.model_copy(update={field: wrong})])[1]


def test_quotes_must_come_from_current_authorized_passages():
    state = initial_state("资料里的说明")
    state["knowledge"] = [
        {"title": "说明", "content": "本功能需要用户确认之后才能执行。"}
    ]
    claim = AnswerClaim(
        kind="quote", value="需要用户确认之后才能执行", evidence_ids=["document-1"]
    )
    assert not verify(state, [claim])[1]
    claim.value = "无需用户确认"
    assert verify(state, [claim])[1]
    state["knowledge"] = []
    assert verify(state, [claim])[1]


def test_one_repair_can_add_a_missing_read_and_publish_both_domains():
    from collections import deque

    from backend.features.assistant.autonomous_types import AutonomousContext
    from backend.features.assistant.autonomous_workflow import run

    choices = deque(
        [
            Decision(
                action="read_api", tool_name="list_events", arguments={"query": SCOPE}
            ),
            Decision(
                action="final_answer",
                answer_kind="business",
                claims=[count("event", 1, ["read-1"]), count("todo", 0, ["read-2"])],
            ),
            Decision(
                action="read_api", tool_name="list_todos", arguments={"query": SCOPE}
            ),
            Decision(
                action="final_answer",
                answer_kind="business",
                claims=[count("event", 1, ["read-1"]), count("todo", 0, ["read-2"])],
            ),
        ]
    )
    result = run(
        "近期日程和待办",
        AutonomousContext(
            lambda state: guard_decision(state, choices.popleft()),
            lambda tool, args: {
                "items": [{"id": "e1"}] if tool == "list_events" else [],
                "total_count": 1 if tool == "list_events" else 0,
                "complete": True,
            },
        ),
    )
    assert result["claim_retries"] == 1
    assert "日程1项" in result["final_answer"] and "待办0项" in result["final_answer"]


def test_count_answer_includes_native_todo_and_event_details():
    state = initial_state("有什么待办和日程")
    state["observations"] = [
        read(
            "list_todos",
            [{"id": "t1", "title": "接孩子", "due_date": None}],
            {"status": "ongoing"},
        ),
        read(
            "list_events",
            [
                {
                    "id": "e1",
                    "title": "去乐天玛特",
                    "start_date": "2026-10-17",
                    "start_time": "16:00",
                    "end_date": "2026-10-17",
                    "end_time": "17:00",
                }
            ],
            {},
        ),
    ]
    # read() uses SCOPE for an empty query.
    decision = Decision(
        action="final_answer",
        answer_kind="business",
        requested_domains=["todo", "event"],
        claims=[
            count("todo", 1, ["read-1"], {"status": "ongoing"}),
            count("event", 1, ["read-2"]),
        ],
    )
    result = guard_decision(state, decision)
    assert result.action == "final_answer"
    assert "接孩子」：不设截止日期" in result.answer
    assert (
        "去乐天玛特" in result.answer
        and "16:00" in result.answer
        and "17:00" in result.answer
    )


def test_missing_requested_domain_requires_repair_and_never_claims_empty():
    state = initial_state("有什么待办和日程")
    state["observations"] = [read("list_todos", [{"id": "t1", "title": "接孩子"}])]
    decision = Decision(
        action="final_answer",
        answer_kind="business",
        requested_domains=["todo", "event"],
        claims=[count("todo", 1, ["read-1"])],
    )
    assert guard_decision(state, decision).action == "revise_answer"
    state["claim_retries"] = 1
    answer = guard_decision(state, decision).answer
    assert "接孩子" in answer and "其余结论暂未核实" in answer
    assert "日程0项" not in answer
