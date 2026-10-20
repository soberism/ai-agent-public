"""add checklists and reminders

Revision ID: f31d0a4c9e87
Revises: e7a6c8d91b42
"""

import sqlalchemy as sa
from alembic import op

revision = "f31d0a4c9e87"
down_revision = "e7a6c8d91b42"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "checklists",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(title) BETWEEN 1 AND 100", name="ck_checklist_title"
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_checklist_owner_updated", "checklists", ["owner_id", "updated_at", "id"]
    )
    op.create_table(
        "checklist_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("checklist_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(title) BETWEEN 1 AND 200", name="ck_checklist_item_title"
        ),
        sa.ForeignKeyConstraint(
            ["checklist_id"], ["checklists.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_checklist_item_order", "checklist_items", ["checklist_id", "position", "id"]
    )
    op.create_table(
        "reminders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("todo_id", sa.Uuid(), nullable=True),
        sa.Column("event_id", sa.Uuid(), nullable=True),
        sa.Column("remind_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("status", sa.String(9), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(todo_id IS NOT NULL)::int + (event_id IS NOT NULL)::int = 1",
            name="ck_reminder_one_subject",
        ),
        sa.CheckConstraint(
            "status IN ('scheduled','disabled')", name="ck_reminder_status"
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["todo_id"], ["todos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["event_id"], ["calendar_events.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_reminder_owner_time", "reminders", ["owner_id", "remind_at", "id"]
    )


def downgrade() -> None:
    op.drop_table("reminders")
    op.drop_table("checklist_items")
    op.drop_table("checklists")
