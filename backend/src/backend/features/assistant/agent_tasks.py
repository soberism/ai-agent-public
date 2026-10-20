"""Celery entry points for autonomous runs and approved plans."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from backend.api.routes.assistant_features import invoke
from backend.core.langsmith_tracing import observed
from backend.core.security import APIError, redis, settings
from backend.db.agent_models import AgentAction, AgentRun
from backend.db.models import User
from backend.db.session import engine
from backend.features.assistant import history
from backend.features.assistant.access import current_context, observation_references
from backend.features.assistant.agent_lifecycle import (
    CANCELLING_PROGRESS,
    finish,
    touch,
)
from backend.features.assistant.agent_plan_persistence import persist_plan
from backend.features.assistant.agent_plan_results import (
    fail_stale_actions,
    result_items,
    summarize,
)
from backend.features.assistant.agent_resume import context_for, resume_graph
from backend.features.assistant.answer_suggestions import (
    from_actions,
    from_observations,
)
from backend.features.assistant.autonomous_workflow import run as run_graph
from backend.features.assistant.checkpoints import RunSaver as PostgresSaver
from backend.features.assistant.preferences import model_context
from backend.features.assistant.summary_jobs import (
    prepare as conversation_context,
)
from backend.features.assistant.threads import load as load_thread

LEASE = timedelta(minutes=30)


def claim(session, run_id, owner_id):
    now = datetime.now(UTC)
    claimed = session.scalar(
        update(AgentRun)
        .where(
            AgentRun.id == run_id,
            AgentRun.owner_id == owner_id,
            or_(
                AgentRun.status == "queued",
                and_(
                    AgentRun.status == "running",
                    AgentRun.lease_expires_at < now,
                ),
            ),
        )
        .values(status="running", lease_expires_at=now + LEASE, updated_at=now)
        .returning(AgentRun.id)
    )
    session.commit()
    if claimed is None:
        return None, None
    run = session.get(AgentRun, claimed)
    user = session.get(User, owner_id)
    if run is None or user is None or not user.active:
        return None, None
    return run, user


@observed
def execute_run(run_id: str, owner_id: str):
    with Session(engine) as session:
        agent_run, user = claim(session, run_id, owner_id)
        if agent_run is None:
            row = session.get(AgentRun, run_id)
            return bool(row and row.status == "running")
        touch(agent_run, status="running", progress="正在分析问题")
        session.commit()
        saved = history.messages(session, agent_run.thread_id)
        history.cache(redis, user.id, agent_run.thread_id, saved)
        safe_history, last_results = current_context(
            session,
            user,
            load_thread(redis, agent_run.thread_id, user.id),
            agent_run.thread_id,
        )
        if safe_history and safe_history[-1] == {
            "role": "user",
            "content": agent_run.prompt,
        }:
            safe_history.pop()
        custom_instructions, memories = model_context(session, user.id)
        context = context_for(session, agent_run, user)
        try:
            history.owned(session, agent_run.thread_id, user.id)
            recent_history, conversation_summary = conversation_context(
                redis, user.id, agent_run.thread_id, safe_history
            )
            with PostgresSaver.from_conn_string(settings.checkpoint_url) as saver:
                saver.run_id = str(agent_run.id)
                result = run_graph(
                    agent_run.prompt,
                    context,
                    recent_history,
                    saver,
                    {"configurable": {"thread_id": str(agent_run.id)}},
                    context_data={
                        "conversation_summary": conversation_summary,
                        "history_prepared": True,
                        "timezone": user.timezone,
                        "custom_instructions": custom_instructions,
                        "memories": memories,
                        "last_results": last_results,
                        "task_context": agent_run.task_context or {},
                    },
                )
            session.refresh(agent_run)
            if agent_run.status == "cancelled":
                return
            agent_run.sources = [
                {
                    "title": item["title"],
                    "url": item["url"],
                    "excerpt": str(item.get("content") or item.get("snippet") or "")[
                        :240
                    ],
                    "chunk_id": item.get("chunk_id"),
                    "document_version": item.get("document_version"),
                    "locator": item.get("locator"),
                }
                for item in [*result["knowledge"], *result["web_results"]]
            ]
            interruptions = result.get("__interrupt__", ())
            if interruptions:
                persist_plan(
                    session, agent_run, user, interruptions[0].value["actions"]
                )
            else:
                finish(
                    session,
                    agent_run,
                    "completed",
                    result["final_answer"],
                    kind="result"
                    if result["observations"] or result["knowledge"]
                    else "message",
                    suggestions=from_observations(agent_run.id, result["observations"]),
                    context_refs=observation_references(result["observations"]),
                )
        except APIError as error:
            session.rollback()
            agent_run = session.get(AgentRun, run_id)
            if agent_run:
                finish(session, agent_run, "failed", error=error.message)
        except Exception:  # noqa: BLE001 -- task boundary must persist a safe failure.
            session.rollback()
            agent_run = session.get(AgentRun, run_id)
            if agent_run:
                finish(session, agent_run, "failed", error="AI任务执行失败，请稍后重试")
        from backend.features.assistant.summary_jobs import schedule

        if agent_run is not None:
            schedule(owner_id, str(agent_run.thread_id))
    return False


@observed
def execute_plan(run_id: str, owner_id: str):
    with Session(engine) as session:
        agent_run, user = claim(session, run_id, owner_id)
        if agent_run is None:
            row = session.get(AgentRun, run_id)
            return bool(row and row.status == "running")
        if not agent_run.graph_resumed:
            try:
                resume_graph(agent_run, context_for(session, agent_run, user))
                agent_run.graph_resumed = True
                agent_run.progress = "图已恢复，等待执行已确认操作"
                session.commit()
            except Exception:  # noqa: BLE001 -- checkpoint resume is a task boundary.
                session.rollback()
                agent_run = session.get(AgentRun, run_id)
                finish(
                    session,
                    agent_run,
                    "failed",
                    error="操作计划恢复失败，请重新发起",
                )
                return
        fail_stale_actions(session, agent_run.id)
        actions = list(
            session.scalars(
                select(AgentAction)
                .where(
                    AgentAction.run_id == agent_run.id, AgentAction.status == "approved"
                )
                .order_by(AgentAction.position)
            )
        )
        if agent_run.progress != CANCELLING_PROGRESS:
            touch(agent_run, status="running", progress="正在执行已确认操作")
        session.commit()
        for action in actions:
            session.refresh(agent_run, with_for_update=True)
            session.refresh(action)
            if (
                agent_run.status == "cancelled"
                or agent_run.progress == CANCELLING_PROGRESS
            ):
                session.rollback()
                break
            if action.status != "approved":
                session.rollback()
                continue
            action.status = "executing"
            session.commit()  # The cancel route observes this before reporting cancellation.
            try:
                reply = invoke(
                    action.tool_name,
                    action.arguments,
                    user,
                    session,
                    idempotency_token=action.id,
                )
                action.result = reply.model_dump(mode="json")
                action.status = "completed"
            except APIError as error:
                session.rollback()
                action = session.get(AgentAction, action.id)
                action.status, action.error = "failed", error.message
            except Exception:  # noqa: BLE001 -- never retry an uncertain business write.
                session.rollback()
                action = session.get(AgentAction, action.id)
                action.status = "failed"
                action.error = "执行结果待核对，请勿重复提交"
            session.commit()
        agent_run = session.get(AgentRun, agent_run.id)
        answer = summarize(
            [action for action in actions if action.status != "cancelled"]
        )
        if agent_run.progress == CANCELLING_PROGRESS:
            finish(
                session,
                agent_run,
                "completed",
                answer,
                kind="result",
                suggestions=from_actions(agent_run.id, actions),
                items=result_items(actions),
            )
        elif agent_run.status == "cancelled":
            return False
        else:
            finish(
                session,
                agent_run,
                "completed",
                answer,
                kind="result",
                suggestions=from_actions(agent_run.id, actions),
                items=result_items(actions),
            )
        from backend.features.assistant.summary_jobs import schedule

        if agent_run is not None:
            schedule(owner_id, str(agent_run.thread_id))
    return False
