from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from backend.features.assistant.agent_lifecycle import finish
from backend.features.assistant.agent_plan_results import result_items
from backend.features.assistant.history import output


def test_only_completed_action_items_are_deduplicated_and_survive_history_reload():
    item = {
        "id": str(uuid4()),
        "kind": "checklist",
        "title": "出行准备",
        "url": "/checklists/example",
        "status": "active",
        "due_date": None,
        "due_time": None,
    }
    actions = [
        SimpleNamespace(status="completed", result={"items": [item]}),
        SimpleNamespace(status="completed", result={"items": [item]}),
        SimpleNamespace(status="failed", result={"items": [{**item, "id": "failed"}]}),
        SimpleNamespace(
            status="cancelled", result={"items": [{**item, "id": "cancelled"}]}
        ),
    ]
    items = result_items(actions)
    assert items == [item]
    session = Mock()
    session.get.return_value = None
    run = SimpleNamespace(
        id=uuid4(),
        status="running",
        progress=None,
        history_saved=False,
        thread_id=uuid4(),
    )
    finish(
        session, run, "completed", "已创建清单，包含2项。", kind="result", items=items
    )
    saved = session.add.call_args.args[0]
    assert saved.items == [item]
    assert output([saved])[0]["reply"]["items"] == [item]
