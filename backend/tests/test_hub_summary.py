from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import Column, MetaData, Table, create_engine, event
from sqlalchemy.orm import Session

from backend.api.routes import hub
from backend.db.cross_system_models import EmailDelivery, VoiceMemo
from backend.db.document_models import DocumentMaterial, DocumentReviewItem
from backend.db.household_models import HouseholdParticipant
from backend.db.models import Todo
from backend.db.sharing_models import ItemSharing, ItemSharingMember


@pytest.mark.parametrize("smtp, connection_issues", [(True, 0), (False, 1)])
def test_summary_counts_only_retained_modules(monkeypatch, smtp, connection_issues):
    # SQLite validates aggregate predicates only, not PostgreSQL constraints.
    engine = create_engine("sqlite://")
    metadata = MetaData()
    for model in (
        EmailDelivery,
        VoiceMemo,
        DocumentReviewItem,
        DocumentMaterial,
        Todo,
        HouseholdParticipant,
        ItemSharing,
        ItemSharingMember,
    ):
        Table(
            model.__tablename__,
            metadata,
            *[
                Column(c.name, c.type, primary_key=c.primary_key, nullable=c.nullable)
                for c in model.__table__.columns
            ],
        )
    metadata.create_all(engine)
    monkeypatch.setattr(
        hub, "capabilities", lambda: SimpleNamespace(imap=False, smtp=smtp)
    )
    owner, other = uuid4(), uuid4()
    with Session(engine) as db:
        for user in (owner, other):
            for status in ("ongoing", "completed"):
                db.add(
                    Todo(
                        owner_id=user,
                        assignee_id=user,
                        assignment_status="assigned",
                        title="任务",
                        status=status,
                        completed_at=datetime.now(UTC)
                        if status == "completed"
                        else None,
                        create_key=uuid4(),
                        create_fingerprint="test",
                    )
                )
            for status in ("pending", "confirmed"):
                material_id = uuid4()
                db.add(
                    DocumentMaterial(
                        id=material_id,
                        owner_id=user,
                        name="材料",
                        kind="file",
                        media_type="text/plain",
                        size=0,
                        content_hash=uuid4().hex,
                        content=b"",
                    )
                )
                db.add(
                    DocumentReviewItem(
                        owner_id=user,
                        material_id=material_id,
                        target_type="todo",
                        title="审核",
                        evidence="证据",
                        confidence=1,
                        status=status,
                    )
                )
            for status in ("draft", "converted"):
                db.add(VoiceMemo(owner_id=user, transcript="备忘", status=status))
            for status in ("failed", "sent"):
                db.add(
                    EmailDelivery(
                        owner_id=user,
                        kind="test",
                        subject="测试",
                        body="测试",
                        status=status,
                    )
                )
        db.commit()
        statements = []
        event.listen(
            engine,
            "before_cursor_execute",
            lambda conn, cursor, statement, parameters, context, many: (
                statements.append(statement)
            ),
        )
        result = hub.summary(SimpleNamespace(id=owner), db)
        assert result.model_dump() == {
            "pending_reviews": 1,
            "pending_assignments": 1,
            "failed_emails": 1,
            "connection_issues": connection_issues,
            "pending_voice_memos": 1,
        }
        assert len(statements) == 4
