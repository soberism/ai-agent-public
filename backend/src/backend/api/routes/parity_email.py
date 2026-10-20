from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from pydantic import BaseModel, EmailStr, Field, model_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from backend.api.schemas import ERROR_RESPONSES
from backend.core.security import DB, APIError, Principal
from backend.core.security import settings as app_settings
from backend.db.cross_system_models import EmailDelivery
from backend.db.models import CalendarEvent, Todo, utcnow
from backend.db.parity_models import EmailPreference
from backend.features.auth.delivery import deliver_record
from backend.features.auth.email_summary import summary_body
from backend.features.sharing.access import visible_condition

router = APIRouter(
    prefix="/api/workflows", tags=["完整工作流"], responses=ERROR_RESPONSES
)


class EmailSettings(BaseModel):
    notifications_enabled: bool = True
    recipient_emails: list[EmailStr] = Field(default_factory=list, max_length=3)
    reminder_enabled: bool = True
    reminder_minutes: int = Field(30, ge=0, le=10080)
    daily_enabled: bool = False
    daily_time: str = Field("08:00", pattern=r"^\d{2}:\d{2}$")
    weekly_enabled: bool = False
    weekly_day: int = Field(0, ge=0, le=6)
    weekly_time: str = Field("20:00", pattern=r"^\d{2}:\d{2}$")
    quiet_start: str = Field("22:00", pattern=r"^\d{2}:\d{2}$")
    quiet_end: str = Field("07:00", pattern=r"^\d{2}:\d{2}$")


class EmailDispatch(BaseModel):
    manual: bool = False
    request_id: UUID | None = None

    @model_validator(mode="after")
    def require_manual_id(self):
        if self.manual and self.request_id is None:
            raise ValueError("手动发送必须提供请求 ID")
        return self


def preference(session, user):
    row = session.get(EmailPreference, user.id)
    if row is None:
        row = EmailPreference(owner_id=user.id)
        session.add(row)
        session.commit()
    return row


@router.get("/email-settings")
def get_email_settings(user: Principal, session: DB):
    value = EmailSettings.model_validate(
        preference(session, user), from_attributes=True
    )
    value.recipient_emails = [user.email] + [
        email for email in value.recipient_emails if email != user.email
    ]
    return value


@router.put("/email-settings")
def put_email_settings(body: EmailSettings, user: Principal, session: DB):
    body.recipient_emails = list(dict.fromkeys([user.email, *body.recipient_emails]))
    if len(body.recipient_emails) > 3:
        raise APIError(422, "VALIDATION_ERROR", "最多支持 3 个收件人，包含注册邮箱")
    row = preference(session, user)
    for key, value in body.model_dump().items():
        setattr(row, key, value)
    row.updated_at = utcnow()
    session.commit()
    return body


def in_quiet(value, start, end):
    current = value.strftime("%H:%M")
    return start <= current < end if start < end else current >= start or current < end


