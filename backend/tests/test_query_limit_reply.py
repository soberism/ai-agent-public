"""预算停止时给出可行动提示，不虚构数据量，也不继续读写。"""

from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

import pytest

from backend.features.assistant.autonomous_reason import reason
from backend.features.assistant.autonomous_types import (
    AutonomousContext,
    Decision,
    initial_state,
)
from backend.features.assistant.autonomous_workflow import read, retrieve


@pytest.mark.parametrize("node", [reason, read])
def test_event_budget_reply_explains_incomplete_query_and_next_step(node):
    def forbidden(*args):
        pytest.fail("预算耗尽后不应调用模型或读取数据")

    state = initial_state("全部时间日程呢额")
    state["decision"] = Decision(
        action="read_api", tool_name="list_all_events"
    ).model_dump()
    context = AutonomousContext(forbidden, forbidden, max_iterations=0, max_reads=0)
    result = node(state, SimpleNamespace(context=context))
    answer = result["final_answer"]
    assert "没能完成日程查询" in answer and "再试一次" in answer
    assert "本月" in answer and "下个月" in answer
    assert all(word not in answer for word in ["自主", "上限", "太多", "50", "日程0项"])
    assert not result["decision"]["claims"] and not result["decision"]["actions"]


def test_generic_and_knowledge_limits_have_relevant_next_steps():
    context = AutonomousContext(
        lambda _: None, lambda *_: {}, max_iterations=0, max_knowledge=0
    )
    state = initial_state("解释一个概念")
    answer = reason(state, SimpleNamespace(context=context))["final_answer"]
    assert "最想先确认的那一项" in answer and "本月" not in answer
    state = initial_state("查询材料")
    answer = retrieve(state, SimpleNamespace(context=context))["final_answer"]
    assert "资料名称" in answer and "完整答案" in answer and "上限" not in answer


@pytest.mark.parametrize(
    "answer",
    [
        "这次没能完成日程查询。可以再试一次；也可以先查“本月”或“下个月”的安排。",
        "这次没能完成查询。可以再试一次，或告诉我最想先确认的那一项。",
        "这次还没能整理出资料中的完整答案。可以再试一次，或告诉我具体的资料名称和想查的内容。",
    ],
)
def test_friendlier_fallback_still_counts_as_unanswered_in_evaluation(answer):
    structural_check = run_path(
        str(Path(__file__).parents[1] / "infra/assistant_eval.py")
    )["structural_check"]
    assert not structural_check(
        {"expect": {"outcome": "answer"}},
        {"status": "completed", "final_answer": answer},
    )


@pytest.mark.parametrize(
    "tool",
    [
        "list_todos",
        "list_meals",
        "list_shopping",
        "list_households",
        "list_memories",
        "list_materials",
        "list_reminders",
        "get_settings",
    ],
)
def test_non_calendar_domains_use_generic_actionable_reply(tool):
    def forbidden(*args):
        pytest.fail("耗尽后不应继续读取")

    state = initial_state("查询现有记录")
    state["decision"] = Decision(action="read_api", tool_name=tool).model_dump()
    result = read(
        state,
        SimpleNamespace(context=AutonomousContext(forbidden, forbidden, max_reads=0)),
    )
    answer = result["final_answer"]
    assert "没能完成查询" in answer and "再试一次" in answer
    assert all(
        word not in answer for word in ["本月", "日程", "没有数据", "不支持", tool]
    )
