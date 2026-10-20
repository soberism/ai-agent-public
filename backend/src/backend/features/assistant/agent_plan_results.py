"""Summarize persisted action outcomes for the chat history."""

from sqlalchemy import select

from backend.db.agent_models import AgentAction


def fail_stale_actions(session, run_id):
    stale = session.scalars(
        select(AgentAction).where(
            AgentAction.run_id == run_id,
            AgentAction.status == "executing",
        )
    )
    for action in stale:
        action.status = "failed"
        action.error = "执行结果待核对，请勿重复提交"
    session.commit()


def outcome(action):
    if action.status == "failed":
        return f"{action.title}失败：{action.error or '请稍后核对结果'}"
    result = action.result or {}
    items = result.get("items") or []
    title = items[0].get("title") if len(items) == 1 else None
    if action.tool_name == "create_checklist":
        title = title or action.arguments.get("body", {}).get("title")
        count = len(action.arguments.get("body", {}).get("items", []))
        return f"已创建清单「{title}」，包含 {count} 项"
    if action.tool_name in {"add_checklist_item", "add_shopping_item"}:
        body = action.arguments.get("body", {})
        item = body.get("title") or body.get("name")
        if title and item:
            return f"已在「{title}」清单添加「{item}」"
        return f"已添加清单项「{item}」" if item else f"{action.title}已完成"
    if action.tool_name == "set_sharing":
        scope = action.arguments.get("body", {}).get("scope")
        visibility = {
            "private": "仅自己可见",
            "household": "家庭可见",
            "members": "指定成员可见",
        }.get(scope, "已更新可见范围")
        return f"已将「{title}」设为{visibility}" if title else visibility
    if (
        action.tool_name.startswith("delete_")
        or action.tool_name in {"check_item", "bulk_checklist"}
    ) and action.description:
        return f"{action.title}已完成（{action.description}）"
    return f"{action.title}「{title}」已完成" if title else f"{action.title}已完成"


def summarize(actions):
    answer = "；".join(outcome(action) for action in actions) + "。"
    if len(answer) <= 900:
        return answer
    completed = sum(action.status == "completed" for action in actions)
    failed = sum(action.status == "failed" for action in actions)
    return f"已完成 {completed} 项操作，{failed} 项失败；请核对对应事项。"


def result_items(actions):
    items = {}
    for action in actions:
        if action.status != "completed":
            continue
        for item in (action.result or {}).get("items", []):
            if not isinstance(item, dict) or not item.get("kind") or not item.get("id"):
                continue
            items[(item["kind"], item["id"])] = item
    return list(items.values())
