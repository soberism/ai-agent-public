"""Delete only checkpoints and caches belonging to the selected conversations."""

from sqlalchemy import bindparam, delete, inspect, select, text

from backend.db.agent_models import AgentRun
from backend.db.models import AssistantMessage, AssistantThread
from backend.features.assistant.threads import key


def remove_threads(session, thread_ids, store=None):
    if not thread_ids:
        return
    run_ids = list(
        session.scalars(
            select(AgentRun.id)
            .where(AgentRun.thread_id.in_(thread_ids))
            .with_for_update()
        )
    )
    if run_ids:
        inspector = inspect(session.connection())
        for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
            if inspector.has_table(table):
                statement = text(
                    f"DELETE FROM {table} WHERE thread_id IN :run_ids"
                ).bindparams(bindparam("run_ids", expanding=True))
                session.execute(
                    statement, {"run_ids": [str(value) for value in run_ids]}
                )
    if store:
        store.delete(
            *[
                key(thread_id) + suffix
                for thread_id in thread_ids
                for suffix in ("", ":context", ":context:pending", ":context:cooldown")
            ]
        )
    session.execute(
        delete(AssistantMessage)
        .where(AssistantMessage.thread_id.in_(thread_ids))
        .execution_options(synchronize_session=False)
    )
    session.execute(
        delete(AssistantThread)
        .where(AssistantThread.id.in_(thread_ids))
        .execution_options(synchronize_session=False)
    )
