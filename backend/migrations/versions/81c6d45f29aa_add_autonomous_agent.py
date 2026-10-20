"""Add autonomous agent runs, plans, checkpoints and RAG chunks.

Revision ID: 81c6d45f29aa
Revises: 6e2d9f4a8c31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "81c6d45f29aa"
down_revision: str | None = "6e2d9f4a8c31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "thread_id",
            sa.Uuid(),
            sa.ForeignKey("assistant_threads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("prompt", sa.String(4000), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("progress", sa.String(200)),
        sa.Column("final_answer", sa.Text()),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("plan_version", sa.Integer()),
        sa.Column("error", sa.String(500)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column(
            "history_saved", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "graph_resumed", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued','running','waiting','completed','failed','cancelled')",
            name="ck_agent_run_status",
        ),
    )
    op.create_index(
        "ix_agent_run_owner_created", "agent_runs", ["owner_id", "created_at", "id"]
    )
    op.create_table(
        "agent_actions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "run_id",
            sa.Uuid(),
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("tool_name", sa.String(100), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.String(800)),
        sa.Column("arguments", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("result", sa.JSON()),
        sa.Column("error", sa.String(500)),
        sa.CheckConstraint(
            "status IN ('proposed','approved','executing','completed','failed','cancelled')",
            name="ck_agent_action_status",
        ),
        sa.UniqueConstraint("run_id", "position", name="uq_agent_action_position"),
    )
    op.create_index("ix_agent_action_run", "agent_actions", ["run_id", "position"])
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "material_id",
            sa.Uuid(),
            sa.ForeignKey("document_materials.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "material_id", "content_hash", name="uq_knowledge_chunk_hash"
        ),
    )
    op.create_index(
        "ix_knowledge_chunk_owner", "knowledge_chunks", ["owner_id", "material_id"]
    )
    op.execute("CREATE TABLE checkpoint_migrations (v INTEGER PRIMARY KEY)")
    op.execute(
        "CREATE TABLE checkpoints (thread_id TEXT NOT NULL, checkpoint_ns TEXT NOT NULL DEFAULT '', checkpoint_id TEXT NOT NULL, parent_checkpoint_id TEXT, type TEXT, checkpoint JSONB NOT NULL, metadata JSONB NOT NULL DEFAULT '{}', PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id))"
    )
    op.execute(
        "CREATE TABLE checkpoint_blobs (thread_id TEXT NOT NULL, checkpoint_ns TEXT NOT NULL DEFAULT '', channel TEXT NOT NULL, version TEXT NOT NULL, type TEXT NOT NULL, blob BYTEA, PRIMARY KEY (thread_id, checkpoint_ns, channel, version))"
    )
    op.execute(
        "CREATE TABLE checkpoint_writes (thread_id TEXT NOT NULL, checkpoint_ns TEXT NOT NULL DEFAULT '', checkpoint_id TEXT NOT NULL, task_id TEXT NOT NULL, task_path TEXT NOT NULL DEFAULT '', idx INTEGER NOT NULL, channel TEXT NOT NULL, type TEXT, blob BYTEA NOT NULL, PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx))"
    )
    op.create_index("checkpoints_thread_id_idx", "checkpoints", ["thread_id"])
    op.create_index("checkpoint_blobs_thread_id_idx", "checkpoint_blobs", ["thread_id"])
    op.create_index(
        "checkpoint_writes_thread_id_idx", "checkpoint_writes", ["thread_id"]
    )
    op.execute("INSERT INTO checkpoint_migrations(v) SELECT generate_series(0, 9)")


def downgrade():
    op.drop_table("checkpoint_writes")
    op.drop_table("checkpoint_blobs")
    op.drop_table("checkpoints")
    op.drop_table("checkpoint_migrations")
    op.drop_index("ix_knowledge_chunk_owner", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    op.drop_index("ix_agent_action_run", table_name="agent_actions")
    op.drop_table("agent_actions")
    op.drop_index("ix_agent_run_owner_created", table_name="agent_runs")
    op.drop_table("agent_runs")
