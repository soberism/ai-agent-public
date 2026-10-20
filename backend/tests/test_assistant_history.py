from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

from helpers import register
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.api.routes import assistant
from backend.api.routes.assistant_threads import start_thread
from backend.api.schemas import AssistantThreadStart
from backend.core import security as auth
from backend.db.agent_models import AgentRun
from backend.db.models import AssistantMessage, AssistantThread
from backend.db.session import engine
from backend.features.assistant import graph, history, threads


def reply():
    return graph.Intent(action="respond", message="收到。")


def test_thread_response_exposes_fixed_expiry():
    local_engine = create_engine("sqlite://")
    AssistantThread.__table__.create(local_engine)
    AssistantMessage.__table__.create(local_engine)
    AgentRun.__table__.create(local_engine)
    owner = uuid4()
    store = SimpleNamespace(set=lambda *_args, **_kwargs: None)
    with Session(local_engine) as session:
        result = start_thread(
            AssistantThreadStart(), SimpleNamespace(id=owner), session, store
        )
        thread = session.get(AssistantThread, result.thread_id)
        assert result.expires_at == thread.created_at.replace(tzinfo=UTC) + timedelta(
            hours=24
        )


def test_local_history_retention_expiry_and_new_thread():
    local_engine = create_engine("sqlite://")
    AssistantThread.__table__.create(local_engine)
    AssistantMessage.__table__.create(local_engine)
    AgentRun.__table__.create(local_engine)
    owner = uuid4()
    with Session(local_engine) as session:
        thread, _ = history.start(session, owner, fresh=True)
        for index in range(101):
            history.append_pair(
                session,
                thread,
                f"问题{index}",
                SimpleNamespace(
                    kind="message", message=f"回答{index}", items=[], action_label=None
                ),
            )
        saved = history.messages(session, thread.id)
        assert len(saved) == 200
        assert saved[0].content == "问题1"
        assert saved[-1].content == "回答100"
        old_id = thread.id
        next_thread, _ = history.start(session, owner, fresh=True)
        assert next_thread.id != old_id
        assert session.get(AssistantThread, old_id) is None
        next_id = next_thread.id
        next_thread.created_at = datetime.now(UTC) - timedelta(hours=25)
        session.commit()
        history.purge(session)
        assert session.get(AssistantThread, next_id) is None


def test_thread_expires_after_24_hours(cloud, monkeypatch):
    user, _ = register(cloud)
    thread_id = cloud.post("/api/assistant/threads", json={}).json()["thread_id"]
    with Session(engine) as session:
        thread = session.get(AssistantThread, thread_id)
        thread.created_at = datetime.now(UTC) - timedelta(hours=23)
        session.commit()
    assert (
        cloud.post("/api/assistant/threads", json={}).json()["thread_id"] == thread_id
    )

    with Session(engine) as session:
        thread = session.get(AssistantThread, thread_id)
        thread.created_at = datetime.now(UTC) - timedelta(hours=25)
        session.commit()

    monkeypatch.setattr(assistant, "interpret", lambda *_: reply())
    expired = cloud.post(
        "/api/assistant/messages",
        json={"thread_id": thread_id, "message": "还在吗"},
    )
    assert expired.status_code == 410
    assert expired.json()["error"]["code"] == "THREAD_EXPIRED"
    assert (
        cloud.post("/api/assistant/threads", json={}).json()["thread_id"] != thread_id
    )
    assert user["id"]


def test_model_receives_full_retained_history(cloud, monkeypatch):
    register(cloud)
    seen = []

    def interpret(_message, messages, _results, *_context):
        seen.append(messages)
        return reply()

    monkeypatch.setattr(assistant, "interpret", interpret)
    thread_id = cloud.post("/api/assistant/threads", json={"fresh": True}).json()[
        "thread_id"
    ]
    for index in range(12):
        response = cloud.post(
            "/api/assistant/messages",
            json={"thread_id": thread_id, "message": f"消息{index}"},
        )
        assert response.status_code == 200

    assert len(seen[-1]) == 22
    assert seen[-1][0]["content"] == "消息0"
    assert seen[-1][-1]["content"] == "收到。"


def test_new_thread_deletes_previous_thread_and_cache(cloud):
    register(cloud)
    first = cloud.post("/api/assistant/threads", json={"fresh": True}).json()[
        "thread_id"
    ]
    second = cloud.post("/api/assistant/threads", json={"fresh": True}).json()[
        "thread_id"
    ]
    assert first != second
    with Session(engine) as session:
        assert session.get(AssistantThread, first) is None
    assert not auth.redis.exists(threads.key(UUID(first)))


def test_expired_thread_is_rejected_before_confirmation(cloud, monkeypatch):
    register(cloud)
    monkeypatch.setattr(
        assistant,
        "interpret",
        lambda *_: graph.Intent(action="create_todo", title="不可创建"),
    )
    thread_id = cloud.post("/api/assistant/threads", json={"fresh": True}).json()[
        "thread_id"
    ]
    draft = cloud.post(
        "/api/assistant/messages",
        json={"thread_id": thread_id, "message": "创建任务"},
    ).json()
    with Session(engine) as session:
        thread = session.get(AssistantThread, thread_id)
        thread.created_at = datetime.now(UTC) - timedelta(hours=25)
        session.commit()

    result = cloud.post(
        f"/api/assistant/actions/{draft['action_token']}/confirm", json={}
    )
    assert result.status_code == 410
    todos = cloud.get("/api/todos", params={"status": "ongoing", "due": "all"})
    assert todos.status_code == 200
    assert todos.json()["items"] == []


def test_confirm_refreshes_cache_and_history_failure_keeps_success(cloud, monkeypatch):
    from backend.features.assistant import replies

    monkeypatch.setattr(replies, "personalize_for_user", lambda reply, *_: reply)
    user, _ = register(cloud)
    monkeypatch.setattr(
        assistant,
        "interpret",
        lambda *_: graph.Intent(action="create_todo", title="买牛奶"),
    )
    thread_id = cloud.post("/api/assistant/threads", json={"fresh": True}).json()[
        "thread_id"
    ]
    draft = cloud.post(
        "/api/assistant/messages",
        json={"thread_id": thread_id, "message": "创建买牛奶"},
    ).json()
    result = cloud.post(
        f"/api/assistant/actions/{draft['action_token']}/confirm", json={}
    )
    assert result.status_code == 200
    cached = threads.load(auth.redis, UUID(thread_id), UUID(user["id"]))
    assert cached.messages[-1].content == "待办已创建。"

    second = cloud.post(
        "/api/assistant/messages",
        json={"thread_id": thread_id, "message": "再创建买牛奶"},
    ).json()

    def fail(*_args):
        raise SQLAlchemyError("history unavailable")

    monkeypatch.setattr(history, "append", fail)
    result = cloud.post(
        f"/api/assistant/actions/{second['action_token']}/confirm", json={}
    )
    assert result.status_code == 200
    assert result.json()["kind"] == "success"
