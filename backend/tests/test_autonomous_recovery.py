from collections import deque

from langgraph.checkpoint.memory import InMemorySaver

from backend.features.assistant.autonomous_guards import oversized_checklist, preflight
from backend.features.assistant.autonomous_types import AutonomousContext, Decision
from backend.features.assistant.autonomous_workflow import run


class Decisions:
    def __init__(self, *values):
        self.values = deque(values)

    def __call__(self, state):
        return self.values.popleft()


def test_registered_read_can_be_validated_without_a_search_step():
    calls = []
    result = run(
        "查看饮食偏好",
        AutonomousContext(
            Decisions(
                Decision(action="read_api", tool_name="list_preferences", arguments={}),
                Decision(action="final_answer", answer="已查到偏好。"),
            ),
            lambda name, args: calls.append(name) or {},
        ),
    )
    assert calls == ["list_preferences"]
    assert result["final_answer"] == "已查到偏好。"


def test_named_todo_detail_retries_when_model_reads_another_todo(monkeypatch):
    from backend.features.assistant import autonomous_guards

    monkeypatch.setattr(autonomous_guards, "same_todo_target", lambda *_: False)
    seen, calls = [], []
    decisions = iter(
        [
            Decision(
                action="read_api",
                tool_name="get_todo",
                arguments={"id": "给植物换盆"},
            ),
            Decision(
                action="read_api",
                tool_name="get_todo",
                arguments={"id": "更换净水滤芯"},
            ),
            Decision(action="final_answer", answer="更换净水滤芯的详情已查到。"),
        ]
    )

    def decide(state):
        seen.append(state)
        return next(decisions)

    def reader(name, args):
        calls.append(args["id"])
        return {"items": [{"title": args["id"]}]}

    result = run(
        "打开“更换净水滤芯”待办，告诉我完整详情。",
        AutonomousContext(decide, reader),
    )

    assert calls == ["给植物换盆", "更换净水滤芯"]
    assert "另一条待办" in seen[1]["stalled_on"]
    assert seen[1]["observations"] == []
    assert result["final_answer"] == "更换净水滤芯的详情已查到。"


def test_named_todo_detail_accepts_semantically_equivalent_title(monkeypatch):
    from backend.features.assistant import autonomous_guards

    monkeypatch.setattr(
        autonomous_guards,
        "same_todo_target",
        lambda requested, actual: requested == "洗牙" and actual == "牙齿清洁",
    )
    for title in ("去洗牙", "牙齿清洁"):
        result = run(
            "打开“洗牙”待办，告诉我完整详情。",
            AutonomousContext(
                Decisions(
                    Decision(
                        action="read_api", tool_name="get_todo", arguments={"id": title}
                    ),
                    Decision(action="final_answer", answer=f"{title}的详情已查到。"),
                ),
                lambda *_, title=title: {"items": [{"title": title}]},
            ),
        )
        assert result["final_answer"] == f"{title}的详情已查到。"


def test_missing_household_id_recovers_by_reading_household_list():
    household_id = "cc2cfa0a-c405-5e38-a8a9-e73e30134524"
    seen, calls = [], []
    decisions = iter(
        [
            Decision(action="read_api", tool_name="get_household", arguments={}),
            Decision(action="read_api", tool_name="list_households", arguments={}),
            Decision(
                action="read_api",
                tool_name="get_household",
                arguments={"household_id": household_id},
            ),
            Decision(action="final_answer", answer="只查到已共享的成员日程。"),
        ]
    )

    def decide(state):
        seen.append(state)
        return next(decisions)

    result = run(
        "yanina_1077这周有啥事吗",
        AutonomousContext(
            decide,
            lambda name, args: calls.append((name, args)) or {"items": []},
        ),
    )
    assert [name for name, _ in calls] == ["list_households", "get_household"]
    assert "household_id" in seen[1]["stalled_on"]
    assert seen[1]["described_tools"][0]["name"] == "get_household"
    assert result["final_answer"] == "只查到已共享的成员日程。"


def test_discovered_write_plan_does_not_require_model_describe_step():
    result = run(
        "修改昵称",
        AutonomousContext(
            Decisions(
                Decision(action="search_tools", query="修改昵称"),
                Decision(
                    action="propose_actions",
                    actions=[
                        {
                            "tool_name": "set_settings",
                            "arguments": {"body": {"nickname": "小安"}},
                        }
                    ],
                ),
            ),
            lambda *_: {},
        ),
        checkpointer=InMemorySaver(),
        config={"configurable": {"thread_id": "auto-describe-write"}},
    )
    assert result["__interrupt__"][0].value["actions"][0]["tool_name"] == "set_settings"


