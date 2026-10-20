"""Reuses authenticated read routes for the assistant's bounded planning loop."""

import json
from uuid import UUID

from fastapi.encoders import jsonable_encoder

from backend.api.calendar_schemas import EventQuery
from backend.api.routes.assistant_features import prepare
from backend.api.routes.assistant_native_reads import native_read
from backend.api.routes.assistant_threads import search_reply
from backend.api.routes.calendar_events import detail as event_detail
from backend.api.routes.calendar_events import list_all as list_all_events
from backend.api.routes.calendar_events import listing as list_events
from backend.api.routes.households import detail as household_detail
from backend.api.routes.life import meals
from backend.api.routes.planning import get_checklist, list_checklists
from backend.api.routes.planning_review import ReviewQuery, review
from backend.api.routes.todos import listing
from backend.api.schemas import TodoQuery
from backend.core.security import APIError
from backend.features.assistant.answer_evidence import scope_for
from backend.features.assistant.feature_replies import without_member_emails
from backend.features.assistant.graph import Intent
from backend.features.assistant.read_filters import filter_result
from backend.features.assistant.workflow_tools import READ_FEATURES


def event_summaries(data):
    items = data["items"]
    if len(items) > 50:
        raise ValueError("查询结果超过50条，请缩小时间范围")
    fields = (
        "id",
        "title",
        "status",
        "assignee_id",
        "start_date",
        "start_time",
        "end_date",
        "end_time",
    )
    return {
        "items": [{key: row[key] for key in fields} for row in items],
        "complete": True,
        "total_count": len(items),
    }


def inspect(name, payload, store, user, session, thread_id):
    if name not in READ_FEATURES:
        raise APIError(422, "INVALID_ACTION", "只能先查询已开放的数据")
    try:
        payload = dict(payload)
        filters = payload.pop("filters", None)
        if filters:
            base_scope = scope_for(
                payload.get("query", {}), user.timezone if user else "Asia/Shanghai"
            )
            if name == "list_todos":
                base_scope.setdefault("status", "ongoing")
            if any(
                key in base_scope and base_scope[key] != value
                for key, value in filters.items()
                if value is not None
            ):
                raise ValueError("列表原始查询与筛选条件冲突，请使用相同范围")
        if name in {"query_todos", "list_todos"}:
            if name == "query_todos":
                intent = Intent.model_validate({**payload, "action": name})
                if intent.reference_index is not None:
                    raise ValueError("不能用序号进行独立查询")
                query = TodoQuery(
                    status=intent.status,
                    due=intent.due,
                    due_time=intent.due_time,
                    date_from=intent.date_from,
                    date_to=intent.date_to,
                )
            else:
                query = TodoQuery.model_validate(payload["query"])
            page = listing(query, user, session)
            data = page.model_dump(mode="json")
            data["kind"] = "result"
            data["items"] = [{**item, "kind": "todo"} for item in data["items"]]
            data["complete"] = not query.cursor and data["next_cursor"] is None
            data["total_count"] = len(data["items"]) if data["complete"] else None
        elif name == "review_plan":
            args, _ = prepare(name, payload, user, session)
            data = jsonable_encoder(review(ReviewQuery(**args["query"]), user, session))
            data["items"] = [
                item
                for group in ("completed", "ongoing", "events")
                for item in data["details"][group]
            ]
            data["complete"] = True
            data["total_count"] = len(data["items"])
        elif name == "search_systems":
            intent = Intent.model_validate({**payload, "action": name})
            data = search_reply(intent, user, session).model_dump(mode="json")
        elif name == "list_all_events":
            prepare(name, payload, user, session)
            data = event_summaries(
                list_all_events(user, session).model_dump(mode="json")
            )
        elif name == "list_events":
            data = event_summaries(
                list_events(
                    EventQuery.model_validate(payload["query"]), user, session
                ).model_dump(mode="json")
            )
        elif name == "get_event":
            args, _ = prepare(name, payload, user, session)
            event = event_detail(UUID(args["event_id"]), user, session).model_dump(
                mode="json"
            )
            data = {
                "kind": "result",
                "items": [
                    {**event, "kind": "event", "url": f"/calendar/{event['id']}/edit"}
                ],
            }
        elif name == "get_household":
            args, _ = prepare(name, payload, user, session)
            data = without_member_emails(
                household_detail(UUID(args["household_id"]), user, session).model_dump(
                    mode="json"
                )
            )
            data["complete"] = True
        elif name == "get_checklist":
            args, _ = prepare(name, payload, user, session)
            data = get_checklist(UUID(args["checklist_id"]), user, session).model_dump(
                mode="json"
            )
        elif name == "list_checklists":
            data = {
                "items": [
                    {
                        "id": str(item.id),
                        "title": item.title,
                        "total_count": item.total_count,
                        "completed_count": item.completed_count,
                    }
                    for item in list_checklists(user, session).items
                ]
            }
            data["complete"] = True
            data["total_count"] = len(data["items"])
        elif name == "list_meals":
            prepare(name, payload, user, session)
            data = meals(user, session).model_dump(mode="json")
            data["items"] = [
                {**item, "kind": "meal", "url": f"/meals/{item['id']}"}
                for item in data["items"]
            ]
            data["complete"] = True
            data["total_count"] = len(data["items"])
        else:
            data = native_read(name, payload, user, session)
        if filters is not None:
            data = filter_result(
                name, data, filters, user.timezone if user else "Asia/Shanghai"
            )
        result = json.dumps(data, ensure_ascii=False)
        if len(result) > 14000:
            raise ValueError("查询结果过多，无法可靠判断；请缩小时间或对象范围")
        return result
    except (ValueError, TypeError) as error:
        raise APIError(422, "INVALID_ACTION", str(error)) from None
