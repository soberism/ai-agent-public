"""Persist run completion and its historical context without duplicating messages."""

from datetime import UTC, datetime

from backend.db.models import AssistantMessage, AssistantThread

CANCELLING_PROGRESS = "正在完成已开始的操作，后续操作已取消"


def touch(row, *, status, progress=None, error=None):
    row.status, row.progress, row.error = status, progress, error
    row.updated_at = datetime.now(UTC)


def save_reply(session, agent_run, content, *, kind="message", **values):
    # The run ID anchors its pending and terminal replies to the same chat turn.
    message = session.get(AssistantMessage, agent_run.id)
    if message is None:
        message = AssistantMessage(
            id=agent_run.id, thread_id=agent_run.thread_id, role="assistant"
        )
        session.add(message)
    message.content, message.kind = content, kind
    for key, value in values.items():
        setattr(message, key, value)


def finish(
    session,
    agent_run,
    status,
    answer=None,
    error=None,
    kind="message",
    suggestions=None,
    context_refs=None,
    items=None,
):
    session.flush()
    session.refresh(agent_run, with_for_update=True)
    if agent_run.status == "cancelled" and status != "cancelled":
        session.rollback()
        return
    if status == "completed" and agent_run.progress == CANCELLING_PROGRESS:
        status = "cancelled"
        answer = f"{answer or '操作结果待核对。'} 后续操作已取消。"
    touch(agent_run, status=status, progress=None, error=error)
    agent_run.lease_expires_at = None
    if answer is not None:
        agent_run.final_answer = answer
    if not agent_run.history_saved:
        agent_run.suggestions = (
            suggestions if status == "completed" and suggestions else []
        )
    if not agent_run.history_saved:
        content = answer or error
        if content:
            save_reply(
                session,
                agent_run,
                content,
                kind=kind if status == "completed" else "message",
                suggestions=agent_run.suggestions,
                context_refs=context_refs,
                items=items,
            )
            thread = session.get(AssistantThread, agent_run.thread_id)
            if thread:
                thread.updated_at = datetime.now(UTC)
        agent_run.history_saved = True
    session.commit()
