from datetime import datetime
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.models import utcnow
from backend.db.session import Base


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','waiting','completed','failed','cancelled')",
            name="ck_agent_run_status",
        ),
        Index("ix_agent_run_owner_created", "owner_id", "created_at", "id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    thread_id: Mapped[UUID] = mapped_column(
        ForeignKey("assistant_threads.id", ondelete="CASCADE")
    )
    prompt: Mapped[str] = mapped_column(String(4000))
    parent_plan_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL")
    )
    task_context: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(12), default="queued")
    progress: Mapped[str | None] = mapped_column(String(200))
    final_answer: Mapped[str | None] = mapped_column(Text)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    suggestions: Mapped[list] = mapped_column(JSON, default=list)
    plan_version: Mapped[int | None]
    error: Mapped[str | None] = mapped_column(String(500))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    history_saved: Mapped[bool] = mapped_column(default=False, server_default="false")
    graph_resumed: Mapped[bool] = mapped_column(default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class AgentAction(Base):
    __tablename__ = "agent_actions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('proposed','approved','executing','completed','failed','cancelled')",
            name="ck_agent_action_status",
        ),
        UniqueConstraint("run_id", "position", name="uq_agent_action_position"),
        Index("ix_agent_action_run", "run_id", "position"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE")
    )
    position: Mapped[int]
    tool_name: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(String(800))
    arguments: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(12), default="proposed")
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(String(500))


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("material_id", "content_hash", name="uq_knowledge_chunk_hash"),
        Index("ix_knowledge_chunk_owner", "owner_id", "material_id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    material_id: Mapped[UUID] = mapped_column(
        ForeignKey("document_materials.id", ondelete="CASCADE")
    )
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    content_hash: Mapped[str] = mapped_column(String(64))
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
