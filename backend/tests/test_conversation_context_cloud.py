"""Cloud PostgreSQL/Redis integration with synthetic accounts and isolated keys."""

import os
from uuid import uuid4

import pytest
from langgraph.checkpoint.postgres import PostgresSaver
from sqlalchemy import delete
from sqlalchemy.orm import Session

from backend.core.security import redis, settings
from backend.db.agent_models import AgentRun
from backend.db.models import AssistantMessage, AssistantThread, User
from backend.db.session import engine
from backend.features.assistant import agent_resume, agent_tasks, conversation_context
from backend.features.assistant.agent_celery import summary_task
from backend.features.assistant.autonomous_types import Decision
from backend.features.assistant.history import messages, output
from backend.features.assistant.summary_worker import generate


@pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION") != "1", reason="requires isolated cloud database"
)
def test_worker_runs_share_conversation_summary_but_not_execution_state(monkeypatch):
    assert settings.postgres_db == "ai_agent_test"
    namespace = f"test:conversation:{uuid4()}:"
    monkeypatch.setattr(settings, "redis_namespace", namespace)
    owner, thread_id, other_thread = uuid4(), uuid4(), uuid4()
    run_ids, seen, summary_calls = [], [], []

    def summarize(previous, batch):
        summary_calls.append((previous, batch))
        return "用户在讨论旅行计划，前面的回答只代表历史情况。"

    def decide(state):
        seen.append(state.copy())
        if state["prompt"] == "你好":
            return Decision(action="final_answer", answer="你好")
        if state["observations"]:
            return Decision(action="final_answer", answer="这次查询已完成。")
        if not state["discovered_tools"]:
            return Decision(action="search_tools", query="查询待办")
        return Decision(
            action="read_api",
            tool_name="list_todos",
            arguments={"query": {"due": "all"}},
        )

    monkeypatch.setattr(conversation_context, "summarize", summarize)
    # 本测试内同步消费测试任务；真实双队列调度由耗时回放验证。
    monkeypatch.setattr(summary_task, "apply_async", lambda args, **_: generate(*args))
    monkeypatch.setattr(agent_resume, "decide", decide)
    with PostgresSaver.from_conn_string(settings.checkpoint_url) as saver:
        saver.setup()
    try:
        with Session(engine) as session:
            session.add(
                User(
                    id=owner,
                    email=f"conversation-{owner}@example.test",
                    password_hash="test-placeholder",
                )
            )
            session.flush()
            session.add_all(
                [
                    AssistantThread(id=thread_id, owner_id=owner),
                    AssistantThread(id=other_thread, owner_id=owner),
                ]
            )
            session.flush()
            for i in range(8):
                session.add_all(
                    [
                        AssistantMessage(
                            thread_id=thread_id, role="user", content=f"旅行问题{i}"
                        ),
                        AssistantMessage(
                            thread_id=thread_id,
                            role="assistant",
                            content=f"旅行回答{i}",
                            kind="message",
                        ),
                    ]
                )
                session.flush()
            session.commit()
        for prompt, target in [
            ("第二条展开说说", thread_id),
            ("换一个", thread_id),
            ("你好", other_thread),
        ]:
            with Session(engine) as session:
                row = AgentRun(owner_id=owner, thread_id=target, prompt=prompt)
                session.add(row)
                session.add(
                    AssistantMessage(thread_id=target, role="user", content=prompt)
                )
                session.commit()
                run_id = row.id
                run_ids.append(run_id)
            agent_tasks.execute_run(str(run_id), str(owner))
            with Session(engine) as session:
                saved_run = session.get(AgentRun, run_id)
                assert saved_run.status == "completed", saved_run.error
                reply = messages(session, target)[-1]
                assert reply.context_refs == []
                assert output([reply])[0]["reply"]["items"] == []
        starts = [state for state in seen if state["iteration"] == 0]
        assert len(starts) == 3
        assert all(
            not state["observations"] and not state["approval"] for state in starts
        )
        assert starts[0]["conversation_summary"] == starts[1]["conversation_summary"]
        assert starts[0]["conversation_summary"]
        assert {message["role"] for message in starts[0]["history"]} == {
            "user",
            "assistant",
        }
        assert summary_calls[0][0] == ""
        assert summary_calls[1][0] == starts[0]["conversation_summary"]
        assert len(summary_calls[1][1]) == 2
        assert starts[2]["history"] == []
        assert starts[2]["conversation_summary"] == ""
    finally:
        with PostgresSaver.from_conn_string(settings.checkpoint_url) as saver:
            for run_id in run_ids:
                saver.delete_thread(str(run_id))
        keys = list(redis.scan_iter(match=namespace + "*"))
        if keys:
            redis.delete(*keys)
        with Session(engine) as session:
            session.execute(
                delete(AssistantMessage).where(
                    AssistantMessage.thread_id.in_([thread_id, other_thread])
                )
            )
            session.execute(
                delete(AssistantThread).where(
                    AssistantThread.id.in_([thread_id, other_thread])
                )
            )
            session.execute(delete(User).where(User.id == owner))
            session.commit()
