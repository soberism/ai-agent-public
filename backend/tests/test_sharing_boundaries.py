from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.api.routes.life_shopping import shopping
from backend.api.routes.sharing import SharingSettings, put_settings
from backend.core.security import APIError
from backend.db.document_models import DocumentMaterial, DocumentReviewItem
from backend.db.household_models import HouseholdParticipant
from backend.db.life_models import ShoppingList
from backend.db.models import Checklist, Todo, User
from backend.db.sharing_models import ItemSharing, ItemSharingMember
from backend.features.sharing.access import accessible
from backend.features.sharing.linked import linked_resources


def test_cross_owner_links_do_not_grant_access_or_overwrite_policy():
    engine = create_engine("sqlite://")
    for model in (
        User,
        HouseholdParticipant,
        ItemSharing,
        ItemSharingMember,
        Checklist,
        ShoppingList,
    ):
        model.__table__.create(engine)
    with Session(engine) as session:
        owner = User(email="owner@example.test", password_hash="test")
        other = User(email="other@example.test", password_hash="test")
        session.add_all([owner, other])
        session.flush()
        checklist = Checklist(owner_id=other.id, title="私有清单")
        session.add(checklist)
        session.flush()
        row = ShoppingList(
            owner_id=owner.id, title="跨归属", unified_checklist_id=checklist.id
        )
        session.add(row)
        session.add(
            ItemSharing(
                kind="checklist",
                resource_id=checklist.id,
                scope="members",
                household_id=uuid4(),
            )
        )
        session.commit()
        with pytest.raises(APIError):
            accessible(session, owner, Checklist, checklist.id)
        with pytest.raises(APIError):
            accessible(session, other, ShoppingList, row.id)
        with pytest.raises(APIError):
            shopping(session, owner, list_id=row.id)
        put_settings("shopping", row.id, SharingSettings(), owner, session)
        assert session.get(ItemSharing, ("checklist", checklist.id)).scope == "members"
        session.get(ItemSharing, ("shopping", row.id)).scope = "household"
        session.commit()
        put_settings("checklist", checklist.id, SharingSettings(), other, session)
        assert session.get(ItemSharing, ("shopping", row.id)).scope == "household"


def test_material_propagates_only_accepted_new_generated_targets():
    engine = create_engine("sqlite://")
    for model in (DocumentMaterial, DocumentReviewItem, Todo):
        model.__table__.create(engine)
    with Session(engine) as session:
        owner_id = uuid4()
        material = DocumentMaterial(
            owner_id=owner_id,
            name="材料",
            kind="file",
            media_type="text/plain",
            size=1,
            content_hash="x",
            content=b"x",
        )
        session.add(material)
        session.flush()
        targets = []
        for change, status in (
            ("new", "accepted"),
            ("changed", "accepted"),
            ("cancelled", "accepted"),
            ("duplicate", "accepted"),
            ("new", "pending"),
        ):
            todo = Todo(
                owner_id=owner_id,
                title="事项",
                create_key=uuid4(),
                create_fingerprint="x",
            )
            session.add(todo)
            session.flush()
            targets.append(todo)
            session.add(
                DocumentReviewItem(
                    owner_id=owner_id,
                    material_id=material.id,
                    target_type="todo",
                    title="事项",
                    evidence="测试",
                    confidence=1,
                    change_kind=change,
                    status=status,
                    target_id=todo.id,
                )
            )
        session.commit()
        assert list(linked_resources(session, "material", material)) == [
            ("todo", targets[0].id)
        ]
