"""删除与过期清理同时移除对应检查点，并保留其他会话。"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from backend.db.agent_models import AgentRun
from backend.db.models import AssistantMessage, AssistantThread, User
from backend.features.assistant import history
from backend.features.assistant.threads import key


@pytest.mark.parametrize("fresh", [True, False])
def test_cleanup_removes_only_selected_history_and_all_checkpoint_tables(fresh):
    engine = create_engine("sqlite://")
    for model in (User, AssistantThread, AssistantMessage, AgentRun):
        model.__table__.create(engine)
    tables = ("checkpoints", "checkpoint_blobs", "checkpoint_writes")
    with engine.begin() as connection:
        for table in tables:
            connection.execute(
                text(f"CREATE TABLE {table} (thread_id TEXT, blob TEXT)")
            )

    class Store:
        def __init__(self):
            self.deleted = []

        def delete(self, *keys):
            self.deleted.extend(keys)

    store = Store()
    with Session(engine) as db:
        owners = [
            User(email=f"{uuid4()}@example.test", password_hash="synthetic")
            for _ in range(2)
        ]
        db.add_all(owners)
        db.flush()
        threads = [AssistantThread(owner_id=o.id) for o in owners]
        if not fresh:
            threads[0].created_at = datetime.now(UTC) - timedelta(hours=25)
        db.add_all(threads)
        db.flush()
        runs = [
            AgentRun(owner_id=o.id, thread_id=t.id, prompt="测试", status="completed")
            for o, t in zip(owners, threads)
        ]
        db.add_all(runs)
        db.flush()
        for run in runs:
            for table in tables:
                db.execute(
                    text(f"INSERT INTO {table} VALUES (:id,'synthetic')"),
                    {"id": str(run.id)},
                )
        db.commit()
        deleted_id, kept_id = threads[0].id, threads[1].id
        if fresh:
            history.start(db, owners[0].id, fresh=True, store=store)
        else:
            history.purge(db, store)
        for table in tables:
            assert db.execute(
                text(f"SELECT thread_id FROM {table}")
            ).scalars().all() == [str(runs[1].id)]
        assert db.get(AssistantThread, deleted_id) is None
        assert db.get(AssistantThread, kept_id) is not None
        assert set(store.deleted) == {
            key(deleted_id) + s
            for s in ("", ":context", ":context:pending", ":context:cooldown")
        }


def test_cloud_cleanup_removes_real_checkpoint_rows_and_summary_cache(cloud):
    from uuid import UUID

    from helpers import register

    from backend.core.security import redis
    from backend.db.session import engine as cloud_engine

    account, _ = register(cloud)
    owner = UUID(account["id"])
    thread_id = UUID(
        cloud.post("/api/assistant/threads", json={"fresh": True}).json()["thread_id"]
    )
    with Session(cloud_engine) as db:
        run = AgentRun(
            owner_id=owner, thread_id=thread_id, prompt="synthetic", status="completed"
        )
        db.add(run)
        db.flush()
        run_id = str(run.id)
        db.execute(
            text(
                "INSERT INTO checkpoints (thread_id,checkpoint_id,checkpoint) VALUES (:id,'1','{}')"
            ),
            {"id": run_id},
        )
        db.execute(
            text(
                "INSERT INTO checkpoint_blobs (thread_id,channel,version,type,blob) VALUES (:id,'audit','1','bytes',:blob)"
            ),
            {"id": run_id, "blob": b"synthetic"},
        )
        db.execute(
            text(
                "INSERT INTO checkpoint_writes (thread_id,checkpoint_id,task_id,idx,channel,type,blob) VALUES (:id,'1','audit',0,'audit','bytes',:blob)"
            ),
            {"id": run_id, "blob": b"synthetic"},
        )
        db.commit()
    for suffix in (":context", ":context:pending", ":context:cooldown"):
        redis.set(key(thread_id) + suffix, "synthetic", ex=60)
    assert cloud.post("/api/assistant/threads", json={"fresh": True}).status_code == 200
    with Session(cloud_engine) as db:
        for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
            assert (
                db.execute(
                    text(f"SELECT COUNT(*) FROM {table} WHERE thread_id=:id"),
                    {"id": run_id},
                ).scalar()
                == 0
            )
    assert not any(
        redis.exists(key(thread_id) + s)
        for s in ("", ":context", ":context:pending", ":context:cooldown")
    )


def test_cloud_checkpoint_writer_cannot_recreate_deleted_history(cloud):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from uuid import UUID

    from helpers import register

    from backend.core.security import APIError, redis, settings
    from backend.db.session import engine as cloud_engine
    from backend.features.assistant.checkpoints import RunSaver
    from backend.features.assistant.history_cleanup import remove_threads

    account, _ = register(cloud)
    owner = UUID(account["id"])
    thread = UUID(
        cloud.post("/api/assistant/threads", json={"fresh": True}).json()["thread_id"]
    )
    with Session(cloud_engine) as db:
        run = AgentRun(
            owner_id=owner, thread_id=thread, prompt="synthetic", status="running"
        )
        db.add(run)
        db.commit()
        run_id = str(run.id)
    started = Event()

    def remove():
        with Session(cloud_engine) as db:
            started.set()
            remove_threads(db, [thread], redis)
            db.commit()

    with RunSaver.from_conn_string(settings.checkpoint_url) as saver:
        saver.run_id = run_id
        with ThreadPoolExecutor(max_workers=1) as pool:
            with saver._cursor(pipeline=True) as cursor:
                future = pool.submit(remove)
                assert started.wait(5)
                assert not future.done()
                cursor.execute(
                    "INSERT INTO checkpoints (thread_id,checkpoint_id,checkpoint) VALUES (%s,'audit','{}')",
                    (run_id,),
                )
            future.result(timeout=10)
        with pytest.raises(APIError) as expired:
            saver.get({"configurable": {"thread_id": run_id}})
        assert expired.value.status == 410
    with Session(cloud_engine) as db:
        assert (
            db.execute(
                text("SELECT COUNT(*) FROM checkpoints WHERE thread_id=:id"),
                {"id": run_id},
            ).scalar()
            == 0
        )
