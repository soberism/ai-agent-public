from backend.features.assistant import autonomous_workflow
from backend.features.assistant.autonomous_types import Decision, initial_state


def test_public_realtime_question_does_not_require_magic_network_keywords(monkeypatch):
    state = initial_state("今天上海空气质量是多少？")
    state["decision"] = Decision(
        action="web_search", query="上海 空气质量 今天"
    ).model_dump()
    calls = []
    monkeypatch.setattr(
        autonomous_workflow,
        "search_web",
        lambda args: (
            calls.append(args)
            or [
                {
                    "title": "公开资料",
                    "url": "https://example.com",
                    "content": "未提供实时数据",
                }
            ]
        ),
    )
    assert autonomous_workflow.web_search(state)["web_results"]
    assert calls == [{"query": "上海 空气质量 今天"}]
    state["observations"] = [{"result": {"title": "私有事项"}}]
    assert "不能将应用内数据" in autonomous_workflow.web_search(state)["final_answer"]
    assert len(calls) == 1
    state["observations"] = []
    state["decision"]["query"] = "someone@example.com 的资料"
    assert "私人信息" in autonomous_workflow.web_search(state)["final_answer"]
    assert len(calls) == 1


def test_web_without_a_verified_claim_explains_the_realtime_limit():
    from backend.features.assistant.answer_guard import guard_decision

    state = initial_state("今天上海空气质量是多少？如果没有实时来源请直说。")
    state["web_results"] = [
        {"title": "不相关公开页面", "content": "旅游资讯", "url": "https://example.com"}
    ]
    state["claim_retries"] = 1
    decision = guard_decision(
        state,
        Decision(action="final_answer", answer_kind="document", answer="空气质量42。"),
    )
    assert "没能从网上核实" in decision.answer and "实时" in decision.answer
    assert "42" not in decision.answer
