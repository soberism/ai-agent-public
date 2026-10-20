import hashlib
import imaplib
from email import message_from_bytes, policy
from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import select

from backend.api.hub_schemas import (
    EmailDeliveryOut,
    EmailNotificationCreate,
    MailCapabilities,
    MailScanResult,
)
from backend.api.schemas import ERROR_RESPONSES
from backend.core.security import DB, APIError, Principal, settings
from backend.db.cross_system_models import EmailDelivery, MailImport
from backend.db.document_models import DocumentMaterial, DocumentReviewItem
from backend.db.parity_models import EmailPreference
from backend.features.auth.delivery import deliver_record
from backend.features.documents.extraction import extract_candidates

router = APIRouter(
    prefix="/api/mail", tags=["邮箱与邮件通知"], responses=ERROR_RESPONSES
)


def configured(*values):
    return all(values)


def delivery_out(row):
    return EmailDeliveryOut.model_validate(row, from_attributes=True)


@router.get("/capabilities", response_model=MailCapabilities)
def capabilities():
    return MailCapabilities(
        imap=configured(
            settings.imap_owner_id,
            settings.imap_host,
            settings.imap_username,
            settings.imap_password.get_secret_value(),
        ),
        smtp=configured(
            settings.smtp_host,
            settings.smtp_username,
            settings.smtp_password.get_secret_value(),
            settings.smtp_from,
        ),
    )


def plain_body(message):
    parts = message.walk() if message.is_multipart() else [message]
    for part in parts:
        if (
            part.get_content_type() == "text/plain"
            and part.get_content_disposition() != "attachment"
        ):
            try:
                return part.get_content()[:20000]
            except LookupError, UnicodeError:
                continue
    return ""


@router.post("/scan", response_model=MailScanResult)
def scan(user: Principal, session: DB):
    if not capabilities().imap:
        raise APIError(503, "IMAP_UNAVAILABLE", "邮箱扫描尚未配置")
    if not settings.imap_owner_id or settings.imap_owner_id != str(user.id):
        raise APIError(403, "IMAP_FORBIDDEN", "此邮箱连接未授权给当前账号")
    imported = duplicates = 0
    try:
        with imaplib.IMAP4_SSL(
            settings.imap_host, settings.imap_port, timeout=15
        ) as client:
            client.login(
                settings.imap_username, settings.imap_password.get_secret_value()
            )
            if client.select(settings.imap_folder, readonly=True)[0] != "OK":
                raise imaplib.IMAP4.error("folder unavailable")
            status, data = client.search(None, "ALL")
            if status != "OK":
                raise imaplib.IMAP4.error("search failed")
            for message_number in data[0].split()[-20:]:
                status, fetched = client.fetch(message_number, "(RFC822)")
                if status != "OK" or not fetched or not isinstance(fetched[0], tuple):
                    continue
                raw = fetched[0][1]
                message = message_from_bytes(raw, policy=policy.default)
                message_id = str(
                    message.get("Message-ID") or hashlib.sha256(raw).hexdigest()
                )[:500]
                if session.scalar(
                    select(MailImport.id).where(
                        MailImport.owner_id == user.id,
                        MailImport.message_id == message_id,
                    )
                ):
                    duplicates += 1
                    continue
                body = plain_body(message)
                digest = hashlib.sha256(raw).hexdigest()
                material = DocumentMaterial(
                    owner_id=user.id,
                    name=str(message.get("Subject") or "无主题邮件")[:255],
                    kind="email",
                    media_type="message/rfc822",
                    size=len(raw),
                    content_hash=digest,
                    content=raw,
                    extracted_text=body,
                    status="ready" if body else "partial",
                    error_message=None if body else "邮件没有可读取的纯文本正文",
                )
                session.add(material)
                session.flush()
                session.add(
                    MailImport(
                        owner_id=user.id,
                        message_id=message_id,
                        subject=material.name,
                        sender=str(message.get("From") or "")[:500],
                        body=body,
                        material_id=material.id,
                    )
                )
                session.add_all(
                    [
                        DocumentReviewItem(
                            owner_id=user.id, material_id=material.id, **candidate
                        )
                        for candidate in extract_candidates(body, material.name)
                    ]
                )
                imported += 1
        session.commit()
        return MailScanResult(imported=imported, duplicates=duplicates)
    except imaplib.IMAP4.error, OSError:
        session.rollback()
        raise APIError(
            503, "IMAP_FAILED", "邮箱连接或扫描失败，请检查配置后重试"
        ) from None


def deliver(row, email, session):
    preference = session.get(EmailPreference, row.owner_id)
    if preference:
        if not preference.notifications_enabled:
            raise APIError(409, "EMAIL_DISABLED", "邮件通知已关闭")
        email = ", ".join(preference.recipient_emails) or email
    return delivery_out(deliver_record(row, email, session))


@router.get("/notifications", response_model=list[EmailDeliveryOut])
def deliveries(user: Principal, session: DB):
    rows = session.scalars(
        select(EmailDelivery)
        .where(EmailDelivery.owner_id == user.id)
        .order_by(EmailDelivery.created_at.desc())
        .limit(30)
    )
    return [delivery_out(row) for row in rows]


@router.post("/notifications", response_model=EmailDeliveryOut, status_code=201)
def notify(body: EmailNotificationCreate, user: Principal, session: DB):
    preference = session.get(EmailPreference, user.id)
    if preference and not preference.notifications_enabled:
        raise APIError(409, "EMAIL_DISABLED", "邮件通知已关闭")
    if not capabilities().smtp:
        raise APIError(503, "SMTP_UNAVAILABLE", "邮件通知尚未配置")
    row = EmailDelivery(
        owner_id=user.id, kind="manual", subject=body.subject, body=body.body
    )
    session.add(row)
    session.commit()
    return deliver(row, user.email, session)


@router.post("/notifications/{delivery_id}/retry", response_model=EmailDeliveryOut)
def retry(delivery_id: UUID, user: Principal, session: DB):
    row = session.scalar(
        select(EmailDelivery)
        .where(
            EmailDelivery.id == delivery_id,
            EmailDelivery.owner_id == user.id,
            EmailDelivery.status == "failed",
        )
        .with_for_update()
    )
    if row is None:
        raise APIError(404, "EMAIL_DELIVERY_NOT_FOUND", "失败邮件不存在或已处理")
    return deliver(row, user.email, session)
