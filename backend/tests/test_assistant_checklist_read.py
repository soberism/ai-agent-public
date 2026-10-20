import json
from types import SimpleNamespace
from uuid import uuid4

from backend.api.routes import assistant_read_steps


def test_assistant_reads_all_checklist_items(monkeypatch):
    checklist_id = uuid4()
    items = [{"title": f"旅行用品{index:02d}"} for index in range(35)]
    monkeypatch.setattr(
        assistant_read_steps,
        "prepare",
        lambda *_: ({"checklist_id": str(checklist_id)}, {}),
    )
    monkeypatch.setattr(
        assistant_read_steps,
        "get_checklist",
        lambda *_: SimpleNamespace(
            model_dump=lambda **_: {"total_count": 35, "items": items}
        ),
    )

    result = json.loads(
        assistant_read_steps.inspect(
            "get_checklist", {"checklist_id": "旅行准备"}, None, None, None, uuid4()
        )
    )

    assert result["total_count"] == 35
    assert len(result["items"]) == 35
    assert result["items"][-1]["title"] == "旅行用品34"


def test_checklist_listing_does_not_pass_a_truncated_item_summary(monkeypatch):
    checklist_id = uuid4()
    checklist = SimpleNamespace(
        id=checklist_id,
        title="旅行准备",
        total_count=35,
        completed_count=0,
        items=[{"title": "不应作为完整清单内容"}],
    )
    monkeypatch.setattr(
        assistant_read_steps,
        "list_checklists",
        lambda *_: SimpleNamespace(items=[checklist]),
    )

    result = json.loads(
        assistant_read_steps.inspect("list_checklists", {}, None, None, None, uuid4())
    )

    assert result == {
        "complete": True,
        "total_count": 1,
        "items": [
            {
                "id": str(checklist_id),
                "title": "旅行准备",
                "total_count": 35,
                "completed_count": 0,
            }
        ],
    }
