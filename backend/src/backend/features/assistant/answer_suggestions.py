"""Offer bounded next steps only for a single verified business object."""

from uuid import UUID, uuid4

from backend.api.routes.assistant_features import invoke
from backend.api.suggestion_schemas import Suggestion
from backend.core.security import APIError
from backend.features.assistant.capabilities import CAPABILITIES
from backend.features.assistant.feature_replies import result_reply

READ_ARGUMENTS = {
    "todo": ("get_todo", "id"),
    "event": ("get_event", "event_id"),
    "checklist": ("get_checklist", "checklist_id"),
    "reminder": ("list_reminders", None),
}
TOP_LEVEL_WRITE_RESULTS = {
    "create_todo",
    "edit_todo",
    "create_event",
    "create_shared_event",
    "edit_event",
    "create_checklist",
    "create_shared_checklist",
    "rename_checklist",
    "duplicate_checklist",
    "create_reminder",
    "edit_reminder",
}


def _choice(run_id, item: dict, label: str, intent: str, draft=None, url=None):
    try:
        target_id = UUID(str(item["id"]))
    except KeyError, TypeError, ValueError:
        return None
    return Suggestion(
        id=uuid4(),
        source_run_id=run_id,
        label=label,
        type="follow_up" if draft else "navigate",
        intent=intent,
        target_kind=item["kind"],
        target_id=target_id,
        target_title=str(item.get("title") or "该事项")[:100],
        draft=draft,
        url=url,
    ).model_dump(mode="json")


def from_result(run_id, result: dict) -> list[dict]:
    if not isinstance(result, dict) or result.get("kind") not in {"result", "success"}:
        return []
    items = result.get("items")
    if not isinstance(items, list) or len(items) != 1:
        return []
    item = items[0]
    if not isinstance(item, dict) or item.get("kind") not in READ_ARGUMENTS:
        return []
    kind = item["kind"]
    title = str(item.get("title") or "该事项").replace("\n", " ")[:100]
    if kind == "todo":
        choices = [
            (
                "标记完成" if item.get("status") != "completed" else "查看待办",
                "edit_todo" if item.get("status") != "completed" else "open_todo",
                f"把待办「{title}」标记完成"
                if item.get("status") != "completed"
                else None,
                None if item.get("status") != "completed" else f"/todos/{item['id']}",
            ),
        ]
    elif kind == "event":
        choices = [
            ("调整时间", "edit_event", f"把日程「{title}」改到：", None),
        ]
    elif kind == "checklist":
        choices = [
            ("添加清单项", "add_checklist_item", f"在清单「{title}」添加：", None),
            ("查看清单", "open_checklist", None, f"/checklists/{item['id']}"),
        ]
    else:
        choices = [
            ("关闭提醒", "edit_reminder", f"关闭这个应用内提醒：{title}", None),
            ("查看提醒", "open_reminder", None, "/todos"),
        ]
    return [
        choice
        for label, intent, draft, url in choices
        if (choice := _choice(run_id, item, label, intent, draft, url))
    ]


def from_observations(run_id, observations: list[dict]) -> list[dict]:
    if not observations:
        return []
    observation = observations[-1]
    result = observation.get("result")
    tool = observation.get("tool_name")
    if (
        tool in CAPABILITIES
        and isinstance(result, dict)
        and result.get("kind") not in {"result", "success"}
    ):
        result = result_reply(tool, result).model_dump(mode="json")
    return from_result(run_id, result)


def from_actions(run_id, actions: list) -> list[dict]:
    completed = [action for action in actions if action.status == "completed"]
    if len(completed) != 1 or len(completed) != len(actions):
        return []
    if completed[0].tool_name not in TOP_LEVEL_WRITE_RESULTS:
        return []
    return from_result(run_id, completed[0].result)


def resolve(session, user, source, suggestion_id, prompt: str) -> dict:
    if source.status != "completed":
        raise APIError(409, "SUGGESTION_STALE", "原任务尚未成功完成")
    suggestion = next(
        (
            item
            for item in source.suggestions or []
            if item.get("id") == str(suggestion_id)
        ),
        None,
    )
    if not suggestion or suggestion.get("type") != "follow_up":
        raise APIError(404, "SUGGESTION_NOT_FOUND", "快捷操作不存在或已失效")
    selected = Suggestion.model_validate(suggestion)
    if not prompt.startswith(selected.draft or ""):
        raise APIError(422, "SUGGESTION_CHANGED", "快捷操作内容已改变，请重新选择")
    read_name, id_field = READ_ARGUMENTS[selected.target_kind]
    arguments = {id_field: str(selected.target_id)} if id_field else {}
    reply = invoke(read_name, arguments, user, session)
    item = next((item for item in reply.items if item.id == selected.target_id), None)
    if item is None:
        raise APIError(409, "SUGGESTION_STALE", "关联事项已不可访问，请重新查询")
    if selected.intent == "edit_todo" and item.status == "completed":
        raise APIError(409, "SUGGESTION_STALE", "这条待办已经完成")
    if selected.intent == "edit_reminder" and item.status != "scheduled":
        raise APIError(409, "SUGGESTION_STALE", "这条提醒已关闭")
    return {
        "kind": "suggestion",
        "source_run_id": str(source.id),
        "suggestion_id": str(selected.id),
        "intent": selected.intent,
        "target_kind": selected.target_kind,
        "target_id": str(selected.target_id),
        "target_title": item.title,
    }


def verify_plan(context: dict, name: str, arguments: dict) -> None:
    """A suggestion can only propose its bound operation on its bound object."""
    if context.get("kind") != "suggestion":
        return
    if name != context["intent"]:
        raise APIError(422, "SUGGESTION_MISMATCH", "快捷操作与待确认计划不一致")
    target_field = {
        "create_reminder": f"body.{context['target_kind']}_id",
        "edit_todo": "id",
        "edit_event": "event_id",
        "add_checklist_item": "checklist_id",
        "edit_reminder": "reminder_id",
    }[name]
    value = arguments
    for key in target_field.split("."):
        value = value.get(key) if isinstance(value, dict) else None
    if str(value) != context["target_id"]:
        raise APIError(422, "SUGGESTION_MISMATCH", "快捷操作的目标事项不一致")
