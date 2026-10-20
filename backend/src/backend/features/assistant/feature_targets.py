"""Resolve complete labels once, then bind confirmation to a concrete ID."""

from uuid import UUID

from sqlalchemy import select

from backend.core.security import APIError
from backend.db.household_models import Household, HouseholdParticipant
from backend.db.life_models import ShoppingList
from backend.db.models import AssistantMemory, Checklist, ChecklistItem
from backend.features.sharing.access import MODELS, visible_condition

PARAM_KINDS = {
    "id": "todo",
    "todo_id": "todo",
    "event_id": "event",
    "checklist_id": "checklist",
    "meal_id": "meal",
    "list_id": "shopping",
    "shopping_list_id": "shopping",
    "material_id": "material",
    "folder_id": "folder",
    "memo_id": "voice_memo",
    "dump_id": "daily_dump",
    "reminder_id": "reminder",
    "preference_id": "preference",
    "memory_id": "memory",
}


def identifier(value):
    try:
        return UUID(value)
    except ValueError, TypeError, AttributeError:
        return None


def resolve(key, value, args, name, user, session):
    ident = identifier(value)
    if key == "household_id":
        model, label = Household, Household.name
        filters = [
            Household.id.in_(
                select(HouseholdParticipant.household_id).where(
                    HouseholdParticipant.account_id == user.id,
                    HouseholdParticipant.status == "active",
                    HouseholdParticipant.role.in_(("owner", "admin", "member")),
                )
            )
        ]
    elif key == "member_id":
        model, label = HouseholdParticipant, HouseholdParticipant.display_name
        filters = [model.household_id == UUID(args["household_id"])]
    elif key == "invitation_id":
        model, label = HouseholdParticipant, HouseholdParticipant.email
        filters = [model.email == user.email, model.status == "pending"]
    elif key == "memory_id":
        model, label = AssistantMemory, AssistantMemory.content
        filters = [model.owner_id == user.id]
    elif key == "preference_id" and name == "delete_meal_preference":
        from backend.features.sharing.access import accessible

        meal = accessible(session, user, MODELS["meal"], UUID(args["meal_id"]))
        matches = [
            p for p in meal.preferences if p["id"] == value or p["label"] == value
        ]
        if len(matches) != 1:
            raise APIError(422, "AMBIGUOUS_TARGET", "请明确本餐偏好的完整内容")
        return matches[0]["id"], matches[0]["label"]
    else:
        kind = args.get("kind") if key == "resource_id" else PARAM_KINDS.get(key)
        model = (
            (MODELS["pantry"] if name.endswith("pantry") else ChecklistItem)
            if key == "item_id"
            else MODELS.get(kind)
        )
        if model is None:
            raise APIError(422, "INVALID_TARGET", "无法识别目标对象")
        label = next(
            (
                getattr(model, attr)
                for attr in ("title", "name", "label", "transcript", "source_text")
                if hasattr(model, attr)
            ),
            None,
        )
        filters = [visible_condition(model, user.id)]
        if model is ChecklistItem:
            if "checklist_id" in args:
                checklist_id = UUID(args["checklist_id"])
            elif "list_id" in args:
                shopping = session.scalar(
                    select(ShoppingList).where(
                        ShoppingList.id == UUID(args["list_id"]),
                        visible_condition(ShoppingList, user.id),
                    )
                )
                if shopping is None or shopping.unified_checklist_id is None:
                    raise APIError(422, "INVALID_TARGET", "购物清单不存在或无法访问")
                checklist_id = shopping.unified_checklist_id
            else:
                raise APIError(422, "INVALID_TARGET", "请先确认清单")
            filters.append(model.checklist_id == checklist_id)
    if ident:
        filters.append(model.id == ident)
    elif label is not None:
        filters.append(label == value)
    else:
        raise APIError(422, "INVALID_TARGET", "请先查询目标对象")
    rows = list(session.scalars(select(model).where(*filters).limit(2)))
    if not rows and ident and key in {"list_id", "shopping_list_id"}:
        # Shopping and its unified checklist have distinct IDs for the same list.
        rows = list(
            session.scalars(
                select(ShoppingList)
                .join(Checklist, ShoppingList.unified_checklist_id == Checklist.id)
                .where(
                    ShoppingList.unified_checklist_id == ident,
                    visible_condition(ShoppingList, user.id),
                    visible_condition(Checklist, user.id),
                )
                .limit(2)
            )
        )
    if not rows and key == "household_id" and name == "get_household" and not ident:
        rows = list(
            session.scalars(
                select(Household)
                .join(HouseholdParticipant)
                .where(
                    *filters,
                    HouseholdParticipant.display_name == value,
                    HouseholdParticipant.status == "active",
                    HouseholdParticipant.role.in_(("owner", "admin", "member")),
                )
                .distinct()
                .limit(2)
            )
        )
    if not rows and key == "checklist_id" and not ident:
        short_name = value.removesuffix("清单").strip()
        if short_name:
            rows = list(
                session.scalars(
                    select(model)
                    .where(
                        visible_condition(model, user.id),
                        model.title.startswith(short_name),
                    )
                    .limit(2)
                )
            )
    if len(rows) != 1:
        if key == "checklist_id" and not rows:
            raise APIError(
                422,
                "TARGET_NOT_FOUND",
                f"没有找到可访问的「{value}」。请先确认清单已创建。",
            )
        raise APIError(
            422, "AMBIGUOUS_TARGET", "目标不存在、无权访问或有重名，请先查询并明确对象"
        )
    return str(rows[0].id), str(
        getattr(rows[0], label.key)
    ) if label is not None else value


def bind_targets(name, payload, user, session):
    args = dict(payload)
    labels = {}
    # Resolve parents first so identical child titles cannot cross containers.
    for key in ("household_id", "checklist_id", "meal_id", "list_id"):
        if key in args:
            args[key], labels[key] = resolve(key, args[key], args, name, user, session)
    for key, value in list(args.items()):
        if (key.endswith("_id") or key == "id") and key not in {
            "household_id",
            "checklist_id",
            "meal_id",
            "list_id",
        }:
            args[key], labels[key] = resolve(key, value, args, name, user, session)
    if isinstance(args.get("body"), dict):
        body = dict(args["body"])
        display = dict(body)
        for key, value in list(body.items()):
            if key.endswith("_id") and value is not None:
                body[key], display[key] = resolve(
                    key, value, {**args, **body}, name, user, session
                )
        if body.get("member_ids"):
            from backend.api.routes.households import detail

            home = detail(UUID(body["household_id"]), user, session)
            members = {str(m.account_id): m.display_name for m in home.members}
            if not all(identifier in members for identifier in body["member_ids"]):
                raise APIError(422, "INVALID_TARGET", "请先查询并选择有效家庭成员")
            display["member_ids"] = [members[ident] for ident in body["member_ids"]]
        args["body"], labels["body"] = body, display
    return args, labels
