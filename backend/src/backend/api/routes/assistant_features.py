"""Thin adapter: validate, preview, confirm, then call existing business routes."""

from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import Response
from pydantic import ValidationError

from backend.api.routes.assistant_actions import confirmation
from backend.api.schemas import AssistantItem, AssistantReply
from backend.core.security import APIError
from backend.features.assistant.capabilities import CAPABILITIES
from backend.features.assistant.feature_edits import EDIT_MODELS, complete_edit
from backend.features.assistant.feature_replies import preview, result_reply
from backend.features.assistant.feature_targets import bind_targets
from backend.features.assistant.feature_tools import contract, parse_arguments


def validate(name, payload):
    if name not in CAPABILITIES:
        raise APIError(422, "INVALID_ACTION", "这项AI能力尚未开放")
    try:
        parsed = parse_arguments(name, payload)
        if name == "review_plan":
            from backend.api.routes.planning_review import ReviewQuery

            ReviewQuery(**parsed.query.model_dump(mode="json"))
        return parsed
    except ValidationError:
        raise APIError(
            422, "INVALID_ACTION", "参数不完整或无效，请补充有效的对象和内容"
        ) from None


def invoke(name, payload, user, session, *, idempotency_token=None):
    if CAPABILITIES.get(name, (None, None, False))[2] and "filters" in payload:
        import json

        from backend.api.routes.assistant_read_steps import inspect

        data = json.loads(inspect(name, payload, None, user, session, None))
        return result_reply(name, data)
    parsed = validate(name, payload)
    handler, _ = contract(name)
    args = {key: getattr(parsed, key) for key in parsed.model_fields_set}
    for key, value in args.items():
        if key.endswith("_id") or key == "id":
            args[key] = UUID(value)
    if name in EDIT_MODELS:
        args["body"] = EDIT_MODELS[name].model_validate(
            args["body"].model_dump(mode="json", exclude_unset=True)
        )
    if name == "review_plan":
        from backend.api.routes.planning_review import ReviewQuery

        args["query"] = ReviewQuery(**args["query"].model_dump(mode="json"))
    if name == "commit_dump":
        from backend.api.routes.parity import DumpCommit

        args["body"] = DumpCommit(**args["body"].model_dump())
    if name == "set_sharing":
        from backend.api.routes.sharing import SharingSettings

        args["body"] = SharingSettings.model_validate(args["body"].model_dump())
    if name in {"create_todo", "create_daily_todos"}:
        if not idempotency_token:
            raise APIError(422, "INVALID_ACTION", "创建待办缺少确认操作标识")
        if name == "create_todo":
            args["response"] = Response()
        args["idempotency_key"] = uuid5(NAMESPACE_URL, str(idempotency_token))
    value = handler(user=user, session=session, **args)
    reply = value if name == "open_connections" else result_reply(name, value)
    if name in {"get_sharing", "set_sharing"}:
        from backend.api.routes.sharing import resource

        row = resource(session, user, args["kind"], args["resource_id"])
        kind = args["kind"]
        title = next(
            (
                getattr(row, key)
                for key in ("title", "name", "transcript", "source_text", "label")
                if hasattr(row, key)
            ),
            "共享事项",
        )
        url = (
            f"/todos/{row.id}"
            if kind == "todo"
            else f"/calendar/{row.id}/edit"
            if kind == "event"
            else f"/checklists/{row.id}"
            if kind == "checklist"
            else f"/meals/{row.id}"
            if kind == "meal"
            else "/voice-memos"
            if kind == "voice_memo"
            else "/daily-dump"
            if kind == "daily_dump"
            else "/documents"
            if kind == "material"
            else "/meals/settings"
            if kind in {"pantry", "preference"}
            else "/todos"
        )
        reply.items = [
            AssistantItem(
                id=row.id,
                title=(title or "共享事项")[:100],
                kind=kind,
                status="available",
                url=url,
            )
        ]
    return reply


def feature_reply(name, payload, store, user, session, thread_id):
    try:
        args, labels = prepare(name, payload, user, session)
        if CAPABILITIES[name][2]:
            return invoke(name, args, user, session)
        label = CAPABILITIES[name][1]
        detail = preview(args, labels)
        if len(detail) > 800:
            return AssistantReply(
                kind="clarify",
                message="本次修改内容过多，请分开操作，以便完整核对确认内容。",
            )
        return confirmation(
            store,
            user,
            thread_id,
            "feature",
            {"name": name, "args": args},
            f"确认{label}吗？\n{detail}",
            "确认执行",
        )
    except APIError as error:
        if error.status not in (404, 422):
            raise
        return AssistantReply(kind="clarify", message=error.message)


def prepare(name, payload, user, session):
    parsed = validate(name, payload)
    args, labels = bind_targets(
        name, parsed.model_dump(mode="json", exclude_unset=True), user, session
    )
    if name in EDIT_MODELS:
        args = complete_edit(name, args, user, session)
    return args, labels
