"""先持久化发送状态；不自动重发结果不确定的邮件。"""

import smtplib
from uuid import UUID

from sqlalchemy import update

from backend.core.security import APIError
from backend.db.cross_system_models import EmailDelivery
from backend.db.models import Reminder, utcnow
from backend.db.parity_models import EmailPreference
from backend.features.auth.mail import send_message


def deliver_record(row, email, session):
    claimed = session.execute(
        update(EmailDelivery)
        .where(
            EmailDelivery.id == row.id, EmailDelivery.status.in_(["pending", "failed"])
        )
        .values(status="sending", error_message=None)
        .returning(EmailDelivery.id)
    ).scalar_one_or_none()
    if claimed is None:
        session.rollback()
        raise APIError(
            409, "EMAIL_ALREADY_PROCESSING", "邮件正在发送或已处理，请刷新记录"
        )
    session.commit()
    try:
        send_message(email, row.subject, row.body)
    except (
        smtplib.SMTPAuthenticationError,
        smtplib.SMTPRecipientsRefused,
        smtplib.SMTPSenderRefused,
        smtplib.SMTPDataError,
    ):
        row.status = "failed"
        row.error_message = "邮件服务拒绝发送，请检查配置后重试"
    except OSError, smtplib.SMTPException:
        row.status = "unknown"
        row.error_message = "发送结果无法确认，请先核对收件箱，勿重复发送"
    else:
        row.status, row.sent_at = "sent", utcnow()
        key = row.dedupe_key or ""
        if key.startswith("reminder:"):
            reminder = session.get(Reminder, UUID(key.split(":", 1)[1]))
            if reminder and reminder.owner_id == row.owner_id:
                reminder.status = "disabled"
        elif key.startswith(("daily:", "weekly:")):
            preference = session.get(EmailPreference, row.owner_id)
            if preference:
                field = (
                    "last_daily_date" if key.startswith("daily:") else "last_weekly_key"
                )
                setattr(preference, field, key.split(":", 1)[1])
    session.commit()
    return row
