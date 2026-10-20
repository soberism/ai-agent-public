import re
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from fastapi.encoders import jsonable_encoder
from kombu.exceptions import OperationalError
from sqlalchemy import select

from backend.api.agent_schemas import Run, RunCreate, RunResume
from backend.api.schemas import ERROR_RESPONSES
from backend.core.security import DB, APIError, Principal, unavailable
from backend.db.agent_models import AgentAction, AgentRun
from backend.db.models import AssistantMessage
from backend.features.assistant import history
from backend.features.assistant.agent_celery import (
    resume_task,
    run_task,
)
from backend.features.assistant.agent_tasks import CANCELLING_PROGRESS, finish
from backend.features.assistant.answer_suggestions import resolve as resolve_suggestion
from backend.features.assistant.request_limits import enforce
from backend.features.assistant.turn_tasks import (
    pending_draft,
)
from backend.features.assistant.turn_tasks import (
    revision_prompt as _revision_prompt,
)

router = APIRouter(
    prefix="/api/agent/runs",
    tags=["自主AI助手"],
    responses=ERROR_RESPONSES,
    dependencies=[Depends(enforce)],
)


def revision_prompt(session, pending, prompt):
    return _revision_prompt(session, pending, prompt)


def owned(session, run_id, owner_id, lock=False):
    query = select(AgentRun).where(AgentRun.id == run_id, AgentRun.owner_id == owner_id)
    row = session.scalar(query.with_for_update() if lock else query)
    if row is None:
        raise APIError(404, "RUN_NOT_FOUND", "AI任务不存在或不可访问")
    return row


def response(session, row):
    actions = list(
        session.scalars(
            select(AgentAction)
            .where(AgentAction.run_id == row.id)
            .order_by(AgentAction.position)
        )
    )
    return Run(
        id=row.id,
        thread_id=row.thread_id,
        prompt=row.prompt,
        parent_plan_id=row.parent_plan_id,
        status=row.status,
        progress=row.progress,
        final_answer=row.final_answer,
        sources=row.sources or [],
        actions=actions,
        plan_version=row.plan_version,
        error=row.error,
        suggestions=row.suggestions or [],
    )


def deletion_choice(session, thread_id, prompt):
    if prompt not in {"可以", "好", "好的", "行", "可以的"}:
        return None
    last = session.scalar(
        select(AssistantMessage)
        .where(AssistantMessage.thread_id == thread_id)
        .order_by(AssistantMessage.created_at.desc(), AssistantMessage.id.desc())
        .limit(1)
    )
    if not last or last.role != "assistant":
        return None
    match = re.search(
        r"要不要(?:我帮你)?把「([^」]+)」或「([^」]+)」删掉一项[？?]?\s*$",
        last.content,
    )
    return f"你想删「{match[1]}」还是「{match[2]}」？" if match else None


@router.post("", response_model=Run, status_code=status.HTTP_202_ACCEPTED)
def create(body: RunCreate, user: Principal, session: DB):
    thread = history.owned(session, body.thread_id, user.id)
    prompt = body.prompt.strip()
    if (body.source_run_id is None) != (body.suggestion_id is None):
        raise APIError(422, "SUGGESTION_INCOMPLETE", "请选择完整的快捷操作")
    suggestion_context = None
    if body.source_run_id:
        source = session.scalar(
            select(AgentRun).where(
                AgentRun.id == body.source_run_id,
                AgentRun.thread_id == body.thread_id,
                AgentRun.owner_id == user.id,
            )
        )
        if source is None:
            raise APIError(404, "SUGGESTION_NOT_FOUND", "快捷操作不存在或已失效")
        suggestion_context = resolve_suggestion(
            session, user, source, body.suggestion_id, prompt
        )
    pending_candidates = list(
        session.scalars(
            select(AgentRun)
            .where(
                AgentRun.thread_id == body.thread_id,
                AgentRun.owner_id == user.id,
                AgentRun.status == "waiting",
            )
            .order_by(AgentRun.created_at.desc())
            .limit(2)
            .with_for_update()
        )
    )
    pending = pending_candidates[0] if len(pending_candidates) == 1 else None
    repeated = pending and (
        pending.prompt == prompt or pending.prompt.endswith(f"\n用户补充：{prompt}")
    )
    draft = (
        None
        if suggestion_context or repeated
        else pending_draft(session, pending, prompt)
    )
    task_context = suggestion_context or draft or {}
    if not task_context and len(pending_candidates) > 1:
        task_context = {"kind": "multiple_pending_plans"}
    choice = None
    if repeated:
        choice = "该请求已有待确认的操作计划，请在上方卡片执行或取消。"
    elif draft is None:
        choice = deletion_choice(session, thread.id, prompt)
    row = AgentRun(
        owner_id=user.id,
        thread_id=body.thread_id,
        prompt=prompt,
        parent_plan_id=pending.id if draft else None,
        task_context=task_context,
        progress="等待开始",
    )
    session.add(row)
    session.add(AssistantMessage(thread_id=thread.id, role="user", content=prompt))
    thread.updated_at = datetime.now(UTC)
    session.commit()
    if choice:
        finish(session, row, "completed", choice)
        return response(session, row)
    try:
        run_task.delay(str(row.id), str(user.id))
    except OperationalError:
        finish(session, row, "failed", error="任务队列暂不可用")
        raise unavailable("任务队列暂不可用") from None
    return response(session, row)


