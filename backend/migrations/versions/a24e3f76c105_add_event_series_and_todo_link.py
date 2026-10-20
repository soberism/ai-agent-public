"""add event series and todo link

Revision ID: a24e3f76c105
Revises: f31d0a4c9e87
"""

import sqlalchemy as sa
from alembic import op

revision = "a24e3f76c105"
down_revision = "f31d0a4c9e87"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("calendar_events", sa.Column("todo_id", sa.Uuid(), nullable=True))
    op.add_column("calendar_events", sa.Column("series_id", sa.Uuid(), nullable=True))
    op.add_column(
        "calendar_events",
        sa.Column("source", sa.String(20), nullable=False, server_default="app"),
    )
    op.add_column(
        "calendar_events",
        sa.Column("status", sa.String(9), nullable=False, server_default="scheduled"),
    )
    op.create_check_constraint(
        "ck_event_status", "calendar_events", "status IN ('scheduled','cancelled')"
    )
    op.create_foreign_key(
        "fk_calendar_event_todo",
        "calendar_events",
        "todos",
        ["todo_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_calendar_event_series", "calendar_events", ["owner_id", "series_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_calendar_event_series", table_name="calendar_events")
    op.drop_constraint("fk_calendar_event_todo", "calendar_events", type_="foreignkey")
    op.drop_column("calendar_events", "source")
    op.drop_constraint("ck_event_status", "calendar_events", type_="check")
    op.drop_column("calendar_events", "status")
    op.drop_column("calendar_events", "series_id")
    op.drop_column("calendar_events", "todo_id")
