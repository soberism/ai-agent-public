"""Revalidate cached business results before giving them to the model."""

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select

from backend.core.security import APIError
from backend.db.agent_models import AgentAction, AgentRun
from backend.db.household_models import Household, HouseholdParticipant
from backend.db.models import AssistantMemory, Todo, utcnow
from backend.features.assistant.capabilities import CAPABILITIES
from backend.features.assistant.threads import ThreadItem
from backend.features.sharing.access import MODELS, accessible


def current_item(session, user, item):
    if item.kind == "invitation":
        row = session.get(HouseholdParticipant, item.id)
        if (
            not row
            or row.email != user.email
            or row.status != "pending"
            or row.role != "member"
            or not row.expires_at
            or row.expires_at <= utcnow()
        ):
            return None
        home = session.get(Household, row.household_id)
        return item.model_copy(update={"title": home.name}) if home else None
    if item.kind == "household":
        from backend.api.household_access import participant

        try:
            participant(session, user, item.id)
            row = session.get(Household, item.id)
            return item.model_copy(update={"title": row.name})
        except APIError:
            return None
    if item.kind == "memory":
        row = session.get(AssistantMemory, item.id)
        return (
            item.model_copy(update={"title": row.content[:100]})
            if row and row.owner_id == user.id
            else None
        )
    model = MODELS.get("material" if item.kind == "document" else item.kind)
    if model is None:
        return None
    try:
        row = accessible(session, user, model, item.id)
    except APIError:
        return None
    if model is Todo:
        return ThreadItem(
            id=row.id,
            title=row.title,
            due_date=row.due_date.isoformat() if row.due_date else None,
            due_time=row.due_time.strftime("%H:%M") if row.due_time else None,
            status=row.status,
        )
    title = next(
        (
            getattr(row, key)
            for key in ("title", "name", "label", "transcript", "source_text")
            if hasattr(row, key)
        ),
        item.title,
    )
    return item.model_copy(update={"title": (title or item.title)[:100]})


def current_data(session, user, item):
    from backend.api.routes import calendar_events, households, life, planning

    if item.kind == "invitation":
        row = session.get(HouseholdParticipant, item.id)
        return {"id": str(row.id), "status": row.status, "household_name": item.title}
    if item.kind == "event":
        return calendar_events.detail(item.id, user, session).model_dump(mode="json")
    if item.kind == "checklist":
        return planning.get_checklist(item.id, user, session).model_dump(mode="json")
    if item.kind == "meal":
        return life.get_meal(item.id, user, session).model_dump(mode="json")
    if item.kind == "household":
        return households.detail(item.id, user, session).model_dump(mode="json")
    if item.kind == "memory":
        row = session.get(AssistantMemory, item.id)
    else:
        row = accessible(
            session,
            user,
            MODELS["material" if item.kind == "document" else item.kind],
            item.id,
        )
    return jsonable_encoder(
        {
            key: getattr(row, key)
            for key in (
                "title",
                "description",
                "due_date",
                "due_time",
                "status",
                "name",
                "quantity",
                "unit",
                "label",
                "kind",
                "transcript",
                "content",
                "enabled",
                "source_text",
                "candidates",
                "folder_id",
            )
            if hasattr(row, key) and not (key == "content" and item.kind != "memory")
        }
    )


