from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.api.routes.sharing import SharingSettings, put_settings
from backend.core.security import APIError
from backend.db.household_models import Household, HouseholdParticipant
from backend.db.models import Todo, User
from backend.db.sharing_models import ItemSharing, ItemSharingMember
from backend.features.sharing.access import (
    RESOURCE_MODELS,
    accessible,
    visible_condition,
)


def test_shared_access_is_dynamic_and_owner_is_preserved():
    engine = create_engine("sqlite://")
    for model in (
        User,
        Household,
        HouseholdParticipant,
        ItemSharing,
        ItemSharingMember,
        Todo,
    ):
        model.__table__.create(engine)
    with Session(engine) as session:
        users = [
            User(id=uuid4(), email=f"u{i}@example.test", password_hash="test")
            for i in range(4)
        ]
        session.add_all(users)
        home = Household(id=uuid4(), owner_id=users[0].id, name="测试家庭")
        session.add(home)
        members = []
        for user, role in zip(users[:3], ("owner", "member", "member")):
            member = HouseholdParticipant(
                household_id=home.id,
                account_id=user.id,
                display_name="测试",
                email=user.email,
                role=role,
                status="active",
                invited_by=users[0].id,
            )
            members.append(member)
            session.add(member)
        todo = Todo(
            owner_id=users[0].id,
            title="共享测试",
            create_key=uuid4(),
            create_fingerprint="x",
        )
        session.add(todo)
        session.commit()

        def ids(user):
            return list(
                session.scalars(select(Todo.id).where(visible_condition(Todo, user.id)))
            )

        assert ids(users[1]) == []
        put_settings(
            "todo",
            todo.id,
            SharingSettings(scope="household", household_id=home.id),
            users[0],
            session,
        )
        assert ids(users[1]) == [todo.id]
        assert ids(users[2]) == [todo.id]
        accessible(session, users[1], Todo, todo.id).title = "成员修改"
        session.commit()
        assert todo.owner_id == users[0].id
        put_settings(
            "todo",
            todo.id,
            SharingSettings(
                scope="members", household_id=home.id, member_ids=[users[2].id]
            ),
            users[0],
            session,
        )
        assert ids(users[1]) == [] and ids(users[2]) == [todo.id]
        members[2].status = "removed"
        session.commit()
        assert ids(users[2]) == []
        with pytest.raises(APIError):
            accessible(session, users[2], Todo, todo.id)
        with pytest.raises(APIError):
            put_settings(
                "todo",
                todo.id,
                SharingSettings(
                    scope="members", household_id=home.id, member_ids=[users[3].id]
                ),
                users[0],
                session,
            )
        put_settings("todo", todo.id, SharingSettings(), users[0], session)
        assert ids(users[1]) == []


def test_all_predicates_compile_without_autocorrelation_errors():
    for model in RESOURCE_MODELS.values():
        str(select(model).where(visible_condition(model, uuid4())).compile())


def test_shared_scope_requires_its_target():
    with pytest.raises(ValueError, match="必须选择家庭"):
        SharingSettings(scope="household")
    with pytest.raises(ValueError, match="至少一位家庭成员"):
        SharingSettings(scope="members", household_id=uuid4())

    assert SharingSettings().scope == "private"
    assert SharingSettings(scope="household", household_id=uuid4()).scope == "household"


def test_shopping_and_checklist_share_one_policy_and_child_access():
    from backend.db.life_models import ShoppingList
    from backend.db.models import Checklist, ChecklistItem

    engine = create_engine("sqlite://")
    for model in (
        User,
        Household,
        HouseholdParticipant,
        ItemSharing,
        ItemSharingMember,
        Checklist,
        ChecklistItem,
        ShoppingList,
    ):
        model.__table__.create(engine)
    with Session(engine) as session:
        owner = User(email="owner@example.test", password_hash="test")
        member = User(email="member@example.test", password_hash="test")
        session.add_all([owner, member])
        session.flush()
        home = Household(owner_id=owner.id, name="测试")
        session.add(home)
        session.flush()
        for user in (owner, member):
            session.add(
                HouseholdParticipant(
                    household_id=home.id,
                    account_id=user.id,
                    display_name="测试",
                    email=user.email,
                    role="member",
                    status="active",
                    invited_by=owner.id,
                )
            )
        checklist = Checklist(owner_id=owner.id, title="清单")
        session.add(checklist)
        session.flush()
        shopping = ShoppingList(
            owner_id=owner.id, title="清单", unified_checklist_id=checklist.id
        )
        child = ChecklistItem(checklist_id=checklist.id, title="子项", position=0)
        session.add_all([shopping, child])
        session.commit()
        put_settings(
            "shopping",
            shopping.id,
            SharingSettings(scope="household", household_id=home.id),
            owner,
            session,
        )
        assert accessible(session, member, Checklist, checklist.id).id == checklist.id
        assert accessible(session, member, ChecklistItem, child.id).id == child.id
        with pytest.raises(APIError) as error:
            put_settings("checklist", checklist.id, SharingSettings(), member, session)
        assert error.value.status == 403
        put_settings("checklist", checklist.id, SharingSettings(), owner, session)
        with pytest.raises(APIError):
            accessible(session, member, ShoppingList, shopping.id)
        with pytest.raises(APIError):
            accessible(session, member, ChecklistItem, child.id)
