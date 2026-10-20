from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.api.agent_schemas import RunCreate
from backend.api.routes import agent_runs
from backend.db.agent_models import AgentAction, AgentRun
from backend.db.models import AssistantMessage, AssistantThread
from backend.features.assistant import history
from backend.features.assistant.autonomous_types import initial_state
from backend.features.assistant.model_input import build_model_input


def test_pending_plan_list_is_scoped_to_owned_thread(monkeypatch):
    from backend.api.routes import agent_runs

    thread_id, owner_id = uuid4(), uuid4()
    checked = []
    monkeypatch.setattr(
        agent_runs.history,
        "owned",
        lambda _session, thread, owner: checked.append((thread, owner)),
    )
    monkeypatch.setattr(agent_runs, "response", lambda _session, row: row)
    first, second = object(), object()
    session = Mock()
    session.scalars.return_value = [first, second]

    assert agent_runs.pending_plans(
        thread_id, SimpleNamespace(id=owner_id), session
    ) == [first, second]
    assert checked == [(thread_id, owner_id)]
    sql = str(session.scalars.call_args.args[0])
    assert "agent_runs.owner_id" in sql and "agent_runs.status" in sql


@pytest.mark.parametrize(
    "prompt",
    [
        "把 去超市 日程 名字改成去乐天玛特",
        "把日程「去超市」调整到明天十二点",
        "把它改成后天",
    ],
)
def test_multiple_pending_plans_do_not_block_or_capture_new_request(
    monkeypatch, prompt
):
    engine = create_engine("sqlite://")
    for model in (AssistantThread, AssistantMessage, AgentRun, AgentAction):
        model.__table__.create(engine)
    dispatch = Mock()
    monkeypatch.setattr(agent_runs.run_task, "delay", dispatch)
    user = SimpleNamespace(id=uuid4())
    with Session(engine) as session:
        thread, _ = history.start(session, user.id)
        pending = [
            AgentRun(
                owner_id=user.id,
                thread_id=thread.id,
                prompt=text,
                status="waiting",
                plan_version=1,
            )
            for text in ("明天接孩子放学", "创建清单：买车、买房")
        ]
        session.add_all(pending)
        session.commit()

        result = agent_runs.create(
            RunCreate(thread_id=thread.id, prompt=prompt), user, session
        )

        assert result.status == "queued"
        assert result.final_answer is None
        assert result.prompt == prompt
        assert result.parent_plan_id is None
        assert result.actions == []
        row = session.get(AgentRun, result.id)
        assert row.task_context == {"kind": "multiple_pending_plans"}
        dispatch.assert_called_once_with(str(result.id), str(user.id))
        waiting = set(
            session.scalars(select(AgentRun.id).where(AgentRun.status == "waiting"))
        )
        assert waiting == {plan.id for plan in pending}
        assert all(plan.plan_version == 1 for plan in pending)


def test_multiple_pending_context_requires_target_resolution_not_draft_revision():
    state = initial_state(
        "把去超市日程名字改成去乐天玛特",
        task_context={"kind": "multiple_pending_plans"},
    )
    messages = build_model_input(state, "reason")
    context = messages[-2]["content"]
    assert "多个尚未执行的待确认计划" in context
    assert "明确指向已有事项" in context
    assert "无法确定目标时先追问" in context
    assert "待修订计划_尚未执行" not in context
    assert messages[-1]["content"] == state["prompt"]


def test_explicit_event_edit_http_preserves_multiple_pending_plans(cloud, monkeypatch):
    from helpers import register

    from backend.db.session import engine

    user, _ = register(cloud)
    thread_id = cloud.post("/api/assistant/threads", json={}).json()["thread_id"]
    dispatch = Mock()
    monkeypatch.setattr(agent_runs.run_task, "delay", dispatch)
    with Session(engine) as session:
        pending = [
            AgentRun(
                owner_id=user["id"],
                thread_id=thread_id,
                prompt=prompt,
                status="waiting",
                plan_version=1,
            )
            for prompt in ("明天接孩子放学", "创建清单：买车、买房")
        ]
        session.add_all(pending)
        session.commit()
        pending_ids = {str(plan.id) for plan in pending}

    response = cloud.post(
        "/api/agent/runs",
        json={
            "thread_id": thread_id,
            "prompt": "把 去超市 日程 名字改成去乐天玛特",
        },
    )
    assert response.status_code == 202, response.text
    result = response.json()
    assert result["status"] == "queued"
    assert result["parent_plan_id"] is None
    assert result["actions"] == []
    dispatch.assert_called_once_with(result["id"], user["id"])
    with Session(engine) as session:
        row = session.get(AgentRun, result["id"])
        assert row.task_context == {"kind": "multiple_pending_plans"}
    plans = cloud.get(f"/api/agent/runs/pending/{thread_id}").json()
    assert {plan["id"] for plan in plans} == pending_ids
    assert all(plan["plan_version"] == 1 for plan in plans)
