import os

import pytest
from helpers import register

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_MODEL") != "1",
    reason="显式 RUN_LIVE_MODEL=1 才调用真实模型",
)


def test_real_model_query_create_complete_with_database(cloud):
    register(cloud)
    thread_id = cloud.post("/api/assistant/threads", json={"fresh": True}).json()[
        "thread_id"
    ]

    queried = cloud.post(
        "/api/assistant/messages",
        json={"thread_id": thread_id, "message": "我现在有待办吗？"},
    )
    assert queried.status_code == 200, queried.text
    assert queried.json()["kind"] == "result"

    drafted = cloud.post(
        "/api/assistant/messages",
        json={"thread_id": thread_id, "message": "创建待办：PRD03真实联调任务"},
    )
    assert drafted.status_code == 200, drafted.text
    assert drafted.json()["kind"] == "confirm"
    created = cloud.post(
        f"/api/assistant/actions/{drafted.json()['action_token']}/confirm", json={}
    )
    assert created.status_code == 200, created.text
    assert created.json()["items"][0]["title"] == "PRD03真实联调任务"

    completion = cloud.post(
        "/api/assistant/messages",
        json={"thread_id": thread_id, "message": "完成PRD03真实联调任务"},
    )
    assert completion.status_code == 200, completion.text
    assert completion.json()["kind"] == "confirm"
    completed = cloud.post(
        f"/api/assistant/actions/{completion.json()['action_token']}/confirm", json={}
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["items"][0]["status"] == "completed"
