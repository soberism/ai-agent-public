import smtplib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from backend.db.cross_system_models import EmailDelivery
from backend.features.auth import delivery


def test_item_reminders_default_to_thirty_minutes():
    from backend.api.routes.parity_email import EmailSettings
    from backend.db.parity_models import EmailPreference

    settings = EmailSettings()
    assert (settings.reminder_enabled, settings.reminder_minutes) == (True, 30)
    columns = EmailPreference.__table__.c
    assert columns.reminder_enabled.default.arg is True
    assert columns.reminder_minutes.default.arg == 30


def test_reminder_delivery_kind_fits_database_column(monkeypatch):
    session = MagicMock()
    reminder = SimpleNamespace(id=uuid4(), todo_id=uuid4(), status="scheduled")
    session.scalars.return_value = [reminder]
    session.get.return_value = SimpleNamespace(title="测试提醒")
    row = EmailDelivery(
        id=uuid4(), owner_id=uuid4(), kind="reminder", subject="测试", body="正文"
    )
    session.get.return_value = None
    send = MagicMock()
    monkeypatch.setattr(delivery, "send_message", send)
    user = SimpleNamespace(
        id=uuid4(), timezone="Asia/Shanghai", email="test@example.com"
    )

    assert delivery.deliver_record(row, user.email, session).status == "sent"
    assert len(row.kind) <= EmailDelivery.__table__.c.kind.type.length
    send.assert_called_once()
    assert session.commit.call_count == 2


def test_database_failure_prevents_smtp(monkeypatch):
    import pytest

    session = MagicMock()
    session.commit.side_effect = RuntimeError("database failure")
    send = MagicMock()
    monkeypatch.setattr(delivery, "send_message", send)
    with pytest.raises(RuntimeError):
        delivery.deliver_record(
            SimpleNamespace(id=uuid4()), "test@example.com", session
        )
    send.assert_not_called()


def test_timeout_is_not_retryable_failure(monkeypatch):
    session = MagicMock()

    def send(*args):
        session.commit.assert_called_once()
        raise TimeoutError()

    monkeypatch.setattr(delivery, "send_message", send)
    row = SimpleNamespace(id=uuid4(), subject="测试", body="正文")
    assert delivery.deliver_record(row, "test@example.com", session).status == "unknown"


def test_rejected_mail_can_retry(monkeypatch):
    session = MagicMock()
    send = MagicMock(side_effect=smtplib.SMTPDataError(550, b"rejected"))
    monkeypatch.setattr(delivery, "send_message", send)
    row = SimpleNamespace(id=uuid4(), subject="测试", body="正文", dedupe_key=None)
    assert delivery.deliver_record(row, "test@example.com", session).status == "failed"
    send.side_effect = None
    assert delivery.deliver_record(row, "test@example.com", session).status == "sent"


def test_dispatch_is_idempotent_in_cloud_database(cloud, monkeypatch):
    from helpers import register

    from backend.api.routes import parity_email

    register(cloud)
    monkeypatch.setattr(parity_email, "in_quiet", lambda *_: False)
    send = MagicMock()
    monkeypatch.setattr(delivery, "send_message", send)
    settings = cloud.get("/api/workflows/email-settings").json()
    settings.update(
        daily_enabled=True,
        daily_time="23:59",
        weekly_enabled=True,
        weekly_time="23:59",
        weekly_day=6,
    )
    assert cloud.put("/api/workflows/email-settings", json=settings).status_code == 200
    request = {"manual": True, "request_id": str(uuid4())}
    first = cloud.post("/api/workflows/email-dispatch", json=request)
    assert first.status_code == 200
    assert first.json()["sent"] == 2
    assert cloud.post("/api/workflows/email-dispatch", json=request).json()["sent"] == 0
    assert send.call_count == 2
    request["request_id"] = str(uuid4())
    assert cloud.post("/api/workflows/email-dispatch", json=request).json()["sent"] == 2
    records = cloud.get("/api/mail/notifications").json()
    assert len(records) == 4
    assert {record["subject"] for record in records} == {
        "今日待办摘要",
        "未来七天待办摘要",
    }
    settings.update(daily_time="00:00", weekly_enabled=False)
    cloud.put("/api/workflows/email-settings", json=settings)
    assert cloud.post("/api/workflows/email-dispatch", json={}).json()["sent"] == 1
    assert cloud.post("/api/workflows/email-dispatch", json={}).json()["sent"] == 0


