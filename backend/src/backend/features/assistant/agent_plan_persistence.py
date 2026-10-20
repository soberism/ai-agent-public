"""Persist a validated proposal and supersede only its revised parent plan."""

from datetime import UTC, datetime

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select

from backend.api.routes.assistant_features import prepare
from backend.core.security import APIError
from backend.db.agent_models import AgentAction, AgentRun
from backend.features.assistant.agent_lifecycle import save_reply
from backend.features.assistant.answer_suggestions import verify_plan
from backend.features.assistant.autonomous_model import same_checklist_item
from backend.features.assistant.capabilities import CAPABILITIES
from backend.features.assistant.feature_replies import preview


def persist_plan(session, agent_run, user, proposals):
    context = getattr(agent_run, "task_context", None) or {}
    if context.get("kind") == "suggestion" and len(proposals) != 1:
        raise APIError(422, "SUGGESTION_MISMATCH", "快捷操作只能生成一项待确认计划")
    parent = None
    if agent_run.parent_plan_id:
        parent = session.scalar(
            select(AgentRun)
            .where(
                AgentRun.id == agent_run.parent_plan_id,
                AgentRun.owner_id == user.id,
                AgentRun.thread_id == agent_run.thread_id,
            )
            .with_for_update()
        )
        if (
            parent is None
            or parent.status != "waiting"
            or parent.plan_version != agent_run.task_context.get("plan_version")
        ):
            raise APIError(409, "PLAN_CHANGED", "原操作计划已变化，请重新提出修改")
    if parent:
        for action in session.scalars(
            select(AgentAction).where(
                AgentAction.run_id == parent.id,
                AgentAction.status == "proposed",
            )
        ):
            action.status = "cancelled"
        parent.status = "cancelled"
        parent.progress = None
        parent.updated_at = datetime.now(UTC)
        parent.final_answer = "已根据你的补充重新整理操作计划。"
        save_reply(session, parent, parent.final_answer)
    for position, proposal in enumerate(proposals):
        name = proposal["tool_name"]
        if CAPABILITIES[name][2]:
            raise APIError(422, "INVALID_ACTION", "只读能力不能加入操作计划")
        args, labels = prepare(name, proposal["arguments"], user, session)
        verify_plan(context, name, args)
        if name in {"check_item", "delete_checklist_item"} and not same_checklist_item(
            agent_run.prompt, labels["item_id"]
        ):
            raise APIError(422, "INVALID_TARGET", "清单项与请求不一致，请确认项目名称")
        description = preview(args, labels)
        if len(description) > 800:
            raise APIError(422, "INVALID_ACTION", "操作内容过多，请拆分后逐项确认")
        session.add(
            AgentAction(
                run_id=agent_run.id,
                position=position,
                tool_name=name,
                title=CAPABILITIES[name][1],
                description=description,
                arguments=jsonable_encoder(args),
            )
        )
    agent_run.plan_version = (agent_run.plan_version or 0) + 1
    agent_run.final_answer = "我已整理好操作计划，请确认要执行的项目。"
    agent_run.status = "waiting"
    agent_run.progress = None
    agent_run.updated_at = datetime.now(UTC)
    agent_run.lease_expires_at = None
    save_reply(session, agent_run, agent_run.final_answer, kind="confirm")
    session.commit()
