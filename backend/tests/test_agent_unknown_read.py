from collections import deque

from backend.features.assistant.autonomous_types import AutonomousContext, Decision
from backend.features.assistant.autonomous_workflow import run


def test_unknown_read_can_recover_with_existing_checklist_tool():
    decisions = deque(
        [
            Decision(action="read_api", tool_name="list_deleted_checklists"),
            Decision(action="search_tools", query="查询清单"),
            Decision(action="read_api", tool_name="list_checklists"),
            Decision(
                action="final_answer", answer="没有找到同学录；当前没有撤销删除功能。"
            ),
        ]
    )
    calls = []
    result = run(
        "我误删了同学录，能恢复吗",
        AutonomousContext(
            lambda _state: decisions.popleft(),
            lambda name, _args: calls.append(name) or {"items": []},
        ),
    )

    assert result["final_answer"] == "没有找到同学录；当前没有撤销删除功能。"
    assert calls == ["list_checklists"]
