import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.api.planning_schemas import ChecklistCreate, ChecklistWithItemsCreate
from backend.api.routes import assistant, assistant_actions, planning
from backend.api.schemas import AssistantMessage


class Session:
    def __init__(self):
        self.rows = []
        self.commits = 0

    def add(self, row):
        self.rows.append(row)

    def flush(self):
        self.rows[0].id = uuid4()

    def add_all(self, rows):
        self.rows.extend(rows)

    def commit(self):
        self.commits += 1


class Store:
    def __init__(self):
        self.values = {}

    def set(self, key, value, ex):
        self.values[key] = value


def draft(monkeypatch, title, items):
    thread_id, user_id = uuid4(), uuid4()
    monkeypatch.setattr(assistant.history, "owned", lambda *_: object())
    monkeypatch.setattr(assistant.history, "append_pair", lambda *_: None)
    monkeypatch.setattr(assistant.history, "cache", lambda *_: None)
    monkeypatch.setattr(assistant.history, "messages", lambda *_: [])
    monkeypatch.setattr(assistant, "load_thread", lambda *_: SimpleNamespace())
    monkeypatch.setattr(assistant, "model_context", lambda *_: ("", []))
    monkeypatch.setattr(assistant, "current_context", lambda *_: ([], []))
    monkeypatch.setattr(assistant, "personalize", lambda reply, *_: reply)
    monkeypatch.setattr(
        assistant,
        "interpret",
        lambda *_: SimpleNamespace(
            action="create_checklist",
            title=title,
            items=items,
            reference_index=None,
            _sources=[],
        ),
    )
    store, session = Store(), Session()
    result = assistant.message(
        AssistantMessage(thread_id=thread_id, message="创建出国清单"),
        SimpleNamespace(id=user_id, timezone="Asia/Shanghai"),
        session,
        store,
    )
    assert not session.rows and session.commits == 0
    return result, store


def test_draft_is_complete_validated_and_requires_confirmation(monkeypatch):
    reply, store = draft(monkeypatch, " 出国必备 ", [" 护照 ", "转换插头"])
    assert reply.kind == "confirm"
    assert "1. 护照\n2. 转换插头" in reply.message
    raw = store.values[assistant_actions.action_key(reply.action_token)]
    assert json.loads(raw.split("|", 1)[1])["payload"] == {
        "title": "出国必备",
        "items": ["护照", "转换插头"],
    }


@pytest.mark.parametrize("items", [[" "], ["a" * 16], ["护照"] * 51])
def test_invalid_items_never_issue_confirmation(monkeypatch, items):
    reply, store = draft(monkeypatch, "出国必备", items)
    assert reply.kind == "clarify" and not store.values


@pytest.mark.parametrize("items", [[], ["护照", "转换插头"]])
def test_create_commits_parent_and_ordered_items_once(monkeypatch, items):
    session = Session()
    monkeypatch.setattr(planning, "checklist_output", lambda *_: session.rows)
    rows = planning.create_checklist(
        ChecklistWithItemsCreate(title="出国必备", items=items),
        SimpleNamespace(id=uuid4()),
        session,
    )
    assert session.commits == 1
    assert len(rows) == len(items) + 1
    assert [row.title for row in rows[1:]] == items
    assert [row.position for row in rows[1:]] == list(range(len(items)))
    assert all(row.checklist_id == rows[0].id for row in rows[1:])


def test_empty_creation_compatible_and_rename_rejects_items():
    assert ChecklistWithItemsCreate(title="清单").items == []
    with pytest.raises(ValidationError):
        ChecklistCreate(title="清单", items=["护照"])


def test_item_failure_never_commits_partial_checklist():
    session = Session()

    def fail(_):
        raise RuntimeError("条目写入失败")

    session.add_all = fail
    with pytest.raises(RuntimeError, match="条目写入失败"):
        planning.create_checklist(
            ChecklistWithItemsCreate(title="出国必备", items=["护照"]),
            SimpleNamespace(id=uuid4()),
            session,
        )
    assert session.commits == 0
