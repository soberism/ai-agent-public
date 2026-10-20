from datetime import datetime
from unittest.mock import MagicMock
from uuid import uuid4
from zoneinfo import ZoneInfo

from backend.features.auth import email_scheduler


def test_scheduler_scans_users_and_uses_automatic_mode(monkeypatch):
    session = MagicMock()
    session.__enter__.return_value = session
    session.scalars.side_effect = [[uuid4()], []]
    session.get.return_value = MagicMock()
    monkeypatch.setattr(email_scheduler, "Session", lambda *_: session)
    monkeypatch.setattr(email_scheduler, "settings", MagicMock())
    dispatch = MagicMock()
    monkeypatch.setattr(email_scheduler, "dispatch_email", dispatch)
    email_scheduler.run_once()
    dispatch.assert_called_once()
    assert dispatch.call_args.args[0].manual is False
    query = str(session.scalars.call_args_list[0].args[0])
    assert "LEFT OUTER JOIN email_preferences" in query
    assert "email_preferences.owner_id IS NULL" in query


def test_automatic_schedule_respects_time_weekday_and_quiet(cloud, monkeypatch):
    from helpers import register

    from backend.api.routes import parity_email
    from backend.features.auth import delivery

    register(cloud)
    zone = ZoneInfo("Asia/Shanghai")
    clock = [datetime(2026, 9, 18, 7, 30, tzinfo=zone)]

    class Clock:
        @staticmethod
        def now(zone):
            return clock[0].replace(tzinfo=zone)

    monkeypatch.setattr(parity_email, "datetime", Clock)
    send = MagicMock()
    monkeypatch.setattr(delivery, "send_message", send)
    settings = cloud.get("/api/workflows/email-settings").json()
    settings.update(
        daily_enabled=True,
        daily_time="08:00",
        weekly_enabled=True,
        weekly_day=4,
        weekly_time="20:00",
        quiet_start="22:00",
        quiet_end="07:00",
    )
    cloud.put("/api/workflows/email-settings", json=settings)

    def check():
        return cloud.post("/api/workflows/email-dispatch", json={}).json()

    assert check()["sent"] == 0
    clock[0] = datetime(2026, 9, 18, 8, 0, tzinfo=zone)
    assert check()["sent"] == 1
    assert check()["sent"] == 0
    clock[0] = datetime(2026, 9, 18, 20, 0, tzinfo=zone)
    assert check()["sent"] == 1
    clock[0] = datetime(2026, 9, 19, 22, 30, tzinfo=zone)
    assert check()["deferred"] is True
    clock[0] = datetime(2026, 9, 19, 8, 0, tzinfo=zone)
    assert check()["sent"] == 1
    assert send.call_count == 3
