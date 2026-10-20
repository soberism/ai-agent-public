from typing import Literal
from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import select

from backend.api.hub_schemas import SearchMailDetail
from backend.core.security import DB, APIError, Principal
from backend.db.cross_system_models import EmailDelivery, MailImport
from backend.db.models import AssistantMessage, AssistantThread
from backend.db.parity_models import DailyDump
from backend.features.sharing.access import visible_condition

router = APIRouter()


@router.get("/search/{kind}/{mail_id}", response_model=SearchMailDetail)
def search_mail_detail(
    kind: Literal["mail", "email", "assistant_message", "daily_dump"],
    mail_id: UUID,
    user: Principal,
    session: DB,
):
    if kind in ("assistant_message", "daily_dump"):
        model = AssistantMessage if kind == "assistant_message" else DailyDump
        scope = (
            model.thread_id.in_(
                select(AssistantThread.id).where(AssistantThread.owner_id == user.id)
            )
            if kind == "assistant_message"
            else visible_condition(model, user.id)
        )
        row = session.scalar(select(model).where(model.id == mail_id, scope))
        if row is None:
            raise APIError(404, "SEARCH_NOT_FOUND", "内容不存在或无法访问")
        return SearchMailDetail(
            subject="AI 对话记录" if kind == "assistant_message" else "随手记录",
            body=row.content if kind == "assistant_message" else row.source_text,
            created_at=row.created_at,
        )
    model = MailImport if kind == "mail" else EmailDelivery
    row = session.scalar(
        select(model).where(model.id == mail_id, model.owner_id == user.id)
    )
    if row is None:
        raise APIError(404, "MAIL_NOT_FOUND", "邮件不存在或无法访问")
    return SearchMailDetail(
        subject=row.subject,
        body=row.body,
        sender=row.sender if kind == "mail" else None,
        created_at=row.created_at,
    )