def test_real_write_plan_interrupts_for_approval_without_wording_heuristics():
    result = run(
        "帮我建一个买面包待办",
        AutonomousContext(
            Decisions(
                Decision(
                    action="propose_actions",
                    actions=[
                        {
                            "tool_name": "create_todo",
                            "arguments": {"body": {"title": "买面包"}},
                        }
                    ],
                )
            ),
            lambda *_: {},
        ),
        checkpointer=InMemorySaver(),
        config={"configurable": {"thread_id": "confirmation-plan"}},
    )
    assert result["__interrupt__"]
    assert not result["approval"]


def test_explicitly_oversized_checklist_is_not_silently_truncated():
    actions = [{"tool_name": "create_checklist"}]
    assert oversized_checklist("创建清单，包含六十个条目", actions)
    assert oversized_checklist("创建清单，包含60个条目", actions)
    assert not oversized_checklist("创建清单，包含50个条目", actions)
    result = run(
        "创建清单，包含六十个条目",
        AutonomousContext(Decisions(), lambda *_: {}),
    )
    assert "最多包含 50 个条目" in result["final_answer"]


def test_later_read_search_keeps_earlier_write_candidate():
    result = run(
        "先看明天待办，再创建买面包待办",
        AutonomousContext(
            Decisions(
                Decision(action="search_tools", query="待办 创建待办 查看待办"),
                Decision(action="search_tools", query="查看待办列表 明天待办"),
                Decision(
                    action="propose_actions",
                    actions=[
                        {
                            "tool_name": "create_todo",
                            "arguments": {"body": {"title": "买面包"}},
                        }
                    ],
                ),
            ),
            lambda *_: {},
        ),
        checkpointer=InMemorySaver(),
        config={"configurable": {"thread_id": "preserve-write"}},
    )
    assert result["__interrupt__"][0].value["actions"][0]["tool_name"] == "create_todo"


def test_registered_write_still_requires_confirmation_without_discovery():
    result = run(
        "下个月3号上午十点提醒我给植物换盆",
        AutonomousContext(
            Decisions(
                Decision(
                    action="propose_actions",
                    actions=[
                        {
                            "tool_name": "create_todo",
                            "arguments": {"body": {"title": "给植物换盆"}},
                        }
                    ],
                )
            ),
            lambda *_: {},
        ),
        checkpointer=InMemorySaver(),
        config={"configurable": {"thread_id": "registered-write"}},
    )
    assert result["__interrupt__"][0].value["actions"][0]["tool_name"] == "create_todo"


def test_unregistered_write_is_rejected_without_discovery():
    result = run(
        "执行未知操作",
        AutonomousContext(
            Decisions(
                Decision(
                    action="propose_actions",
                    actions=[{"tool_name": "unknown_write", "arguments": {}}],
                )
            ),
            lambda *_: {},
        ),
    )
    assert "未执行这项操作" in result["final_answer"]
    assert not result.get("proposed_actions")
    assert not result.get("__interrupt__")


def test_conflicting_meeting_time_asks_for_clarification():
    assert "确认" in preflight("昨天上午十点帮我安排一个明天的会")
    assert preflight("把昨天的会改到明天上午十点") is None


def test_invalid_plan_arguments_get_one_schema_guided_retry():
    result = run(
        "修改昵称",
        AutonomousContext(
            Decisions(
                Decision(action="search_tools", query="修改昵称"),
                Decision(
                    action="propose_actions",
                    actions=[
                        {"tool_name": "set_settings", "arguments": {"nickname": "小安"}}
                    ],
                ),
                Decision(
                    action="propose_actions",
                    actions=[
                        {
                            "tool_name": "set_settings",
                            "arguments": {"body": {"nickname": "小安"}},
                        }
                    ],
                ),
            ),
            lambda *_: {},
        ),
        checkpointer=InMemorySaver(),
        config={"configurable": {"thread_id": "retry-plan"}},
    )
    assert result["__interrupt__"][0].value["actions"][0]["arguments"] == {
        "body": {"nickname": "小安"}
    }