@router.post("/email-dispatch")
def dispatch_email(body: EmailDispatch, user: Principal, session: DB):
    settings = preference(session, user)
    now = datetime.now(ZoneInfo(user.timezone))
    if not settings.notifications_enabled:
        if body.manual:
            raise APIError(409, "EMAIL_DISABLED", "邮件通知已关闭")
        return {"sent": 0, "failed": 0, "unknown": 0, "deferred": False}
    if not body.manual and in_quiet(now, settings.quiet_start, settings.quiet_end):
        return {"sent": 0, "failed": 0, "unknown": 0, "deferred": True}
    if not all(
        (
            app_settings.smtp_host,
            app_settings.smtp_username,
            app_settings.smtp_password.get_secret_value(),
            app_settings.smtp_from,
        )
    ):
        raise APIError(503, "SMTP_UNAVAILABLE", "邮件通知尚未配置")
    payloads = []
    if settings.reminder_enabled and not body.manual:
        lead = timedelta(minutes=settings.reminder_minutes)
        current = now.astimezone(UTC)
        # A one-day grace window allows quiet-hour deferral without sending old backlog.
        earliest = max(current - timedelta(days=1), settings.updated_at.astimezone(UTC))
        todos = session.scalars(
            select(Todo).where(
                visible_condition(Todo, user.id),
                Todo.status == "ongoing",
                Todo.due_at.is_not(None),
                Todo.due_at >= earliest,
                Todo.due_at <= current + lead,
            )
        )
        for todo in todos:
            payloads.append(
                (
                    f"todo:{todo.id}:{int(todo.due_at.timestamp())}",
                    "reminder",
                    f"事项提醒：{todo.title}",
                    "\n".join(
                        [
                            f"待办：{todo.title}",
                            f"截止时间：{todo.due_at.astimezone(ZoneInfo(todo.timezone)):%Y-%m-%d %H:%M}",
                            "状态：进行中",
                            f"内容：{todo.description or '无'}",
                            f"查看事项：{app_settings.app_url.rstrip('/')}/todos/{todo.id}/edit",
                        ]
                    ),
                )
            )
        events = session.scalars(
            select(CalendarEvent).where(
                visible_condition(CalendarEvent, user.id),
                CalendarEvent.status == "scheduled",
                CalendarEvent.starts_at >= earliest,
                CalendarEvent.starts_at <= current + lead,
            )
        )
        for event in events:
            zone = ZoneInfo(event.timezone)
            payloads.append(
                (
                    f"event:{event.id}:{int(event.starts_at.timestamp())}",
                    "reminder",
                    f"事项提醒：{event.title}",
                    "\n".join(
                        [
                            f"日程：{event.title}",
                            f"开始：{event.starts_at.astimezone(zone):%Y-%m-%d %H:%M}",
                            f"结束：{event.ends_at.astimezone(zone):%Y-%m-%d %H:%M}",
                            f"地点：{event.location or '无'}",
                            f"内容：{event.description or '无'}",
                            f"查看事项：{app_settings.app_url.rstrip('/')}/calendar/{event.id}/edit",
                        ]
                    ),
                )
            )
    today = now.date().isoformat()
    week = f"{now.isocalendar().year}-{now.isocalendar().week:02d}"
    if settings.daily_enabled and (
        body.manual
        or (
            settings.last_daily_date != today
            and now.strftime("%H:%M") >= settings.daily_time
        )
    ):
        todos = session.scalars(
            select(Todo).where(
                visible_condition(Todo, user.id),
                Todo.status == "ongoing",
                Todo.due_date == now.date(),
            )
        )
        payloads.append(
            (
                f"daily:{today}",
                "daily",
                "今日待办摘要",
                summary_body(todos, now.date(), now.date(), user.timezone),
            )
        )
    if settings.weekly_enabled and (
        body.manual
        or (
            settings.last_weekly_key != week
            and now.weekday() == settings.weekly_day
            and now.strftime("%H:%M") >= settings.weekly_time
        )
    ):
        end = now.date() + timedelta(days=7)
        todos = session.scalars(
            select(Todo).where(
                visible_condition(Todo, user.id),
                Todo.status == "ongoing",
                Todo.due_date >= now.date(),
                Todo.due_date < end,
            )
        )
        payloads.append(
            (
                f"weekly:{week}",
                "weekly",
                "未来七天待办摘要",
                summary_body(todos, now.date(), end - timedelta(days=1), user.timezone),
            )
        )
    if body.manual:
        payloads = [
            (f"manual:{body.request_id}:{kind}", kind, subject, content)
            for _, kind, subject, content in payloads
        ]
    for key, kind, subject, content in payloads:
        session.execute(
            insert(EmailDelivery)
            .values(
                owner_id=user.id,
                dedupe_key=key,
                kind=kind,
                subject=subject,
                body=content,
            )
            .on_conflict_do_nothing(constraint="uq_email_delivery_dedupe")
        )
    session.commit()
    rows = list(
        session.scalars(
            select(EmailDelivery)
            .where(
                EmailDelivery.owner_id == user.id,
                EmailDelivery.status == "pending",
                EmailDelivery.dedupe_key.in_([item[0] for item in payloads]),
            )
            .limit(30)
        )
    )
    counts = {"sent": 0, "failed": 0, "unknown": 0}
    for row in rows:
        try:
            deliver_record(
                row, ", ".join(settings.recipient_emails) or user.email, session
            )
        except APIError as exc:
            if exc.status == 409:
                continue
            raise
        counts[row.status] += 1
    return {**counts, "deferred": False}
