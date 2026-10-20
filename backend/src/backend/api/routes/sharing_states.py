from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import select

from backend.core.security import DB, APIError, Principal
from backend.db.models import Reminder
from backend.db.sharing_models import ItemSharing
from backend.features.sharing.access import RESOURCE_MODELS, visible_condition

router = APIRouter()


@router.get("/states")
def states(
    resources: Annotated[str, Query(max_length=16000)], user: Principal, session: DB
):
    groups = {}
    try:
        keys = resources.split(",")
        if len(keys) > 200:
            raise ValueError
        for key in keys:
            kind, identifier = key.split(":")
            if kind not in RESOURCE_MODELS:
                raise ValueError
            groups.setdefault(kind, set()).add(UUID(identifier))
    except ValueError:
        raise APIError(422, "INVALID_SHARING", "可见范围查询参数无效") from None
    result = {}
    editable = []
    for kind, ids in groups.items():
        model = RESOURCE_MODELS[kind]
        rows = session.scalars(
            select(model).where(model.id.in_(ids), visible_condition(model, user.id))
        ).all()
        references = {
            row.id: (("todo", row.todo_id) if row.todo_id else ("event", row.event_id))
            if model is Reminder
            else (kind, row.id)
            for row in rows
        }
        policies = {}
        for source_kind in {value[0] for value in references.values()}:
            source_ids = [
                identifier
                for source, identifier in references.values()
                if source == source_kind
            ]
            for policy in session.scalars(
                select(ItemSharing).where(
                    ItemSharing.kind == source_kind,
                    ItemSharing.resource_id.in_(source_ids),
                )
            ):
                policies[(source_kind, policy.resource_id)] = policy.scope
        for row in rows:
            reference = references[row.id]
            source = (
                session.get(RESOURCE_MODELS[reference[0]], reference[1])
                if model is Reminder
                else row
            )
            if kind != "folder" and source and source.owner_id == user.id:
                editable.append(f"{kind}:{row.id}")
        for identifier, reference in references.items():
            scope = policies.get(reference, "private")
            result[f"{kind}:{identifier}"] = (
                scope if scope in ("private", "household", "members") else "private"
            )
    return {"states": result, "editable": editable}
