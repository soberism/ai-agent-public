"""complete cross system assistant

Revision ID: d19f2c47a801
Revises: b813db9827c1
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d19f2c47a801"
down_revision: str | None = "b813db9827c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("todos", sa.Column("household_id", sa.Uuid(), nullable=True))
    op.add_column("todos", sa.Column("assignee_id", sa.Uuid(), nullable=True))
    op.add_column(
        "todos",
        sa.Column(
            "assignment_status",
            sa.String(20),
            nullable=False,
            server_default="personal",
        ),
    )
    op.add_column("todos", sa.Column("assignment_note", sa.String(500), nullable=True))
    op.create_foreign_key(
        "fk_todo_household",
        "todos",
        "households",
        ["household_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_todo_assignee",
        "todos",
        "users",
        ["assignee_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "calendar_events", sa.Column("household_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        "fk_event_household",
        "calendar_events",
        "households",
        ["household_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "document_materials", sa.Column("subject_type", sa.String(20), nullable=True)
    )
    op.add_column(
        "document_materials", sa.Column("subject_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "document_materials", sa.Column("ocr_confidence", sa.Float(), nullable=True)
    )
    op.add_column(
        "document_review_items",
        sa.Column("change_kind", sa.String(20), nullable=False, server_default="new"),
    )
    op.add_column(
        "document_review_items",
        sa.Column("previous_value", sa.String(500), nullable=True),
    )
    op.create_table(
        "mail_imports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("message_id", sa.String(500), nullable=False),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("sender", sa.String(500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "material_id",
            sa.Uuid(),
            sa.ForeignKey("document_materials.id", ondelete="SET NULL"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "owner_id", "message_id", name="uq_mail_import_owner_message"
        ),
    )
    op.create_index(
        "ix_mail_import_owner_created", "mail_imports", ["owner_id", "created_at"]
    )
    op.create_table(
        "email_deliveries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("body", sa.String(2000), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.String(300)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_email_delivery_owner_created",
        "email_deliveries",
        ["owner_id", "created_at"],
    )
    op.create_table(
        "voice_memos",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("transcript", sa.String(4000), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("target_type", sa.String(20)),
        sa.Column("target_id", sa.Uuid()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_voice_memo_owner_created", "voice_memos", ["owner_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_table("voice_memos")
    op.drop_table("email_deliveries")
    op.drop_table("mail_imports")
    op.drop_column("document_review_items", "previous_value")
    op.drop_column("document_review_items", "change_kind")
    op.drop_column("document_materials", "ocr_confidence")
    op.drop_column("document_materials", "subject_id")
    op.drop_column("document_materials", "subject_type")
    op.drop_constraint("fk_event_household", "calendar_events", type_="foreignkey")
    op.drop_column("calendar_events", "household_id")
    op.drop_constraint("fk_todo_assignee", "todos", type_="foreignkey")
    op.drop_constraint("fk_todo_household", "todos", type_="foreignkey")
    op.drop_column("todos", "assignment_note")
    op.drop_column("todos", "assignment_status")
    op.drop_column("todos", "assignee_id")
    op.drop_column("todos", "household_id")
