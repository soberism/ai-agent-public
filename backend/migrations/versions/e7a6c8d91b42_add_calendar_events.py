"""add calendar events

Revision ID: e7a6c8d91b42
Revises: caa30fef726c
"""

import sqlalchemy as sa
from alembic import op

revision = "e7a6c8d91b42"
down_revision = "caa30fef726c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calendar_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(title) BETWEEN 1 AND 100", name="ck_event_title"),
        sa.CheckConstraint("ends_at > starts_at", name="ck_event_time_range"),
        sa.CheckConstraint(
            "description IS NULL OR length(description) <= 2000",
            name="ck_event_description",
        ),
        sa.CheckConstraint(
            "location IS NULL OR length(location) <= 200",
            name="ck_event_location",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_event_owner_time",
        "calendar_events",
        ["owner_id", "starts_at", "ends_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_event_owner_time", table_name="calendar_events")
    op.drop_table("calendar_events")
