"""Run with RUN_INTEGRATION=1 POSTGRES_DB=ai_agent_test; cloud services only."""

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app import app
from backend.core import security as auth
from backend.db.cross_system_models import EmailDelivery, MailImport, VoiceMemo
from backend.db.document_models import (
    DocumentFolder,
    DocumentMaterial,
    DocumentReviewItem,
)
from backend.db.household_models import (
    Contact,
    ContactGroup,
    ContactGroupMembership,
    Household,
    HouseholdParticipant,
    HouseholdProfile,
    Notification,
    Pet,
)
from backend.db.life_models import (
    LifePreference,
    MealPlan,
    MedicalAppointment,
    PantryItem,
    ShoppingList,
)
from backend.db.models import (
    AssistantMemory,
    AssistantMessage,
    AssistantProfile,
    AssistantThread,
    CalendarEvent,
    Checklist,
    ChecklistItem,
    Reminder,
    Todo,
    User,
)
from backend.db.session import engine
from backend.features.auth import verification

MAILBOX = {}

HEADERS = {"Origin": "http://localhost:5173", "X-App-Request": "1"}
PASSWORD = "合法测试密码12345678"


def login_as(client, cookies):
    client.cookies.clear()
    client.cookies.update(cookies)


def family_accounts(client):
    owner, _ = register(client)
    owner_cookie = dict(client.cookies)
    home = client.post("/api/households", json={"name": "权限测试家庭"}).json()
    client.cookies.clear()
    member, email = register(client)
    member_cookie = dict(client.cookies)
    client.cookies.clear()
    helper, helper_email = register(client)
    helper_cookie = dict(client.cookies)
    for receiver, cookies, role in [
        (email, member_cookie, "member"),
        (helper_email, helper_cookie, "member"),
    ]:
        login_as(client, owner_cookie)
        invitation = client.post(
            f"/api/households/{home['id']}/invitations",
            json={"email": receiver, "role": role},
        )
        assert invitation.status_code == 201, invitation.text
        login_as(client, cookies)
        accepted = client.post(
            f"/api/households/invitations/{invitation.json()['id']}/accept", json={}
        )
        assert accepted.status_code == 200, accepted.text
    return owner, owner_cookie, home, member, member_cookie, helper, helper_cookie


