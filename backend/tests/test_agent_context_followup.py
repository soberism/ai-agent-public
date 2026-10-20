from backend.features.assistant.autonomous_types import AutonomousContext
from backend.features.assistant.autonomous_workflow import run


def test_short_meal_followup_does_not_reuse_older_checklist():
    history = [
        {"role": "assistant", "content": "之前已创建同学录清单。"},
        {"role": "user", "content": "有什么菜单"},
        {
            "role": "assistant",
            "content": "目前没有餐食计划。请告诉我要在哪天、吃哪一餐、想吃什么。",
        },
    ]

    def unexpected_decision(_state):
        raise AssertionError("缺少餐食信息时不应生成操作计划")

    result = run(
        "创建一个吧",
        AutonomousContext(unexpected_decision, lambda *_args: None),
        history=history,
    )

    assert result["final_answer"] == "可以，请告诉我想安排哪一天、哪一餐、吃什么。"
    assert result["proposed_actions"] == []
