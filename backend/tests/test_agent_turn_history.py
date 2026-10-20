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
from backend.features.assistant import agent_plan_persistence, history
from backend.features.assistant.agent_lifecycle import finish, save_reply
from backend.features.assistant.autonomous_types import initial_state
from backend.features.assistant.model_input import build_model_input


def test_waiting_plan_is_a_reply_and_completion_updates_that_turn(monkeypatch):
    engine = create_engine("sqlite://")
    for model in (AssistantThread, AssistantMessage, AgentRun, AgentAction):
        model.__table__.create(engine)
    monkeypatch.setattr(
        agent_plan_persistence,
        "prepare",
        lambda *_: ({"body": {"title": "接孩子"}}, {}),
    )
    user = SimpleNamespace(id=uuid4())
    with Session(engine) as session:
        thread, _ = history.start(session, user.id)
        row = AgentRun(owner_id=user.id, thread_id=thread.id, prompt="明天去接孩子")
        session.add(row)
        history.append(session, thread, "user", row.prompt)
        agent_plan_persistence.persist_plan(
            session, row, user, [{"tool_name": "create_todo", "arguments": {}}]
        )
        saved = history.messages(session, thread.id)
        assert [item.role for item in saved] == ["user", "assistant"]
        assert saved[-1].kind == "confirm"
        assert saved[-1].id == row.id
        assert "确认" in saved[-1].content
        assert row.history_saved is False
        assert history.output(saved)[-1]["id"] == str(row.id)

        history.append(session, thread, "user", "你好")
        finish(session, row, "cancelled", "已取消本次任务。")
        finish(session, row, "cancelled", "已取消本次任务。")
        saved = history.messages(session, thread.id)
        assert len(saved) == 3
        assert saved[1].content == "已取消本次任务。"
        assert saved[1].kind == "message"
        assert saved[-1].content == "你好"


def test_current_greeting_is_the_last_model_message_after_historical_request():
    state = initial_state(
        "你好",
        history=[{"role": "user", "content": "明天上午去接孩子"}],
    )
    inputs = build_model_input(state, "reason")
    assert inputs[-1] == {"role": "user", "content": "你好"}
    assert inputs[0]["content"] == "明天上午去接孩子"


@pytest.mark.parametrize("revised", [False, True])
def test_repeated_pending_request_saves_a_reply_for_each_turn(monkeypatch, revised):
    engine = create_engine("sqlite://")
    for model in (AssistantThread, AssistantMessage, AgentRun, AgentAction):
        model.__table__.create(engine)
    dispatch = Mock()
    monkeypatch.setattr(agent_runs.run_task, "delay", dispatch)
    user = SimpleNamespace(id=uuid4())
    prompt = "创建待办：下周天下午去郊游"
    with Session(engine) as session:
        thread, _ = history.start(session, user.id)
        pending = AgentRun(
            owner_id=user.id,
            thread_id=thread.id,
            prompt=f"用户正在修订旧计划。\n用户补充：{prompt}" if revised else prompt,
            status="waiting",
            plan_version=1,
        )
        session.add(pending)
        history.append(session, thread, "user", prompt)
        save_reply(session, pending, "请确认要执行的操作", kind="confirm")
        history.append(session, thread, "user", "你好")
        history.append(session, thread, "assistant", "你好，有什么需要帮忙的？")
        session.commit()

        replies = []
        for _ in range(3):
            result = agent_runs.create(
                RunCreate(thread_id=thread.id, prompt=prompt), user, session
            )
            assert result.id != pending.id
            assert result.status == "completed"
            assert result.actions == []
            assert "待确认" in result.final_answer
            replies.append(result.id)

        assert len(set(replies)) == 3
        session.expire_all()
        saved = history.messages(session, thread.id)
        assert [item.role for item in saved] == ["user", "assistant"] * 5
        assert [item.id for item in saved[5::2]] == replies
        assert [item.content for item in saved[4::2]] == [prompt] * 3
        waiting = list(
            session.scalars(select(AgentRun).where(AgentRun.status == "waiting"))
        )
        assert [item.id for item in waiting] == [pending.id]
        assert pending.plan_version == 1
        assert pending.parent_plan_id is None
        dispatch.assert_not_called()


def test_repeated_request_http_history_round_trip(cloud, monkeypatch):
    from helpers import register

    from backend.db.session import engine as cloud_engine

    user, _ = register(cloud)
    thread_id = cloud.post("/api/assistant/threads", json={}).json()["thread_id"]
    prompt = "创建待办：下周天下午去郊游"
    dispatch = Mock()
    monkeypatch.setattr(agent_runs.run_task, "delay", dispatch)
    with Session(cloud_engine) as session:
        thread = session.get(AssistantThread, thread_id)
        pending = AgentRun(
            owner_id=user["id"],
            thread_id=thread_id,
            prompt=prompt,
            status="waiting",
            plan_version=1,
        )
        session.add(pending)
        history.append(session, thread, "user", prompt)
        save_reply(session, pending, "请确认要执行的操作", kind="confirm")
        session.commit()
        pending_id = str(pending.id)

    replies = []
    for _ in range(2):
        result = cloud.post(
            "/api/agent/runs", json={"thread_id": thread_id, "prompt": prompt}
        )
        assert result.status_code == 202, result.text
        assert result.json()["status"] == "completed"
        assert result.json()["actions"] == []
        replies.append(result.json()["id"])
    assert len(set(replies + [pending_id])) == 3
    reloaded = cloud.post("/api/assistant/threads", json={}).json()["entries"]
    assert [entry["role"] for entry in reloaded] == ["user", "assistant"] * 3
    assert [entry["id"] for entry in reloaded[3::2]] == replies
    plans = cloud.get(f"/api/agent/runs/pending/{thread_id}").json()
    assert [plan["id"] for plan in plans] == [pending_id]
    dispatch.assert_not_called()
