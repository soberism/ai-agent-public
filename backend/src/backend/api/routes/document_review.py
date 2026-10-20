import hashlib
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query
from sqlalchemy import select

from backend.api.document_schemas import ReviewList, ReviewOut, ReviewPatch
from backend.api.schemas import ERROR_RESPONSES
from backend.core.security import DB, APIError, Principal
from backend.db.document_models import DocumentMaterial, DocumentReviewItem
from backend.db.models import CalendarEvent, Todo, utcnow
from backend.features.sharing.access import (
    accessible,
    inherit_sharing,
    visible_condition,
)

router = APIRouter(
    prefix="/api/documents/review-items",
    tags=["文档审核"],
    responses=ERROR_RESPONSES,
)


def owned(session, user, item_id, lock=False):
    statement = select(DocumentReviewItem).where(
        DocumentReviewItem.id == item_id, visible_condition(DocumentReviewItem, user.id)
    )
    row = session.scalar(statement.with_for_update() if lock else statement)
    if row is None:
        raise APIError(404, "REVIEW_ITEM_NOT_FOUND", "审核项不存在或无法访问")
    return row


def output(session, row):
    material = session.get(DocumentMaterial, row.material_id)
    url = None
    if row.status == "accepted" and row.target_id:
        url = (
            f"/todos/{row.target_id}"
            if row.target_type == "todo"
            else f"/calendar/{row.target_id}/edit"
        )
    return ReviewOut(
        id=row.id,
        material_id=row.material_id,
        material_name=material.name,
        target_type=row.target_type,
        title=row.title,
        evidence=row.evidence,
        confidence=row.confidence,
        status=row.status,
        target_url=url,
        change_kind=row.change_kind,
        previous_value=row.previous_value,
    )


@router.get("", response_model=ReviewList)
def listing(
    user: Principal,
    session: DB,
    status: Annotated[
        str, Query(pattern="^(pending|accepted|ignored|failed)$")
    ] = "pending",
):
    rows = session.scalars(
        select(DocumentReviewItem)
        .where(
            visible_condition(DocumentReviewItem, user.id),
            DocumentReviewItem.status == status,
        )
        .order_by(DocumentReviewItem.created_at, DocumentReviewItem.id)
    )
    return ReviewList(items=[output(session, row) for row in rows])


@router.patch("/{item_id}", response_model=ReviewOut)
def update(item_id: UUID, body: ReviewPatch, user: Principal, session: DB):
    row = owned(session, user, item_id, lock=True)
    if row.status != "pending":
        raise APIError(409, "REVIEW_ALREADY_RESOLVED", "审核项已处理，不能再修改")
    row.title = body.title.strip()
    session.commit()
    return output(session, row)


@router.post("/{item_id}/accept", response_model=ReviewOut)
def accept(item_id: UUID, user: Principal, session: DB):
    row = owned(session, user, item_id, lock=True)
    if row.status == "accepted":
        return output(session, row)
    if row.status != "pending" or not row.proposed_date:
        raise APIError(409, "REVIEW_NOT_ACCEPTABLE", "该审核项不能接受")
    if len(row.title.strip()) > 15:
        raise APIError(422, "TITLE_INVALID", "标题最多15个字符，请缩短后再接受")
    proposed = date.fromisoformat(row.proposed_date)
    if row.target_id and row.change_kind in ("changed", "cancelled"):
        target = accessible(
            session,
            user,
            CalendarEvent if row.target_type == "event" else Todo,
            row.target_id,
            lock=True,
        )
        if row.change_kind == "cancelled":
            target.status = "cancelled" if row.target_type == "event" else "completed"
        elif row.target_type == "event":
            zone = ZoneInfo(user.timezone)
            starts_at = datetime.combine(proposed, time(9), zone).astimezone(UTC)
            target.starts_at, target.ends_at = starts_at, starts_at + timedelta(hours=1)
        else:
            target.due_date = proposed
        row.status, row.accepted_at = "accepted", utcnow()
        session.commit()
        return output(session, row)
    if row.target_type == "todo":
        source = f"document:{row.material_id}:{row.id}"
        target = Todo(
            owner_id=row.owner_id,
            title=row.title,
            description=f"来源材料：{session.get(DocumentMaterial, row.material_id).name}",
            due_date=proposed,
            due_time=None,
            timezone=user.timezone,
            due_at=None,
            status="ongoing",
            completed_at=None,
            create_key=uuid4(),
            create_fingerprint=hashlib.sha256(source.encode()).hexdigest(),
        )
    else:
        zone = ZoneInfo(user.timezone)
        starts_at = datetime.combine(proposed, time(9), zone).astimezone(UTC)
        target = CalendarEvent(
            owner_id=row.owner_id,
            todo_id=None,
            series_id=None,
            title=row.title,
            description=f"来源材料：{session.get(DocumentMaterial, row.material_id).name}",
            location=None,
            source="document",
            status="scheduled",
            timezone=user.timezone,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=1),
        )
    session.add(target)
    session.flush()
    inherit_sharing(session, "material", row.material_id, row.target_type, target.id)
    row.status = "accepted"
    row.target_id = target.id
    row.accepted_at = utcnow()
    session.commit()
    return output(session, row)


@router.post("/{item_id}/ignore", response_model=ReviewOut)
def ignore(item_id: UUID, user: Principal, session: DB):
    row = owned(session, user, item_id, lock=True)
    if row.status == "accepted":
        raise APIError(409, "REVIEW_ALREADY_ACCEPTED", "已接受的审核项不能忽略")
    row.status = "ignored"
    session.commit()
    return output(session, row)