def current_context(session, user, thread, thread_id):
    checked_items = {}

    def checked(item):
        key = (item.kind, item.id)
        if key not in checked_items:
            checked_items[key] = current_item(session, user, item)
        return checked_items[key]

    revoked_titles = set()
    results = []
    for index, item in enumerate(thread.last_results, 1):
        fresh = checked(item)
        if fresh is None:
            revoked_titles.add(item.title)
        else:
            results.append(
                {
                    "index": index,
                    "reference_origin": "last_result",
                    **fresh.model_dump(mode="json"),
                    "data": current_data(session, user, fresh),
                }
            )
    recent_actions = session.scalars(
        select(AgentAction)
        .join(AgentRun, AgentAction.run_id == AgentRun.id)
        .where(
            AgentRun.thread_id == thread_id,
            AgentRun.owner_id == user.id,
            AgentAction.status == "completed",
        )
        .order_by(AgentRun.updated_at.desc(), AgentAction.position.desc())
        .limit(10)
    )
    for action in recent_actions:
        for value in (action.result or {}).get("items", []):
            item = ThreadItem.model_validate(value)
            if any(result["id"] == str(item.id) for result in results):
                continue
            fresh = checked(item)
            if fresh is not None:
                results.append(
                    {
                        "index": len(results) + 1,
                        "reference_origin": "recent_action",
                        **fresh.model_dump(mode="json"),
                        "data": current_data(session, user, fresh),
                    }
                )
    # 查询历史只用于理解语境；业务事实始终重新查询。
    from backend.features.assistant.history import messages

    saved_messages = messages(session, thread_id)
    revoked_messages = set()
    for saved in saved_messages:
        for value in [
            *(saved.items or []),
            *(getattr(saved, "context_refs", None) or []),
        ]:
            item = ThreadItem.model_validate(value)
            if item.kind == "navigation":
                continue
            if checked(item) is None:
                revoked_titles.add(item.title)
                revoked_messages.add(saved.content)
    unverified = {
        saved.content
        for saved in saved_messages
        if saved.kind == "result"
        and saved.items is None
        and getattr(saved, "context_refs", None) is None
    }
    history = []
    for value in thread.messages:
        content = (
            "此前业务回答缺少可复核对象引用，请重新查询；此前用户请求仍可用于理解语境。"
            if value.role == "assistant" and value.content in unverified
            else value.content
        )
        for title in revoked_titles:
            content = content.replace(title, "[已不可访问的内容]")
        # 旧结果带有细节，整段移除而非仅替换标题。
        if value.role == "assistant" and (
            value.content in revoked_messages
            or any(title in value.content for title in revoked_titles)
        ):
            content = "此前查询的部分业务内容已不可访问，请重新查询。"
        history.append({"role": value.role, "content": content})
    return history, results


def observation_references(observations):
    """Retain only object locators so future turns can recheck historical access."""
    kinds = {
        "list_todos": "todo",
        "query_todos": "todo",
        "get_todo": "todo",
        "list_events": "event",
        "get_event": "event",
        "list_checklists": "checklist",
        "get_checklist": "checklist",
    }
    references = {}
    for observation in observations:
        result = observation.get("result", {})
        if not isinstance(result, dict):
            continue
        tool = observation.get("tool_name")
        default_kind = (
            kinds.get(tool) or (CAPABILITIES.get(tool) or (None, None, None, None))[3]
        )
        if tool == "incoming_invitations":
            default_kind = "invitation"
        if default_kind in {"settings", "navigation", "sharing", "search", "review"}:
            default_kind = None
        values = result.get("items", [])
        if observation.get("tool_name") == "review_plan":
            values = [
                {**item, "kind": "event" if group == "events" else "todo"}
                for group in ("completed", "ongoing", "events")
                for item in result.get("details", {}).get(group, [])
            ]
        if result.get("id") and default_kind:
            values = [result]
        for value in values:
            if not isinstance(value, dict):
                continue
            kind = default_kind or value.get("kind")
            title = next(
                (
                    value[k]
                    for k in (
                        "title",
                        "name",
                        "label",
                        "content",
                        "transcript",
                        "remind_at",
                        "household_name",
                    )
                    if value.get(k)
                ),
                "",
            )
            if not kind or not value.get("id") or not title:
                continue
            try:
                item = ThreadItem(
                    id=value["id"],
                    title=str(title)[:100],
                    kind=kind,
                    status=value.get("status") or "available",
                )
            except ValueError:
                continue
            references[(kind, str(item.id))] = item.model_dump(mode="json")
    return list(references.values())
