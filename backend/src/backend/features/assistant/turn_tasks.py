"""Resolve a new message against a pending plan without rewriting user text."""

import json
import re

from sqlalchemy import select

from backend.db.agent_models import AgentAction

CONTINUATION = re.compile(
    r"^(?:改成|改到|改为|换成|调整|提前|推迟|延后|再加|加上|去掉|删掉|补充|不要|感觉|把它|将它|时间|日期|地点|提醒时间)"
)


def pending_draft(session, pending, prompt: str) -> dict | None:
    if pending is None:
        return None
    if re.match(r"^(?:查看|查询|创建|新建|添加|帮我创建|帮我查看)", prompt):
        return None
    actions = list(
        session.scalars(
            select(AgentAction)
            .where(AgentAction.run_id == pending.id, AgentAction.status == "proposed")
            .order_by(AgentAction.position)
        )
    )
    same_subject = any(
        isinstance(action.arguments, dict)
        and isinstance(action.arguments.get("body"), dict)
        and isinstance(action.arguments["body"].get("title"), str)
        and len(action.arguments["body"]["title"]) >= 3
        and action.arguments["body"]["title"] in prompt
        for action in actions
    )
    if not actions or not (CONTINUATION.match(prompt) or same_subject):
        return None
    return {
        "parent_plan_id": str(pending.id),
        "plan_version": getattr(pending, "plan_version", None),
        "relation": "revision",
        "draft": [
            {
                "operation": action.title,
                "tool_name": action.tool_name,
                "arguments": action.arguments,
            }
            for action in actions
        ],
    }


def revision_prompt(session, pending, prompt: str) -> str:
    """Compatibility helper for older callers; new runs keep the raw prompt."""
    draft = pending_draft(session, pending, prompt)
    if draft is None:
        return prompt
    return (
        "用户正在修订尚未执行的操作计划。以下是旧草稿数据，不代表对象已经创建；"
        "不能用旧草稿查找或修改现有对象。"
        "如果用户只是更改旧草稿的日期、时间或内容，请保留旧草稿的创建工具及参数结构，"
        "只替换用户更改的字段，重新提出待确认的创建计划；不要改用编辑工具。"
        "如果用户提出无关的新请求，则按新请求处理。\n"
        f"旧草稿：{json.dumps(draft['draft'], ensure_ascii=False)[:2500]}\n"
        f"用户补充：{prompt}"
    )
