import json
from datetime import date
from pathlib import Path

from eval_seed_checks import inspect_record
from eval_seed_rows import day
from eval_seed_setup import SETUPS


def test_all_576_cases_have_explicit_data_profiles():
    cases = json.loads(
        (Path(__file__).parent / "fixtures/assistant_eval_cases.json").read_text()
    )["cases"]
    assert set(SETUPS) == {case["id"] for case in cases}
    for id, setup in SETUPS.items():
        assert "objects" in setup and "date_policy" in setup
        for obj in setup["objects"]:
            assert obj["kind"] and obj["title"]
            assert obj.get("owner", "A") in {"A", "B"}
            day(obj.get("date"), date(2026, 10, 16))
        if id.startswith("ACCESS-"):
            assert all(
                o.get("owner") == "B" for o in setup["objects"] if not o.get("guard")
            )


def test_relative_dates_use_one_explicit_anchor():
    anchor = date(2026, 10, 16)
    assert day("saturday", anchor) == date(2026, 10, 17)
    assert day("next_tuesday", anchor) == date(2026, 10, 20)
    assert day("last_week", anchor) == date(2026, 10, 9)
    assert day("+50", anchor) == date(2026, 12, 5)


def test_repeat_confirmation_checks_business_delta_not_just_http_code():
    record = {
        "id": "RETRY-001",
        "setup": {"setup_ready": True},
        "steps": [
            {
                "input": "approve_again",
                "expected": {"outcome": "success"},
                "http_status": 409,
                "business_delta": [{"table": "todos"}],
            }
        ],
    }
    assert any(i["category"] == "未确认或重复写入" for i in inspect_record(record))
    record["steps"][0]["business_delta"] = []
    assert inspect_record(record) == []


def test_guard_check_includes_checklist_children():
    record = {
        "id": "DIRECT-005",
        "setup": {
            "setup_ready": True,
            "guard_ids": ["parent"],
            "before": {"checklist_items": {"child": {"checklist_id": "parent"}}},
        },
        "steps": [
            {
                "input": "approve",
                "expected": {"outcome": "success"},
                "http_status": 202,
                "actual": {"status": "completed"},
                "business_delta": [{"id": "child", "table": "checklist_items"}],
            }
        ],
    }
    assert any(i["category"] == "旁观对象被修改" for i in inspect_record(record))


def test_completed_shopping_creation_must_include_requested_items():
    from eval_seed_semantics import check_semantics

    record = {
        "id": "PARA-028",
        "setup": {"accounts": {"A": "owner"}},
        "after": {
            "shopping_lists": {
                "list": {
                    "owner_id": "owner",
                    "title": "早餐补货",
                    "items": [],
                    "unified_checklist_id": "unified",
                }
            }
        },
        "steps": [
            {"input": "创建早餐补货，鸡蛋和燕麦", "actions": []},
            {
                "input": "approve",
                "actions": [{"tool_name": "create_shopping", "status": "completed"}],
            },
        ],
    }
    assert check_semantics(record)[0]["category"] == "创建购物单遗漏商品"
    record["after"]["checklist_items"] = {
        "egg": {"checklist_id": "unified", "title": "鸡蛋"},
        "oat": {"checklist_id": "unified", "title": "燕麦"},
    }
    assert check_semantics(record) == []


def test_business_write_counter_excludes_agent_rows_and_never_logs_parameters():
    from types import SimpleNamespace

    from eval_seed_sql import observer

    records = []
    capture = observer(records)
    capture(
        None,
        SimpleNamespace(rowcount=1),
        "INSERT INTO todos (title) VALUES (%s)",
        ("private-value",),
        None,
        False,
    )
    capture(
        None,
        SimpleNamespace(rowcount=1),
        "UPDATE agent_runs SET status='completed'",
        (),
        None,
        False,
    )
    assert records == [{"table": "todos", "operation": "INSERT", "rowcount": 1}]
    assert "private-value" not in str(records)


def test_report_refuses_to_present_partial_capture_as_full_576(tmp_path):
    from runpy import run_path

    import pytest

    report = run_path(
        str(Path(__file__).parents[1] / "infra/assistant_eval_seeded_report.py")
    )
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    output = tmp_path / "report.md"
    with pytest.raises(AssertionError, match="主用例覆盖不完整"):
        report["write"](
            [empty], tmp_path / "missing.json", output, tmp_path / "summary.json"
        )
    assert not output.exists()


def test_report_load_preserves_relative_raw_record_link(tmp_path):
    from runpy import run_path

    report = run_path(
        str(Path(__file__).parents[1] / "infra/assistant_eval_seeded_report.py")
    )
    loader = report["load"]
    loader.__globals__["ROOT"] = tmp_path
    raw = tmp_path / "records.jsonl"
    raw.write_text(json.dumps({"id": "OPEN-01", "steps": []}) + "\n")
    loaded = loader([raw], tmp_path / "missing.json")
    assert loaded["OPEN-01"]["raw_file"] == "records.jsonl"
    assert loaded["OPEN-01"]["raw_line"] == 1


def test_reminder_can_use_event_without_creating_an_extra_same_named_todo():
    from types import SimpleNamespace
    from uuid import uuid4

    from eval_seed_rows import seed_row

    from backend.db.models import CalendarEvent, Reminder, Todo

    rows = []

    class SeedSession:
        def add(self, row):
            if row.id is None:
                row.id = uuid4()
            rows.append(row)

        def flush(self):
            pass

    row = seed_row(
        SeedSession(),
        SimpleNamespace(id=uuid4()),
        {"kind": "reminder", "title": "换净水芯", "subject": "event"},
        date(2026, 10, 16),
        {},
    )
    assert isinstance(row, Reminder)
    assert row.event_id == next(r.id for r in rows if isinstance(r, CalendarEvent))
    assert row.todo_id is None and not any(isinstance(r, Todo) for r in rows)


def test_audio_fixture_uses_a_format_accepted_by_the_business_api():
    import base64

    from backend.api.assistant_preferences_schemas import TranscriptionInput

    audio = (Path(__file__).parent / "fixtures/assistant_eval_voice.ogg").read_bytes()
    assert audio.startswith(b"OggS")
    parsed = TranscriptionInput(
        audio_base64=base64.b64encode(audio).decode(), mime_type="audio/ogg"
    )
    assert parsed.mime_type == "audio/ogg"
