from uuid import uuid4

from fastapi import APIRouter, Depends
from sqlalchemy import select

from backend.api.calendar_schemas import EventCreate
from backend.api.planning_schemas import ChecklistWithItemsCreate
from backend.api.routes.assistant_actions import confirmation
from backend.api.routes.assistant_actions import router as actions_router
from backend.api.routes.assistant_objects import manage_reply
from backend.api.routes.assistant_read_steps import inspect
from backend.api.routes.assistant_threads import query_message, search_reply
from backend.api.routes.assistant_threads import router as threads_router
from backend.api.routes.todos import listing
from backend.api.schemas import (
    ERROR_RESPONSES,
    AssistantItem,
    AssistantMessage,
    AssistantReply,
    TodoCreate,
    TodoQuery,
)
from backend.core.security import DB, APIError, Principal, Store
from backend.db.models import Todo
from backend.features.assistant import history
from backend.features.assistant.access import current_context, current_item
from backend.features.assistant.graph import interpret
from backend.features.assistant.preferences import model_context
from backend.features.assistant.replies import personalize
from backend.features.assistant.request_limits import enforce
from backend.features.assistant.threads import ThreadItem
from backend.features.assistant.threads import load as load_thread
from backend.features.assistant.web_search import with_sources
from backend.features.sharing.access import visible_condition

router = APIRouter(
    prefix="/api/assistant",
    tags=["AI待办助手"],
    responses=ERROR_RESPONSES,
    dependencies=[Depends(enforce)],
)
router.include_router(actions_router)
router.include_router(threads_router)


