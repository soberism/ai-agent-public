from uuid import uuid4

from fastapi.testclient import TestClient
from helpers import HEADERS, create, register

from backend.api.routes import assistant
from backend.app import app
from backend.features.assistant import graph, threads


def test_open_conversation_reply_is_saved(cloud, monkeypatch):
    register(cloud)
    monkeypatch.setattr(
        assistant,
        "interpret",
        lambda *_: graph.Intent(action="respond", message="你好，有什么需要安排？"),
    )
    thread_id = cloud.post("/api/assistant/threads", json={}).json()["thread_id"]

    reply = cloud.post(
        "/api/assistant/messages",
        json={"thread_id": thread_id, "message": "你好"},
    )

    assert reply.status_code == 200
    assert reply.json()["kind"] == "message"

    restored = cloud.post("/api/assistant/threads", json={}).json()
    assert restored["thread_id"] == thread_id
    assert restored["entries"] == [
        {"role": "user", "message": "你好"},
        {
            "role": "assistant",
            "reply": {
                "kind": "message",
                "message": "你好，有什么需要安排？",
                "items": [],
                "action_token": None,
                "action_label": None,
            },
        },
    ]

    fresh = cloud.post("/api/assistant/threads", json={"fresh": True}).json()
    assert fresh["thread_id"] != thread_id
    assert fresh["entries"] == []


def test_thread_remembers_recent_results():
    class Store:
        def __init__(self):
            self.values = {}

        def set(self, key, value, ex):
            self.values[key] = value

        def get(self, key):
            return self.values.get(key)

    store = Store()
    owner_id = uuid4()
    thread_id = threads.create(store, owner_id)
    state = threads.load(store, thread_id, owner_id)
    result = threads.ThreadItem(
        id=uuid4(), title="买牛奶", status="ongoing", due_date="2026-09-15"
    )
    threads.remember(store, thread_id, state, "今天的待办", "找到1条。", [result])

    saved = threads.load(store, thread_id, owner_id)
    assert saved.last_results == [result]
    assert len(saved.messages) == 2


def test_confirmation_is_user_bound_and_single_use(cloud, monkeypatch):
    register(cloud)
    monkeypatch.setattr(
        assistant,
        "interpret",
        lambda *_: graph.Intent(
            action="create_todo",
            title="买一注大乐透",
            due_date="2026-09-15",
            due_time="20:00",
        ),
    )
    thread_id = cloud.post("/api/assistant/threads", json={}).json()["thread_id"]
    draft = cloud.post(
        "/api/assistant/messages",
        json={"thread_id": thread_id, "message": "买牛奶"},
    )
    assert draft.status_code == 200
    token = draft.json()["action_token"]

    other = TestClient(app, headers=HEADERS)
    register(other)
    assert (
        other.post(
            "/api/assistant/messages",
            json={"thread_id": thread_id, "message": "是的"},
        ).status_code
        == 410
    )
    assert (
        other.post(f"/api/assistant/actions/{token}/confirm", json={}).status_code
        == 404
    )

    result = cloud.post(f"/api/assistant/actions/{token}/confirm", json={})
    assert result.status_code == 200
    assert result.json()["items"][0]["title"] == "买一注大乐透"
    assert result.json()["items"][0]["due_time"] == "20:00"
    restored = cloud.post("/api/assistant/threads", json={}).json()
    assert restored["entries"][-1]["reply"]["kind"] == "success"
    assert restored["entries"][-1]["reply"]["message"] == "待办已创建。"
    confirmation = restored["entries"][-2]["reply"]
    assert confirmation["kind"] == "confirm"
    assert confirmation["action_token"] is None
    assert confirmation["action_label"] is None
    assert (
        cloud.post(f"/api/assistant/actions/{token}/confirm", json={}).status_code
        == 404
    )
    other.close()


def test_recent_query_result_can_be_viewed_and_completed_by_index(cloud, monkeypatch):
    register(cloud)
    create(cloud, title="第一候选")
    create(cloud, title="第二候选")

    def fake_interpret(message, _history, last_results, *_context):
        if message == "列出待办":
            return graph.Intent(action="query_todos")
        assert last_results and last_results[0]["index"] == 1
        return graph.Intent(
            action="complete_todo" if "完成" in message else "query_todos",
            reference_index=1,
        )

    monkeypatch.setattr(assistant, "interpret", fake_interpret)
    thread_id = cloud.post("/api/assistant/threads", json={}).json()["thread_id"]
    query = cloud.post(
        "/api/assistant/messages",
        json={"thread_id": thread_id, "message": "列出待办"},
    ).json()
    first = query["items"][0]

    viewed = cloud.post(
        "/api/assistant/messages",
        json={"thread_id": thread_id, "message": "查看第一条"},
    ).json()
    assert viewed["items"] == [first]

    draft = cloud.post(
        "/api/assistant/messages",
        json={"thread_id": thread_id, "message": "完成第一条"},
    ).json()
    assert draft["kind"] == "confirm" and first["title"] in draft["message"]
    completed = cloud.post(
        f"/api/assistant/actions/{draft['action_token']}/confirm", json={}
    ).json()
    assert completed["items"][0]["id"] == first["id"]
    assert completed["items"][0]["status"] == "completed"