@pytest.fixture
def cloud(monkeypatch):
    if os.environ.get("RUN_INTEGRATION") != "1":
        pytest.skip("显式 RUN_INTEGRATION=1 才访问云端隔离测试库")
    assert engine.url.database == "ai_agent_test", "禁止对开发数据运行测试"
    from queue_isolation import isolate_default_queue

    cleanup_queue = isolate_default_queue(monkeypatch)
    MAILBOX.clear()
    namespace = "ai-agent:test:" + uuid4().hex + ":"
    monkeypatch.setattr(auth.settings, "redis_namespace", namespace)
    monkeypatch.setattr(auth.settings, "cookie_secure", False)
    monkeypatch.setattr(auth.settings, "allowed_origins", [HEADERS["Origin"]])
    monkeypatch.setattr(
        auth.settings,
        "email_verification_secret",
        SecretStr("isolated-email-secret-for-tests-32chars"),
    )
    for name, value in {
        "smtp_host": "smtp.example.com",
        "smtp_username": "test",
        "smtp_from": "test@example.com",
        "smtp_password": SecretStr("test-only"),
    }.items():
        monkeypatch.setattr(auth.settings, name, value)
    monkeypatch.setattr(
        verification, "send_code", lambda email, code: MAILBOX.__setitem__(email, code)
    )
    with TestClient(app, headers=HEADERS) as client:
        yield client
    app.dependency_overrides.clear()
    cleanup_queue()
    keys = list(auth.redis.scan_iter(match=namespace + "*"))
    if keys:
        auth.redis.delete(*keys)
    with Session(engine) as db:
        ids = select(User.id).where(User.email.in_(list(MAILBOX)))
        db.execute(delete(VoiceMemo).where(VoiceMemo.owner_id.in_(ids)))
        db.execute(delete(EmailDelivery).where(EmailDelivery.owner_id.in_(ids)))
        db.execute(delete(MailImport).where(MailImport.owner_id.in_(ids)))
        material_ids = select(DocumentMaterial.id).where(
            DocumentMaterial.owner_id.in_(ids)
        )
        db.execute(
            delete(DocumentReviewItem).where(
                DocumentReviewItem.material_id.in_(material_ids)
            )
        )
        db.execute(delete(DocumentMaterial).where(DocumentMaterial.owner_id.in_(ids)))
        db.execute(delete(DocumentFolder).where(DocumentFolder.owner_id.in_(ids)))
        db.execute(
            delete(MedicalAppointment).where(MedicalAppointment.owner_id.in_(ids))
        )
        db.execute(delete(ShoppingList).where(ShoppingList.owner_id.in_(ids)))
        db.execute(delete(MealPlan).where(MealPlan.owner_id.in_(ids)))
        db.execute(delete(PantryItem).where(PantryItem.owner_id.in_(ids)))
        db.execute(delete(LifePreference).where(LifePreference.owner_id.in_(ids)))
        contact_ids = select(Contact.id).where(Contact.owner_id.in_(ids))
        group_ids = select(ContactGroup.id).where(ContactGroup.owner_id.in_(ids))
        db.execute(
            delete(ContactGroupMembership).where(
                ContactGroupMembership.contact_id.in_(contact_ids)
                | ContactGroupMembership.group_id.in_(group_ids)
            )
        )
        db.execute(delete(Contact).where(Contact.owner_id.in_(ids)))
        db.execute(delete(ContactGroup).where(ContactGroup.owner_id.in_(ids)))
        household_ids = select(Household.id).where(Household.owner_id.in_(ids))
        db.execute(
            delete(Notification).where(
                Notification.recipient_id.in_(ids)
                | Notification.household_id.in_(household_ids)
            )
        )
        db.execute(
            delete(HouseholdProfile).where(
                HouseholdProfile.household_id.in_(household_ids)
            )
        )
        db.execute(delete(Pet).where(Pet.household_id.in_(household_ids)))
        db.execute(
            delete(HouseholdParticipant).where(
                HouseholdParticipant.household_id.in_(household_ids)
            )
        )
        db.execute(delete(Household).where(Household.id.in_(household_ids)))
        thread_ids = select(AssistantThread.id).where(AssistantThread.owner_id.in_(ids))
        db.execute(
            delete(AssistantMessage).where(AssistantMessage.thread_id.in_(thread_ids))
        )
        db.execute(delete(AssistantThread).where(AssistantThread.owner_id.in_(ids)))
        db.execute(delete(AssistantMemory).where(AssistantMemory.owner_id.in_(ids)))
        db.execute(delete(AssistantProfile).where(AssistantProfile.owner_id.in_(ids)))
        checklist_ids = select(Checklist.id).where(Checklist.owner_id.in_(ids))
        db.execute(
            delete(ChecklistItem).where(ChecklistItem.checklist_id.in_(checklist_ids))
        )
        db.execute(delete(Reminder).where(Reminder.owner_id.in_(ids)))
        db.execute(delete(CalendarEvent).where(CalendarEvent.owner_id.in_(ids)))
        db.execute(delete(Checklist).where(Checklist.owner_id.in_(ids)))
        db.execute(delete(Todo).where(Todo.owner_id.in_(ids)))
        db.execute(delete(User).where(User.email.in_(list(MAILBOX))))
        db.commit()


def register(client, email=None):
    email = email or uuid4().hex + "@integration.example.com"
    code = request_code(client, email)
    result = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "confirm_password": PASSWORD,
            "verification_code": code,
        },
    )
    assert result.status_code == 201, result.text
    return result.json(), email


def create(client, **body):
    result = client.post(
        "/api/todos",
        headers={"Idempotency-Key": str(uuid4())},
        json={"title": "买牛奶", **body},
    )
    assert result.status_code == 201, result.text
    return result.json()


def request_code(client, email):
    response = client.post("/api/auth/register/code", json={"email": email})
    assert response.status_code == 200, response.text
    return MAILBOX[email]
