from types import SimpleNamespace

from helpers import register
from sqlalchemy.orm import Session

from backend.db.agent_models import AgentRun
from backend.db.models import AssistantMessage
from backend.db.session import engine
from backend.features.assistant.agent_plan_results import summarize
from backend.features.assistant.agent_tasks import finish


def test_completed_plan_reply_survives_thread_reload(cloud):
    user, _ = register(cloud)
    thread_id = cloud.post("/api/assistant/threads", json={}).json()["thread_id"]
    action = SimpleNamespace(
        status="completed",
        tool_name="add_checklist_item",
        title="添加清单项",
        arguments={"body": {"title": "香水"}},
        result={"items": [{"title": "旅行准备"}]},
    )
    answer = summarize([action])
    assert answer == "已在「旅行准备」清单添加「香水」。"
    with Session(engine) as session:
        run = AgentRun(owner_id=user["id"], thread_id=thread_id, prompt="新建清单")
        session.add(run)
        session.add(
            AssistantMessage(thread_id=thread_id, role="user", content="新建清单")
        )
        session.commit()
        finish(session, run, "completed", answer)

    reloaded = cloud.post("/api/assistant/threads", json={})
    assert reloaded.status_code == 200, reloaded.text
    assert reloaded.json()["thread_id"] == thread_id
    assert reloaded.json()["entries"][-1]["reply"]["message"] == answer
