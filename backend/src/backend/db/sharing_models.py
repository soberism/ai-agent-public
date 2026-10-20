from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.session import Base


class ItemSharing(Base):
    __tablename__ = "item_sharing"
    __table_args__ = (
        CheckConstraint(
            "scope IN ('private','household','members')",
            name="ck_item_sharing_scope",
        ),
    )
    kind: Mapped[str] = mapped_column(String(30), primary_key=True)
    resource_id: Mapped[UUID] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(20))
    household_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE")
    )


class ItemSharingMember(Base):
    __tablename__ = "item_sharing_members"
    __table_args__ = (
        ForeignKeyConstraint(
            ["kind", "resource_id"],
            ["item_sharing.kind", "item_sharing.resource_id"],
            ondelete="CASCADE",
        ),
    )
    kind: Mapped[str] = mapped_column(String(30), primary_key=True)
    resource_id: Mapped[UUID] = mapped_column(primary_key=True)
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
