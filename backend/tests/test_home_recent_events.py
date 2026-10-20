from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from backend.api.routes.platform import home
from backend.db.models import CalendarEvent


def test_home_returns_recent_events_scoped_to_owner():
    owner = uuid4()
    now = datetime(2026, 9, 17, tzinfo=UTC)
    event = CalendarEvent(
        id=uuid4(),
        owner_id=owner,
        title="家长会",
        source="app",
        status="scheduled",
        timezone="Asia/Shanghai",
        starts_at=now,
        ends_at=now + timedelta(hours=1),
        created_at=now,
        updated_at=now,
    )
    session = Mock()
    session.scalars.side_effect = [[], [event], [], []]
    session.scalar.return_value = 0
    result = home(SimpleNamespace(id=owner, timezone="Asia/Shanghai"), session)
    assert result.recent_events[0].id == event.id
    assert result.recent_events[0].start_time == "08:00"
    statement = (
        session.scalars.call_args_list[1].args[0].compile(dialect=postgresql.dialect())
    )
    assert owner in statement.params.values()
    assert "calendar_events.owner_id =" in str(statement)
    assert "calendar_events.updated_at DESC, calendar_events.id ASC" in str(statement)
    assert 5 in statement.params.values()
