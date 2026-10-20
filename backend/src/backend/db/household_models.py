from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.models import utcnow
from backend.db.session import Base


class Household(Base):
    __tablename__ = "households"
    __table_args__ = (Index("ix_household_owner", "owner_id", "created_at"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class HouseholdParticipant(Base):
    __tablename__ = "household_participants"
    __table_args__ = (
        UniqueConstraint("household_id", "email", name="uq_household_email"),
        Index("ix_participant_account_status", "account_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE")
    )
    account_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    display_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254))
    role: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    permissions: Mapped[list] = mapped_column(JSON, default=list)
    invited_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class HouseholdProfile(Base):
    __tablename__ = "household_profiles"
    __table_args__ = (Index("ix_profile_household", "household_id", "created_at"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(100))
    relationship: Mapped[str] = mapped_column(String(50))
    birth_date: Mapped[date | None]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class Pet(Base):
    __tablename__ = "pets"
    __table_args__ = (Index("ix_pet_household", "household_id", "created_at"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(100))
    species: Mapped[str] = mapped_column(String(50))
    breed: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class ContactGroup(Base):
    __tablename__ = "contact_groups"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_contact_group_owner_name"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (Index("ix_contact_owner_name", "owner_id", "name", "id"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(100))
    relationship: Mapped[str] = mapped_column(String(50), default="其他")
    phone: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(254))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class ContactGroupMembership(Base):
    __tablename__ = "contact_group_memberships"
    __table_args__ = (
        UniqueConstraint("group_id", "contact_id", name="uq_group_contact"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    group_id: Mapped[UUID] = mapped_column(
        ForeignKey("contact_groups.id", ondelete="CASCADE")
    )
    contact_id: Mapped[UUID] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE")
    )


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notification_recipient", "recipient_id", "created_at"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    recipient_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    household_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE")
    )
    invitation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("household_participants.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(100))
    message: Mapped[str] = mapped_column(String(500))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