@router.post("/messages", response_model=AssistantReply)
def message(body: AssistantMessage, user: Principal, session: DB, store: Store):
    saved_thread = history.owned(session, body.thread_id, user.id)
    try:
        thread = load_thread(store, body.thread_id, user.id)
    except APIError:
        saved = history.messages(session, body.thread_id)
        history.cache(store, user.id, body.thread_id, saved)
        thread = load_thread(store, body.thread_id, user.id)
    custom_instructions, memories = model_context(session, user.id)
    safe_history, safe_results = current_context(session, user, thread, body.thread_id)
    intent = interpret(
        body.message,
        safe_history,
        safe_results,
        custom_instructions,
        memories,
        user.timezone,
        lambda name, payload: inspect(
            name, payload, store, user, session, body.thread_id
        ),
    )

    def answer(reply: AssistantReply, last_results: list[ThreadItem] | None = None):
        if intent.action != "respond":
            reply = personalize(reply, custom_instructions, memories)
        reply.message = with_sources(reply.message, intent._sources)
        history.append_pair(session, saved_thread, body.message, reply)
        history.cache(
            store, user.id, body.thread_id, history.messages(session, body.thread_id)
        )
        return reply

    if intent.action == "open_feature":
        from backend.features.assistant.feature_replies import entry_reply

        return answer(entry_reply(intent.feature))
    if intent.action == "feature":
        from backend.api.routes.assistant_features import feature_reply

        reply = feature_reply(
            intent.feature, intent.payload, store, user, session, body.thread_id
        )
        return answer(
            reply,
            [ThreadItem(**item.model_dump(mode="json")) for item in reply.items]
            if reply.kind == "result"
            else None,
        )

    if intent.reference_index is not None:
        index = intent.reference_index - 1
        if index >= len(thread.last_results):
            return answer(
                AssistantReply(
                    kind="clarify", message="最近的查询结果中没有这一条待办。"
                )
            )
        selected = current_item(session, user, thread.last_results[index])
        if selected is None:
            return answer(
                AssistantReply(
                    kind="clarify", message="这条内容已不可访问，请重新查询。"
                )
            )
        selected_item = AssistantItem(**selected.model_dump())
        if intent.action == "query_todos":
            return answer(
                AssistantReply(
                    kind="result",
                    message=f"这是第{intent.reference_index}条待办。",
                    items=[selected_item],
                )
            )
        if intent.action == "complete_todo":
            todo = session.scalar(
                select(Todo).where(
                    Todo.id == selected.id,
                    visible_condition(Todo, user.id),
                    Todo.status == "ongoing",
                )
            )
            if todo is None:
                return answer(
                    AssistantReply(
                        kind="clarify", message="这条待办已不可完成，请重新查询。"
                    )
                )
            return answer(
                confirmation(
                    store,
                    user,
                    body.thread_id,
                    "complete",
                    {"id": str(todo.id)},
                    f"确认完成“{todo.title}”吗？",
                    "确认完成",
                )
            )
        return answer(
            AssistantReply(kind="clarify", message="请说明要查看还是完成这条待办。")
        )
    if intent.action == "clarify":
        return answer(
            AssistantReply(kind="clarify", message=intent.message or "请再具体一点。")
        )
    if intent.action == "respond":
        return answer(
            AssistantReply(kind="message", message=intent.message or "我在，请继续说。")
        )
    if intent.action == "query_todos":
        page = listing(
            TodoQuery(
                status=intent.status,
                due=intent.due,
                due_time=intent.due_time,
                date_from=intent.date_from,
                date_to=intent.date_to,
            ),
            user,
            session,
        )
        results = [
            AssistantItem(
                **value.model_dump(
                    include={"id", "title", "due_date", "due_time", "status"}
                )
            )
            for value in page.items
        ]
        return answer(
            AssistantReply(
                kind="result",
                message=query_message(results, intent.status),
                items=results,
            ),
            [ThreadItem(**value.model_dump(mode="json")) for value in results],
        )
    if intent.action == "search_systems":
        reply = search_reply(intent, user, session)
        return answer(
            reply,
            [ThreadItem(**item.model_dump(mode="json")) for item in reply.items]
            if reply.kind == "result"
            else None,
        )
    if intent.action == "create_checklist":
        try:
            draft = ChecklistWithItemsCreate(title=intent.title, items=intent.items)
        except ValueError:
            return answer(
                AssistantReply(
                    kind="clarify",
                    message="清单名称和每项内容须为1至15字，最多50项，请调整后重试。",
                )
            )
        preview = "\n".join(
            f"{index}. {title}" for index, title in enumerate(draft.items, 1)
        )
        return answer(
            confirmation(
                store,
                user,
                body.thread_id,
                "create_checklist",
                draft.model_dump(mode="json"),
                f"确认创建清单“{draft.title}”（共{len(draft.items)}项）吗？"
                + (f"\n{preview}" if preview else ""),
                "确认创建",
            )
        )
    if intent.action == "create_event":
        try:
            payload = EventCreate(
                title=intent.title,
                start_date=intent.start_date,
                start_time=intent.start_time,
                end_date=intent.end_date,
                end_time=intent.end_time,
            ).model_dump(mode="json")
        except ValueError:
            return answer(
                AssistantReply(
                    kind="clarify", message="请补充有效的日程标题和起止时间。"
                )
            )
        return answer(
            confirmation(
                store,
                user,
                body.thread_id,
                "create_event",
                payload,
                f"确认创建日程“{payload['title']}”吗？",
                "确认创建",
            )
        )
    if intent.action == "manage_object":
        return answer(manage_reply(intent, store, user, session, body.thread_id))
    if intent.action == "create_todo":
        try:
            payload = TodoCreate(
                title=intent.title,
                description=intent.description,
                due_date=intent.due_date,
                due_time=intent.due_time,
            ).model_dump(mode="json")
        except ValueError:
            return answer(
                AssistantReply(
                    kind="clarify", message="请补充有效的待办标题和截止时间。"
                )
            )
        payload["create_key"] = str(uuid4())
        return answer(
            confirmation(
                store,
                user,
                body.thread_id,
                "create",
                payload,
                f"确认创建待办“{payload['title']}”吗？",
                "确认创建",
            )
        )
    title = (intent.title or "").strip()
    matches = list(
        session.scalars(
            select(Todo)
            .where(
                visible_condition(Todo, user.id),
                Todo.status == "ongoing",
                Todo.title == title,
            )
            .limit(2)
        )
    )
    if len(matches) != 1:
        return answer(
            AssistantReply(
                kind="clarify", message="请提供一个能唯一匹配进行中待办的完整标题。"
            )
        )
    return answer(
        confirmation(
            store,
            user,
            body.thread_id,
            "complete",
            {"id": str(matches[0].id)},
            f"确认完成“{title}”吗？",
            "确认完成",
        )
    )
