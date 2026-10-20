"""Accept requested changes, preserve other fields, validate the original contract."""

from copy import deepcopy
from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import ConfigDict, ValidationError, create_model

from backend.api.calendar_schemas import EventPatch
from backend.api.life_schemas import MealCreate
from backend.core.security import APIError

EDIT_MODELS = {"edit_event": EventPatch, "edit_meal": MealCreate}
EDIT_FIELDS = {
    "edit_event": {
        "title",
        "description",
        "location",
        "start_date",
        "start_time",
        "end_date",
        "end_time",
        "status",
    },
    "edit_meal": {
        "schedule_text",
        "date",
        "meal_type",
        "diners",
        "dish",
        "notes",
        "preferences",
    },
}


def partial_input(name):
    fields = {}
    for key, field in EDIT_MODELS[name].model_fields.items():
        if key not in EDIT_FIELDS[name]:
            continue
        copy = deepcopy(field)
        if copy.is_required():
            copy.default = None
        fields[key] = (field.annotation, copy)
    return create_model(
        f"Assistant_{name}", __config__=ConfigDict(extra="forbid"), **fields
    )


def complete_edit(name, args, user, session):
    from backend.api.routes.calendar_events import detail
    from backend.api.routes.life import get_meal

    changes = args["body"]
    if not changes:
        raise APIError(422, "INVALID_ACTION", "请提供需要修改的字段")
    source = (
        detail(UUID(args["event_id"]), user, session)
        if name == "edit_event"
        else get_meal(UUID(args["meal_id"]), user, session)
    ).model_dump(mode="json")
    model = EDIT_MODELS[name]
    body = {key: value for key, value in source.items() if key in model.model_fields}
    if name == "edit_meal":
        body["preferences"] = [
            {key: value for key, value in pref.items() if key != "id"}
            for pref in body["preferences"]
        ]
    body.update(changes)
    if (
        name == "edit_event"
        and {"start_date", "start_time"}.intersection(changes)
        and not {"end_date", "end_time"}.intersection(changes)
    ):
        zone = ZoneInfo(source["timezone"])
        start = datetime.fromisoformat(
            f"{body['start_date']}T{body['start_time']}"
        ).replace(tzinfo=zone)
        duration = datetime.fromisoformat(source["ends_at"]) - datetime.fromisoformat(
            source["starts_at"]
        )
        end = (start.astimezone(UTC) + duration).astimezone(zone)
        body["end_date"], body["end_time"] = (
            end.date().isoformat(),
            end.strftime("%H:%M"),
        )
    try:
        validated = model.model_validate(body).model_dump(
            mode="json", exclude_unset=True
        )
        args["body"] = {
            key: value for key, value in validated.items() if key in EDIT_FIELDS[name]
        }
    except ValidationError:
        raise APIError(
            422, "INVALID_ACTION", "修改后的标题、时间或餐食参数无效，请重新说明"
        ) from None
    return args
