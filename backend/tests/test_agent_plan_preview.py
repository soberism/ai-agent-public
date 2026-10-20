from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from backend.core.security import APIError
from backend.features.assistant.agent_plan_persistence import persist_plan


def test_oversize_plan_preview_is_rejected_without_persisting(monkeypatch):
    from backend.features.assistant import agent_plan_persistence

    monkeypatch.setattr(
        agent_plan_persistence,
        "prepare",
        lambda *_: ({"body": {"content": "字" * 801}}, {}),
    )
    session = Mock()
    run_row = SimpleNamespace(
        id=uuid4(), thread_id=uuid4(), plan_version=0, parent_plan_id=None
    )
    session.scalars.return_value = []
    with pytest.raises(APIError) as error:
        persist_plan(
            session,
            run_row,
            SimpleNamespace(id=uuid4()),
            [{"tool_name": "create_todo", "arguments": {}, "description": "短描述"}],
        )
    assert "拆分" in error.value.message
    session.add.assert_not_called()
    session.commit.assert_not_called()
