import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine

from backend.api.household_schemas import InvitationCreate, MemberPatch
from backend.api.routes.sharing import SharingSettings


def test_retired_role_and_scope_rejected():
    for model, body in (
        (InvitationCreate, {"email": "test@example.test", "role": "helper"}),
        (MemberPatch, {"role": "helper"}),
        (SharingSettings, {"scope": "helpers"}),
    ):
        with pytest.raises(ValidationError):
            model.model_validate(body)


def test_retirement_migration_revokes_only_legacy_access():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        statements = (
            "CREATE TABLE household_participants (id TEXT, role TEXT, status TEXT)",
            "CREATE TABLE item_sharing (kind TEXT, resource_id TEXT, scope TEXT, household_id TEXT)",
            "CREATE TABLE item_sharing_members (kind TEXT, resource_id TEXT, account_id TEXT)",
            "CREATE TABLE notifications (kind TEXT, invitation_id TEXT, read_at TEXT)",
            "INSERT INTO household_participants VALUES ('legacy', 'helper', 'active'), ('pending', 'helper', 'pending'), ('member', 'member', 'active')",
            "INSERT INTO item_sharing VALUES ('todo','legacy','helpers','home'), ('todo','member','members','home')",
            "INSERT INTO item_sharing_members VALUES ('todo','legacy','legacy'), ('todo','member','member')",
            "INSERT INTO notifications VALUES ('invitation','pending',NULL), ('invitation','member',NULL)",
        )
        for statement in statements:
            conn.exec_driver_sql(statement)
        for name in (
            "f82b13c94de0_remove_collaborator_role.py",
            "a93c24d05ef1_close_retired_role_invitations.py",
        ):
            path = Path(__file__).parents[1] / "migrations" / "versions" / name
            spec = importlib.util.spec_from_file_location("migration", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.op = SimpleNamespace(
                execute=conn.exec_driver_sql,
                drop_constraint=lambda *args, **kwargs: None,
                create_check_constraint=lambda *args, **kwargs: None,
            )
            module.upgrade()
        assert conn.exec_driver_sql(
            "SELECT id,status FROM household_participants ORDER BY id"
        ).all() == [
            ("legacy", "removed"),
            ("member", "active"),
            ("pending", "rejected"),
        ]
        assert conn.exec_driver_sql(
            "SELECT scope,household_id FROM item_sharing WHERE resource_id='legacy'"
        ).one() == ("private", None)
        assert conn.exec_driver_sql(
            "SELECT resource_id FROM item_sharing_members"
        ).all() == [("member",)]
        assert (
            conn.exec_driver_sql(
                "SELECT read_at FROM notifications WHERE invitation_id='pending'"
            ).scalar()
            is not None
        )
        assert (
            conn.exec_driver_sql(
                "SELECT read_at FROM notifications WHERE invitation_id='member'"
            ).scalar()
            is None
        )
