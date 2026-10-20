from helpers import register
from sqlalchemy.orm import Session

from backend.api.routes import agent_runs
from backend.db.models import AssistantMessage
from backend.db.session import engine


def test_ambiguous_deletion_consent_asks_which_item(cloud, monkeypatch):
    register(cloud)
    thread_id = cloud.post("/api/assistant/threads", json={}).json()["thread_id"]
    with Session(engine) as session:
        session.add(
            AssistantMessage(
                thread_id=thread_id,
                role="assistant",
                content="要不要我帮你把「钱」或「一次性袜子」删掉一项？",
                kind="message",
            )
        )
        session.commit()

    def unexpected_queue(*_args):
        raise AssertionError("含糊同意不应进入任务队列")

    monkeypatch.setattr(agent_runs.run_task, "delay", unexpected_queue)
    reply = cloud.post(
        "/api/agent/runs", json={"thread_id": thread_id, "prompt": "可以"}
    )
    assert reply.status_code == 202, reply.text
    assert reply.json()["status"] == "completed"
    assert reply.json()["final_answer"] == "你想删「钱」还是「一次性袜子」？"
    assert reply.json()["actions"] == []
