"""Redis原子任务去重与陈旧任务隔离，仅访问测试命名空间。"""

import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from test_conversation_context import exchanges

from backend.core.security import redis
from backend.features.assistant import conversation_context as memory
from backend.features.assistant import summary_jobs as jobs
from backend.features.assistant import summary_worker as worker
from backend.features.assistant.agent_celery import summary_task


def test_concurrent_requests_publish_once_and_stale_task_cannot_clear_new_lock(
    cloud, monkeypatch
):
    owner, thread, messages = uuid4(), uuid4(), exchanges(8)
    dispatched = []
    monkeypatch.setattr(summary_task, "apply_async", lambda **kw: dispatched.append(kw))
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert all(
            pool.map(lambda _: jobs.request(redis, owner, thread, messages), range(16))
        )
    assert len(dispatched) == 1 and dispatched[0]["queue"] == jobs.QUEUE
    old_job = redis.get(jobs.keys(thread)[1])
    redis.set(jobs.keys(thread)[1], "new-lock", ex=120)
    assert not jobs.finish(redis, thread, old_job, value="bad", failed=True)
    assert redis.get(jobs.keys(thread)[1]) == "new-lock"
    assert redis.get(jobs.keys(thread)[0]) is None
    assert redis.get(jobs.keys(thread)[2]) is None


@pytest.mark.parametrize("change", ["none", "permission", "new-token", "failure"])
def test_worker_rechecks_revision_before_publishing_and_cools_down(
    cloud, monkeypatch, change
):
    owner, thread, messages = uuid4(), uuid4(), exchanges(8)
    monkeypatch.setattr(summary_task, "apply_async", lambda **_: None)
    assert jobs.request(redis, owner, thread, messages)
    raw = redis.get(jobs.keys(thread)[1])
    reads = []

    def authorized(*_):
        reads.append(True)
        result = [dict(m) for m in messages]
        if change == "permission" and len(reads) > 1:
            result[1]["content"] = "此前内容已不可访问"
        return result

    def summarize(*_):
        if change == "new-token":
            redis.set(jobs.keys(thread)[1], "replacement", ex=120)
        if change == "failure":
            from backend.core.security import APIError

            raise APIError(503, "UNAVAILABLE", "摘要未完成")
        return "授权摘要"

    monkeypatch.setattr(worker, "authorized_messages", authorized)
    monkeypatch.setattr(memory, "summarize", summarize)
    worker.generate(str(owner), str(thread), json.loads(raw)["token"])
    if change == "none":
        assert jobs.cached(redis, owner, thread, messages).summary == "授权摘要"
        assert redis.get(jobs.keys(thread)[1]) is None
    else:
        assert redis.get(jobs.keys(thread)[0]) is None
    if change in {"permission", "failure"}:
        assert redis.get(jobs.keys(thread)[2])
        assert not jobs.request(redis, owner, thread, messages)
    if change == "new-token":
        assert redis.get(jobs.keys(thread)[1]) == "replacement"


def test_publish_failure_is_not_a_failed_answer(cloud, monkeypatch):
    def unavailable(**_):
        raise ConnectionError("isolated broker failure")

    monkeypatch.setattr(summary_task, "apply_async", unavailable)
    owner, thread = uuid4(), uuid4()
    assert not jobs.request(redis, owner, thread, exchanges(8))
    assert redis.get(jobs.keys(thread)[1]) is None
    assert redis.get(jobs.keys(thread)[2])


def test_real_thread_owner_is_checked_before_model_call(cloud, monkeypatch):
    from helpers import register
    from sqlalchemy.orm import Session

    from backend.db.session import engine

    account, _ = register(cloud)
    thread = cloud.post("/api/assistant/threads", json={"fresh": True}).json()[
        "thread_id"
    ]
    monkeypatch.setattr(
        memory, "summarize", lambda *_: pytest.fail("越权线程不能调用摘要模型")
    )
    with Session(engine) as session:
        assert worker.authorized_messages(session, account["id"], thread) == []
        with pytest.raises(Exception) as denied:
            worker.authorized_messages(session, uuid4(), thread)
        assert "账号不可用" in str(denied.value)
    other, _ = register(cloud)
    with Session(engine) as session:
        from backend.core.security import APIError

        with pytest.raises(APIError) as denied:
            worker.authorized_messages(session, other["id"], thread)
        assert denied.value.status == 410
        assert denied.value.code == "THREAD_EXPIRED"
