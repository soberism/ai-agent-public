"""complete ohai core parity

Revision ID: f824c0e153b2
Revises: d19f2c47a801
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f824c0e153b2"
down_revision: str | None = "d19f2c47a801"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade():
    op.add_column(
        "checklists",
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "email_preferences",
        sa.Column(
            "owner_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("reminder_enabled", sa.Boolean(), nullable=False),
        sa.Column("daily_enabled", sa.Boolean(), nullable=False),
        sa.Column("daily_time", sa.String(5), nullable=False),
        sa.Column("weekly_enabled", sa.Boolean(), nullable=False),
        sa.Column("weekly_day", sa.Integer(), nullable=False),
        sa.Column("weekly_time", sa.String(5), nullable=False),
        sa.Column("quiet_start", sa.String(5), nullable=False),
        sa.Column("quiet_end", sa.String(5), nullable=False),
        sa.Column("last_daily_date", sa.String(10)),
        sa.Column("last_weekly_key", sa.String(10)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "voice_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("turns", sa.JSON(), nullable=False),
        sa.Column("summary", sa.String(2000)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_voice_session_owner_created", "voice_sessions", ["owner_id", "created_at"]
    )
    op.create_table(
        "daily_dumps",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_text", sa.String(4000), nullable=False),
        sa.Column("candidates", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "household_audits",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "household_id",
            sa.Uuid(),
            sa.ForeignKey("households.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_household_audit_home_created",
        "household_audits",
        ["household_id", "created_at"],
    )
    op.create_table(
        "checklist_shares",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "checklist_id",
            sa.Uuid(),
            sa.ForeignKey("checklists.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "household_id",
            sa.Uuid(),
            sa.ForeignKey("households.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "checklist_id", "household_id", name="uq_checklist_household"
        ),
    )


def downgrade():
    op.drop_table("checklist_shares")
    op.drop_index("ix_household_audit_home_created", table_name="household_audits")
    op.drop_table("household_audits")
    op.drop_table("daily_dumps")
    op.drop_index("ix_voice_session_owner_created", table_name="voice_sessions")
    op.drop_table("voice_sessions")
    op.drop_table("email_preferences")
    op.drop_column("checklists", "pinned")
