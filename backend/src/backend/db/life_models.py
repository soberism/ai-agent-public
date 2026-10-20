from __future__ import annotations

from datetime import date, datetime, time
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.models import Checklist, utcnow
from backend.db.session import Base


class LifePreference(Base):
    __tablename__ = "life_preferences"
    __table_args__ = (
        UniqueConstraint("owner_id", "label", "kind", name="uq_life_preference"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    label: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class PantryItem(Base):
    __tablename__ = "pantry_items"
    __table_args__ = (Index("ix_pantry_owner_name", "owner_id", "name", "id"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(100))
    quantity: Mapped[float]
    unit: Mapped[str] = mapped_column(String(20))
    expires_on: Mapped[date | None]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class MealPlan(Base):
    __tablename__ = "meal_plans"
    __table_args__ = (Index("ix_meal_owner_date", "owner_id", "meal_date", "id"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str | None] = mapped_column(String(15))
    schedule_text: Mapped[str | None] = mapped_column(Text)
    meal_date: Mapped[date | None]
    meal_type: Mapped[str | None] = mapped_column(String(20))
    dish: Mapped[str] = mapped_column(String(100))
    diners: Mapped[int | None]
    ingredients: Mapped[list] = mapped_column(JSON, default=list)
    preferences: Mapped[list] = mapped_column(JSON, default=list)
    shopping_list: Mapped[ShoppingList | None] = relationship()
    notes: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(20), default="draft")
    event_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("calendar_events.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class ShoppingList(Base):
    __tablename__ = "shopping_lists"
    __table_args__ = (Index("ix_shopping_owner_created", "owner_id", "created_at"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    meal_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("meal_plans.id", ondelete="SET NULL"), unique=True
    )
    title: Mapped[str] = mapped_column(String(100))
    items: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    checklist_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("checklists.id", ondelete="SET NULL")
    )
    unified_checklist_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("checklists.id", ondelete="SET NULL"), unique=True
    )
    unified_checklist: Mapped[Checklist | None] = relationship(
        foreign_keys=[unified_checklist_id]
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class MedicalAppointment(Base):
    __tablename__ = "medical_appointments"
    __table_args__ = (
        Index("ix_appointment_owner_date", "owner_id", "scheduled_date", "id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    patient_name: Mapped[str] = mapped_column(String(100))
    provider_name: Mapped[str] = mapped_column(String(150))
    service_type: Mapped[str] = mapped_column(String(100))
    scheduled_date: Mapped[date]
    scheduled_time: Mapped[time]
    notes: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(20), default="draft")
    event_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("calendar_events.id", ondelete="SET NULL")
    )
    todo_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("todos.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