@router.get(
    "/active/{thread_id}",
    response_model=Run,
    responses={204: {"description": "没有活跃任务"}},
)
def active(thread_id: UUID, user: Principal, session: DB):
    history.owned(session, thread_id, user.id)
    row = session.scalar(
        select(AgentRun)
        .where(
            AgentRun.thread_id == thread_id,
            AgentRun.owner_id == user.id,
            AgentRun.status.in_(["queued", "running", "waiting"]),
        )
        .order_by(AgentRun.created_at.desc())
        .limit(1)
    )
    return response(session, row) if row else Response(status_code=204)


@router.get("/pending/{thread_id}", response_model=list[Run])
def pending_plans(thread_id: UUID, user: Principal, session: DB):
    history.owned(session, thread_id, user.id)
    rows = session.scalars(
        select(AgentRun)
        .where(
            AgentRun.thread_id == thread_id,
            AgentRun.owner_id == user.id,
            AgentRun.status == "waiting",
        )
        .order_by(AgentRun.created_at.desc())
        .limit(20)
    )
    return [response(session, row) for row in rows]


@router.get("/{run_id}", response_model=Run)
def get(run_id: UUID, user: Principal, session: DB):
    return response(session, owned(session, run_id, user.id))


@router.post(
    "/{run_id}/resume", response_model=Run, status_code=status.HTTP_202_ACCEPTED
)
def resume(run_id: UUID, body: RunResume, user: Principal, session: DB):
    row = owned(session, run_id, user.id, lock=True)
    if row.status != "waiting" or row.plan_version != body.plan_version:
        raise APIError(409, "PLAN_CHANGED", "操作计划已变化，请刷新后重新确认")
    actions = list(
        session.scalars(select(AgentAction).where(AgentAction.run_id == row.id))
    )
    selected = set(body.selected_action_ids)
    if not selected <= {action.id for action in actions}:
        raise APIError(422, "INVALID_ACTION", "选择了不属于当前计划的操作")
    edits = {edit.id: edit.arguments for edit in body.edits}
    if not edits.keys() <= selected:
        raise APIError(422, "INVALID_ACTION", "只能修改已选择的操作")
    from backend.api.routes.assistant_features import prepare

    for action in actions:
        if action.id in selected:
            if action.id in edits:
                arguments, _ = prepare(
                    action.tool_name, edits[action.id], user, session
                )
                action.arguments = jsonable_encoder(arguments)
            action.status = "approved"
        else:
            action.status = "cancelled"
    if not selected:
        finish(session, row, "completed", "已取消本次操作计划。")
        return response(session, row)
    row.status = "queued"
    row.progress = "等待执行"
    row.final_answer = None
    row.updated_at = datetime.now(UTC)
    session.commit()
    try:
        resume_task.delay(str(row.id), str(user.id))
    except OperationalError:
        finish(session, row, "failed", error="任务队列暂不可用")
        raise unavailable("任务队列暂不可用") from None
    return response(session, row)


@router.post("/{run_id}/cancel", response_model=Run)
def cancel(run_id: UUID, user: Principal, session: DB):
    row = owned(session, run_id, user.id, lock=True)
    if row.status in {"completed", "failed", "cancelled"}:
        return response(session, row)
    executing = session.scalar(
        select(AgentAction.id).where(
            AgentAction.run_id == row.id, AgentAction.status == "executing"
        )
    )
    for action in session.scalars(
        select(AgentAction).where(
            AgentAction.run_id == row.id,
            AgentAction.status.in_(["proposed", "approved"]),
        )
    ):
        action.status = "cancelled"
    if executing:
        row.progress = CANCELLING_PROGRESS
        row.updated_at = datetime.now(UTC)
        session.commit()
        return response(session, row)
    finish(session, row, "cancelled", "已取消本次任务。")
    return response(session, row)


@router.post("/knowledge/reindex", status_code=status.HTTP_202_ACCEPTED)
def reindex(user: Principal):
    try:
        from backend.features.assistant.index_queue import enqueue

        enqueue(user.id)
    except OperationalError:
        raise unavailable("任务队列暂不可用") from None
    return {"status": "queued"}