def test_item_reminders_include_content_and_dedupe(cloud, monkeypatch):
    from uuid import UUID

    from helpers import register
    from sqlalchemy.orm import Session

    from backend.api.routes import parity_email
    from backend.db.models import CalendarEvent, Todo
    from backend.db.parity_models import EmailPreference
    from backend.db.session import engine

    user, _ = register(cloud)
    with Session(engine) as session:
        preference = session.get(EmailPreference, UUID(user["id"]))
        assert preference is not None
        assert (preference.reminder_enabled, preference.reminder_minutes) == (True, 30)
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    due = now + timedelta(minutes=20)
    todo = Todo(
        owner_id=UUID(user["id"]),
        title="买牛奶",
        description="低脂两盒",
        due_date=due.date(),
        due_time=due.time(),
        due_at=due,
        timezone="UTC",
        create_key=uuid4(),
        create_fingerprint="test",
    )
    event = CalendarEvent(
        owner_id=UUID(user["id"]),
        title="项目会议",
        description="讨论预算",
        location="会议室",
        timezone="UTC",
        starts_at=due,
        ends_at=due + timedelta(hours=1),
    )
    with Session(engine) as session:
        session.add_all([todo, event])
        session.commit()
        todo_id, event_id = todo.id, event.id
    monkeypatch.setattr(parity_email, "in_quiet", lambda *_: False)
    send = MagicMock()
    monkeypatch.setattr(delivery, "send_message", send)
    settings = cloud.get("/api/workflows/email-settings").json()
    settings.update(reminder_enabled=True, reminder_minutes=30)
    assert cloud.put("/api/workflows/email-settings", json=settings).status_code == 200
    assert cloud.post("/api/workflows/email-dispatch", json={}).json()["sent"] == 2
    assert cloud.post("/api/workflows/email-dispatch", json={}).json()["sent"] == 0
    bodies = [call.args[2] for call in send.call_args_list]
    assert any("低脂两盒" in body for body in bodies)
    assert any("讨论预算" in body and "会议室" in body for body in bodies)
    assert any(f"http://localhost:9988/todos/{todo_id}/edit" in body for body in bodies)
    assert any(
        f"http://localhost:9988/calendar/{event_id}/edit" in body for body in bodies
    )


def test_custom_recipients_and_notification_switch(cloud, monkeypatch):
    from helpers import register

    _, email = register(cloud)
    send = MagicMock()
    monkeypatch.setattr(delivery, "send_message", send)
    settings = cloud.get("/api/workflows/email-settings").json()
    assert settings["recipient_emails"] == [email]
    settings.update(
        recipient_emails=["one@example.com", "two@example.com"], daily_enabled=True
    )
    assert cloud.put("/api/workflows/email-settings", json=settings).status_code == 200
    assert cloud.get("/api/workflows/email-settings").json()["recipient_emails"] == [
        email,
        "one@example.com",
        "two@example.com",
    ]
    result = cloud.post(
        "/api/workflows/email-dispatch",
        json={"manual": True, "request_id": str(uuid4())},
    )
    assert result.json()["sent"] == 1
    assert send.call_args.args[0] == f"{email}, one@example.com, two@example.com"
    settings["notifications_enabled"] = False
    assert cloud.put("/api/workflows/email-settings", json=settings).status_code == 200
    assert (
        cloud.post(
            "/api/workflows/email-dispatch",
            json={"manual": True, "request_id": str(uuid4())},
        ).status_code
        == 409
    )
    assert cloud.post("/api/workflows/email-dispatch", json={}).json()["sent"] == 0
    assert (
        cloud.post(
            "/api/mail/notifications", json={"subject": "测试", "body": "正文"}
        ).status_code
        == 409
    )
    settings["recipient_emails"] = ["invalid-email"]
    assert cloud.put("/api/workflows/email-settings", json=settings).status_code == 422
    assert send.call_count == 1
    settings["recipient_emails"] = [f"person{i}@example.com" for i in range(4)]
    assert cloud.put("/api/workflows/email-settings", json=settings).status_code == 422
