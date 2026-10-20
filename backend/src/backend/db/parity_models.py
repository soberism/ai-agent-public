from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.models import utcnow
from backend.db.session import Base


class EmailPreference(Base):
    __tablename__ = "email_preferences"
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    reminder_enabled: Mapped[bool] = mapped_column(default=True)
    reminder_minutes: Mapped[int] = mapped_column(default=30)
    notifications_enabled: Mapped[bool] = mapped_column(default=True)
    recipient_emails: Mapped[list] = mapped_column(JSON, default=list)
    daily_enabled: Mapped[bool] = mapped_column(default=False)
    daily_time: Mapped[str] = mapped_column(String(5), default="08:00")
    weekly_enabled: Mapped[bool] = mapped_column(default=False)
    weekly_day: Mapped[int] = mapped_column(default=0)
    weekly_time: Mapped[str] = mapped_column(String(5), default="20:00")
    quiet_start: Mapped[str] = mapped_column(String(5), default="22:00")
    quiet_end: Mapped[str] = mapped_column(String(5), default="07:00")
    last_daily_date: Mapped[str | None] = mapped_column(String(10))
    last_weekly_key: Mapped[str | None] = mapped_column(String(10))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class VoiceSession(Base):
    __tablename__ = "voice_sessions"
    __table_args__ = (
        Index("ix_voice_session_owner_created", "owner_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(20), default="active")
    turns: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[str | None] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DailyDump(Base):
    __tablename__ = "daily_dumps"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    source_text: Mapped[str] = mapped_column(String(4000))
    candidates: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class HouseholdAudit(Base):
    __tablename__ = "household_audits"
    __table_args__ = (
        Index("ix_household_audit_home_created", "household_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE")
    )
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(50))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class ChecklistShare(Base):
    __tablename__ = "checklist_shares"
    __table_args__ = (
        UniqueConstraint("checklist_id", "household_id", name="uq_checklist_household"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    checklist_id: Mapped[UUID] = mapped_column(
        ForeignKey("checklists.id", ondelete="CASCADE")
    )
    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
