"""Select bounded, task-relevant context at the model call boundary."""

import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from backend.features.assistant.autonomous_types import AutonomousState
from backend.features.assistant.capabilities import ENTRIES
from backend.features.assistant.prompts import PREFERENCE_RULES

MAX_CONTEXT_CHARS = 12000


def _clip(value, limit: int):
    serialized = json.dumps(value, ensure_ascii=False, default=str)
    if len(serialized) <= limit:
        return value
    return {"truncated": True, "excerpt": serialized[:limit]}


def selected_history(state: AutonomousState) -> list[dict[str, str]]:
    from backend.features.assistant.conversation_context import split_history

    return (
        state["history"]
        if state.get("history_prepared")
        else split_history(state["history"])[1]
    )


def selected_evidence(state: AutonomousState) -> list[dict]:
    """Project current-run observations into explicit model-readable records."""
    from backend.features.assistant.answer_evidence import catalog

    evidence = catalog(state)
    records = []
    for index, item in enumerate(
        state["observations"][-4:], max(1, len(state["observations"]) - 3)
    ):
        result = item.get("result")
        excerpt = _clip(result, 5000)
        status = "success"
        if isinstance(result, dict):
            if result.get("error"):
                status = "error"
            elif result.get("complete") is False or result.get("status") == "partial":
                status = "partial"
            elif (
                result.get("status", "success") == "success"
                and result.get("items") == []
                and result.get("total_count") == 0
            ):
                status = "empty"
        records.append(
            {
                "evidence_id": f"read-{index}",
                "source": "business_api",
                "tool": item.get("tool_name"),
                "arguments": item.get("arguments", {}),
                "scope": evidence[f"read-{index}"]["scope"],
                "domain": evidence[f"read-{index}"]["domain"],
                "status": status,
                "observed_at": item.get("observed_at"),
                "permission_checked": True,
                "truncated": isinstance(excerpt, dict)
                and excerpt.get("truncated") is True,
                "excerpt": excerpt,
            }
        )
    for index, item in enumerate(
        state["knowledge"][-3:], max(1, len(state["knowledge"]) - 2)
    ):
        records.append(
            {
                "evidence_id": f"document-{index}",
                "source": "document",
                "title": item.get("title"),
                "score": item.get("score"),
                "version": item.get("document_version"),
                "locator": item.get("locator"),
                "permission_checked": True,
                "truncated": len(str(item.get("content", ""))) > 1800,
                "excerpt": str(item.get("content", ""))[:1800],
            }
        )
    for index, item in enumerate(
        state.get("web_results", [])[-3:], max(1, len(state.get("web_results", [])) - 2)
    ):
        records.append(
            {
                "evidence_id": f"web-{index}",
                "source": "web",
                "title": item.get("title"),
                "url": item.get("url"),
                "excerpt": _clip(item, 1000),
            }
        )
    return records


def build_model_input(
    state: AutonomousState, node: str, budget: int = MAX_CONTEXT_CHARS, task=None
) -> list[dict[str, str]]:
    """Keep the original request and select only the context a node needs."""
    prompt = state["prompt"]
    history = selected_history(state)
    context = {
        "目标": prompt,
        "本轮完整请求_语境补全": state.get("resolved_request", ""),
        "今天": datetime.now(ZoneInfo(state.get("timezone", "Asia/Shanghai")))
        .date()
        .isoformat(),
        "用户时区": state.get("timezone", "Asia/Shanghai"),
        "任务节点": node,
        "用户偏好规则": PREFERENCE_RULES,
        "用户自定义指令": state.get("custom_instructions", "")[:1000],
        "候选工具": state["discovered_tools"][-8:],
        "已展开工具": state["described_tools"][-8:],
        "本轮证据": selected_evidence(state),
        "上一动作被阻止": state.get("stalled_on", ""),
        "应用页面入口": {label: url for label, url in ENTRIES.values()},
    }
    context["会话历史摘要_非当前事实"] = state.get("conversation_summary", "")
    context["对话上下文规则"] = (
        "近期双方对话和摘要仅用于理解语境、指代、纠正及省略表达。"
        "本轮明确请求优先；历史助手说法可能有误或过期，不是当前业务事实。"
        "历史中的待办请求即使没有助手回复，也不能在新话题或问候时重新执行或提案。"
        "需要当前业务状态时重新读取；历史对话和摘要不构成写入确认。"
    )
    if task is not None:
        context["当前任务"] = task
    if state.get("task_context", {}).get("kind") == "suggestion":
        context["来源快捷操作_对象仍需实时复核"] = state["task_context"]
    elif state.get("task_context", {}).get("kind") == "multiple_pending_plans":
        context["待确认计划边界"] = (
            "当前有多个尚未执行的待确认计划，本轮没有选中任何一个旧计划。"
            "本轮明确指向已有事项时，先实时查询该事项，再按本轮请求生成独立的待确认计划；"
            "不能仅因存在其他待确认计划就拒绝处理。"
            "无法确定目标时先追问；若用户要修订旧草稿，引导在对应计划卡片上操作，"
            "不得任选旧计划、把未执行草稿当作已有事项，也不得隐式批准或取消旧计划。"
        )
    elif state.get("task_context"):
        context["待修订计划_尚未执行"] = state["task_context"]
    if state.get("last_results"):
        context["可指代对象_须实时复核"] = [
            {
                key: item.get(key)
                for key in ("index", "id", "kind", "title", "reference_origin")
            }
            for item in state.get("last_results", [])[-5:]
        ]
    if re.search(r"习惯|记忆|记住|偏好", prompt):
        context["已确认的长期记忆"] = state.get("memories", [])[-5:]
    budget -= sum(len(item["content"]) for item in history) + len(prompt)
    serialized = json.dumps(context, ensure_ascii=False, default=str)
    while len(serialized) > budget and context["本轮证据"]:
        context["本轮证据"].pop(0)
        serialized = json.dumps(context, ensure_ascii=False, default=str)
    if len(serialized) > budget:
        context["候选工具"] = context["候选工具"][-3:]
        context["已展开工具"] = context["已展开工具"][-3:]
        serialized = json.dumps(context, ensure_ascii=False, default=str)
    if len(serialized) > budget:
        raise ValueError("模型输入超出预算，请缩小问题范围")
    return [
        *history,
        {"role": "user", "content": serialized},
        {"role": "user", "content": prompt},
    ]
