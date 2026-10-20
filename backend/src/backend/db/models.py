from datetime import UTC, date, datetime, time
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.session import Base


def utcnow():
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    nickname: Mapped[str | None] = mapped_column(String(30))
    password_hash: Mapped[str]
    active: Mapped[bool] = mapped_column(default=True, server_default="true")
    auth_version: Mapped[int] = mapped_column(default=0, server_default="0")
    timezone: Mapped[str] = mapped_column(default="Asia/Shanghai")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class Todo(Base):
    __tablename__ = "todos"
    __table_args__ = (
        UniqueConstraint("owner_id", "create_key", name="uq_todo_owner_key"),
        CheckConstraint("status IN ('ongoing','completed')", name="ck_todo_status"),
        CheckConstraint(
            "(status='ongoing' AND completed_at IS NULL) OR (status='completed' AND completed_at IS NOT NULL)",
            name="ck_todo_completion",
        ),
        CheckConstraint(
            "(due_time IS NULL AND due_at IS NULL) OR (due_date IS NOT NULL AND due_time IS NOT NULL AND due_at IS NOT NULL)",
            name="ck_todo_due",
        ),
        CheckConstraint("length(title) BETWEEN 1 AND 100", name="ck_todo_title"),
        CheckConstraint(
            "description IS NULL OR length(description) <= 2000",
            name="ck_todo_description",
        ),
        Index(
            "ix_todo_owner_status_due",
            "owner_id",
            "status",
            "due_date",
            "due_time",
            "created_at",
            "id",
        ),
        Index("ix_todo_owner_completed", "owner_id", "status", "completed_at", "id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    household_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("households.id", ondelete="SET NULL")
    )
    assignee_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    assignment_status: Mapped[str] = mapped_column(String(20), default="personal")
    assignment_note: Mapped[str | None] = mapped_column(String(500))
    title: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None]
    due_date: Mapped[date | None]
    due_time: Mapped[time | None]
    timezone: Mapped[str] = mapped_column(default="Asia/Shanghai")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(default="ongoing")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    create_key: Mapped[UUID]
    create_fingerprint: Mapped[str] = mapped_column(String(64))


class CalendarEvent(Base):
    __tablename__ = "calendar_events"
    __table_args__ = (
        CheckConstraint("length(title) BETWEEN 1 AND 100", name="ck_event_title"),
        CheckConstraint("ends_at > starts_at", name="ck_event_time_range"),
        CheckConstraint("status IN ('scheduled','cancelled')", name="ck_event_status"),
        CheckConstraint(
            "description IS NULL OR length(description) <= 2000",
            name="ck_event_description",
        ),
        CheckConstraint(
            "location IS NULL OR length(location) <= 200",
            name="ck_event_location",
        ),
        Index("ix_event_owner_time", "owner_id", "starts_at", "ends_at", "id"),
        Index("ix_calendar_event_series", "owner_id", "series_id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    household_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("households.id", ondelete="SET NULL")
    )
    todo_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("todos.id", ondelete="SET NULL")
    )
    series_id: Mapped[UUID | None]
    title: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None]
    location: Mapped[str | None] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(20), default="app")
    status: Mapped[str] = mapped_column(String(9), default="scheduled")
    timezone: Mapped[str] = mapped_column(String(64))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class Checklist(Base):
    __tablename__ = "checklists"
    __table_args__ = (
        CheckConstraint("length(title) BETWEEN 1 AND 100", name="ck_checklist_title"),
        Index("ix_checklist_owner_updated", "owner_id", "updated_at", "id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(100))
    pinned: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class ChecklistItem(Base):
    __tablename__ = "checklist_items"
    __table_args__ = (
        CheckConstraint(
            "length(title) BETWEEN 1 AND 200", name="ck_checklist_item_title"
        ),
        Index("ix_checklist_item_order", "checklist_id", "position", "id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    checklist_id: Mapped[UUID] = mapped_column(
        ForeignKey("checklists.id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(String(200))
    completed: Mapped[bool] = mapped_column(default=False)
    position: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class Reminder(Base):
    __tablename__ = "reminders"
    __table_args__ = (
        CheckConstraint(
            "(todo_id IS NOT NULL)::int + (event_id IS NOT NULL)::int = 1",
            name="ck_reminder_one_subject",
        ),
        CheckConstraint(
            "status IN ('scheduled','disabled')", name="ck_reminder_status"
        ),
        Index("ix_reminder_owner_time", "owner_id", "remind_at", "id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    todo_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("todos.id", ondelete="CASCADE")
    )
    event_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("calendar_events.id", ondelete="CASCADE")
    )
    remind_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(9), default="scheduled")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class AssistantThread(Base):
    __tablename__ = "assistant_threads"
    __table_args__ = (
        Index("ix_assistant_thread_owner_updated", "owner_id", "updated_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class AssistantMessage(Base):
    __tablename__ = "assistant_messages"
    __table_args__ = (
        CheckConstraint(
            "role IN ('user','assistant')", name="ck_assistant_message_role"
        ),
        Index("ix_assistant_message_thread_created", "thread_id", "created_at", "id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    thread_id: Mapped[UUID] = mapped_column(
        ForeignKey("assistant_threads.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String(9))
    content: Mapped[str] = mapped_column(String(1000))
    kind: Mapped[str | None] = mapped_column(String(10))
    items: Mapped[list | None] = mapped_column(JSON)
    suggestions: Mapped[list | None] = mapped_column(JSON)
    context_refs: Mapped[list | None] = mapped_column(JSON)
    action_label: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


# Register feature tables in shared SQLAlchemy metadata without growing this core file.
from backend.db import (  # noqa: F401
    agent_models,
    cross_system_models,
    document_models,
    household_models,
    life_models,
    parity_models,
    sharing_models,
)


class AssistantProfile(Base):
    __tablename__ = "assistant_profiles"
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    custom_instructions: Mapped[str] = mapped_column(String(2000), default="")
    memory_enabled: Mapped[bool] = mapped_column(default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class AssistantMemory(Base):
    __tablename__ = "assistant_memories"
    __table_args__ = (
        CheckConstraint("source IN ('user','assistant')", name="ck_memory_source"),
        CheckConstraint("length(content) BETWEEN 1 AND 500", name="ck_memory_content"),
        Index("ix_memory_owner_updated", "owner_id", "updated_at", "id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    content: Mapped[str] = mapped_column(String(500))
    source: Mapped[str] = mapped_column(String(20), default="user")
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
