from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import select

from backend.api.household_schemas import NotificationList, NotificationOut
from backend.api.schemas import ERROR_RESPONSES
from backend.core.security import DB, APIError, Principal
from backend.db.household_models import Notification
from backend.db.models import utcnow

router = APIRouter(
    prefix="/api/notifications", tags=["站内通知"], responses=ERROR_RESPONSES
)


def output(row):
    return NotificationOut(
        id=row.id,
        type=row.kind,
        title=row.title,
        message=row.message,
        read=row.read_at is not None,
        created_at=row.created_at,
        invitation_id=row.invitation_id,
    )


@router.get("", response_model=NotificationList)
def listing(user: Principal, session: DB):
    rows = session.scalars(
        select(Notification)
        .where(Notification.recipient_id == user.id)
        .order_by(Notification.created_at.desc(), Notification.id)
    )
    return NotificationList(items=[output(row) for row in rows])


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_read(notification_id: UUID, user: Principal, session: DB):
    row = session.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.recipient_id == user.id,
        )
    )
    if row is None:
        raise APIError(404, "NOTIFICATION_NOT_FOUND", "通知不存在或无法访问")
    row.read_at = row.read_at or utcnow()
    session.commit()
    return output(row)
