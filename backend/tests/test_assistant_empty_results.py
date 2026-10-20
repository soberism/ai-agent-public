import json
from collections import deque
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from backend.api.routes import assistant_read_steps as reads
from backend.core.security import APIError
from backend.features.assistant.answer_claims import AnswerClaim
from backend.features.assistant.answer_guard import guard_decision
from backend.features.assistant.answer_suggestions import from_result
from backend.features.assistant.autonomous_types import (
    AutonomousContext,
    Decision,
    initial_state,
)
from backend.features.assistant.autonomous_workflow import run
from backend.features.assistant.claim_verification import verify


def today_scope():
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    return {"date_from": today, "date_to": today, "status": "ongoing"}


def test_native_todo_empty_page_passes_adapter_and_structured_publication(monkeypatch):
    page = {"items": [], "next_cursor": None, "server_time": "2026-10-15T00:00:00Z"}
    handler = Mock(return_value=SimpleNamespace(model_dump=lambda **_: page.copy()))
    monkeypatch.setattr(reads, "listing", handler)
    user, session = SimpleNamespace(id=uuid4()), Mock()
    choices = deque(
        [
            Decision(
                action="read_api",
                tool_name="list_todos",
                arguments={"query": {"due": "today"}},
            ),
            Decision(
                action="final_answer",
                answer_kind="business",
                claims=[
                    AnswerClaim(
                        kind="count",
                        domain="todo",
                        scope=today_scope(),
                        value=0,
                        evidence_ids=["read-1"],
                    )
                ],
            ),
        ]
    )
    result = run(
        "查看今天待办",
        AutonomousContext(
            lambda state: guard_decision(state, choices.popleft()),
            lambda name, args: reads.inspect(
                name, args, Mock(), user, session, uuid4()
            ),
        ),
    )
    assert "进行中待办0项" in result["final_answer"]
    assert result["read_count"] == 1
    query, principal, db = handler.call_args.args
    assert query.due == "today" and principal is user and db is session
    assert page.get("complete") is None


@pytest.mark.parametrize("cursor,next_cursor", [(None, "next"), ("previous", None)])
def test_partial_or_later_todo_page_cannot_prove_global_empty(
    monkeypatch, cursor, next_cursor
):
    monkeypatch.setattr(
        reads,
        "listing",
        lambda *_: SimpleNamespace(
            model_dump=lambda **_: {"items": [], "next_cursor": next_cursor}
        ),
    )
    arguments = {"query": {"due": "today", "cursor": cursor}}
    result = json.loads(
        reads.inspect("list_todos", arguments, Mock(), Mock(), Mock(), uuid4())
    )
    assert result["complete"] is False and result["total_count"] is None
    state = initial_state("今天待办")
    state["observations"] = [
        {"tool_name": "list_todos", "arguments": arguments, "result": result}
    ]
    claim = AnswerClaim(
        kind="count",
        domain="todo",
        scope=today_scope(),
        value=0,
        evidence_ids=["read-1"],
    )
    assert verify(state, [claim])[1]


def test_events_and_review_keep_native_evidence_not_display_summaries(monkeypatch):
    monkeypatch.setattr(
        reads,
        "list_events",
        lambda *_: SimpleNamespace(model_dump=lambda **_: {"items": []}),
    )
    scope = {key: value for key, value in today_scope().items() if key != "status"}
    result = json.loads(
        reads.inspect("list_events", {"query": scope}, Mock(), Mock(), Mock(), uuid4())
    )
    assert result == {"items": [], "complete": True, "total_count": 0}
    native = {
        **scope,
        "summary": {"completed_todos": 2, "ongoing_todos": 0, "events": 0},
        "details": {
            "completed": [{"id": "a"}, {"id": "b"}],
            "ongoing": [],
            "events": [],
        },
        "organize": {},
    }
    monkeypatch.setattr(reads, "review", lambda *_: native)
    result = json.loads(
        reads.inspect("review_plan", {"query": scope}, Mock(), Mock(), Mock(), uuid4())
    )
    assert result["summary"] == native["summary"] and result["total_count"] == 2
    state = initial_state("回顾")
    state["observations"] = [
        {"tool_name": "review_plan", "arguments": {"query": scope}, "result": result}
    ]
    claims = [
        AnswerClaim(
            kind="count",
            domain="todo",
            scope={**scope, "status": status},
            value=count,
            evidence_ids=["read-1"],
        )
        for status, count in (("completed", 2), ("ongoing", 0))
    ]
    assert not verify(state, claims)[1]


def test_read_failure_remains_error_instead_of_becoming_empty(monkeypatch):
    def failed(*_):
        raise APIError(503, "SERVICE_UNAVAILABLE", "查询失败")

    monkeypatch.setattr(reads, "listing", failed)
    with pytest.raises(APIError):
        reads.inspect(
            "list_todos", {"query": {"due": "today"}}, Mock(), Mock(), Mock(), uuid4()
        )


def test_native_todo_details_and_suggestions_survive_claim_validation(monkeypatch):
    target = str(uuid4())
    page = {
        "items": [
            {
                "id": target,
                "title": "买牛奶",
                "status": "ongoing",
                "due_date": "2026-10-15",
            }
        ],
        "next_cursor": None,
    }
    monkeypatch.setattr(
        reads, "listing", lambda *_: SimpleNamespace(model_dump=lambda **_: page.copy())
    )
    result = json.loads(
        reads.inspect(
            "list_todos", {"query": {"due": "today"}}, Mock(), Mock(), Mock(), uuid4()
        )
    )
    assert result["total_count"] == 1 and result["items"][0]["id"] == target
    assert from_result(uuid4(), result)
