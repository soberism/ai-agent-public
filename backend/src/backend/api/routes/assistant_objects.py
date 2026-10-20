from sqlalchemy import select

from backend.api.routes.assistant_actions import confirmation
from backend.api.schemas import AssistantReply
from backend.db.models import CalendarEvent, Checklist, Todo
from backend.features.sharing.access import visible_condition


def manage_reply(intent, store, user, session, thread_id):
    model = {"event": CalendarEvent, "checklist": Checklist, "todo": Todo}.get(
        intent.target_type
    )
    if (
        model is None
        or not intent.operation
        or not intent.title
        or (intent.operation == "rename" and not intent.new_title)
    ):
        return AssistantReply(
            kind="clarify", message="请说明要修改的对象、完整标题和新标题。"
        )
    matches = list(
        session.scalars(
            select(model)
            .where(visible_condition(model, user.id), model.title == intent.title)
            .limit(2)
        )
    )
    if len(matches) != 1:
        return AssistantReply(
            kind="clarify", message="请提供一个能唯一匹配对象的完整标题。"
        )
    label = "删除" if intent.operation == "delete" else "重命名"
    return confirmation(
        store,
        user,
        thread_id,
        "manage_object",
        {
            "id": str(matches[0].id),
            "kind": intent.target_type,
            "operation": intent.operation,
            "new_title": intent.new_title,
        },
        f"确认{label}“{intent.title}”吗？",
        f"确认{label}",
    )
