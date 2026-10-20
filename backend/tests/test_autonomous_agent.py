from collections import deque

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from pydantic import ValidationError

from backend.features.assistant import autonomous_workflow
from backend.features.assistant.autonomous_model import parse_decision
from backend.features.assistant.autonomous_types import AutonomousContext, Decision
from backend.features.assistant.autonomous_workflow import initial_state, run
from backend.features.assistant.tool_registry import describe, search


class Decisions:
    def __init__(self, *values):
        self.values = deque(values)

    def __call__(self, state):
        return self.values.popleft()


def test_model_tool_name_action_is_normalized_only_for_discovered_reads():
    state = initial_state("查看清单")
    state["discovered_tools"] = [
        {"name": "list_checklists", "mode": "read"},
        {"name": "create_checklist", "mode": "write"},
    ]

    decision = parse_decision('{"action":"list_checklists"}', state)

    assert decision.action == "read_api"
    assert decision.tool_name == "list_checklists"
    with pytest.raises(ValidationError):
        parse_decision('{"action":"create_checklist"}', state)
    with pytest.raises(ValidationError):
        parse_decision('{"action":"unknown_tool"}', state)


@pytest.mark.parametrize("alias", ["get_meals", "get_meal_plans"])
def test_menu_read_alias_reaches_meal_reader(alias):
    calls = []
    decision = parse_decision(
        f'{{"action":"read_api","tool_name":"{alias}","arguments":{{}}}}',
        initial_state("现在有什么菜单"),
    )
    result = run(
        "现在有什么菜单",
        AutonomousContext(
            Decisions(
                decision, Decision(action="final_answer", answer="查到今晚的餐食。")
            ),
            lambda name, args: calls.append((name, args)) or {"items": []},
        ),
    )
    assert calls == [("list_meals", {})]
    assert result["final_answer"] == "查到今晚的餐食。"


def test_registry_searches_summaries_and_describes_only_on_demand():
    results = search("查询日程", mode="read")

    assert any(item["name"] == "list_events" for item in results)
    assert all("input_schema" not in item for item in results)
    assert all(item["mode"] == "read" for item in results)
    assert describe("list_events")["input_schema"]["required"] == ["query"]


def test_autonomous_loop_discovers_describes_reads_and_answers():
    calls = []
    decisions = Decisions(
        Decision(action="search_tools", query="账号设置"),
        Decision(action="describe_tools", names=["get_settings"]),
        Decision(action="read_api", tool_name="get_settings", arguments={}),
        Decision(action="final_answer", answer="当前时区是 Asia/Shanghai。"),
    )

    def reader(name, arguments):
        calls.append((name, arguments))
        return {"timezone": "Asia/Shanghai"}

    result = run("我的时区是什么？", AutonomousContext(decisions, reader))

    assert calls == [("get_settings", {})]
    assert result["read_count"] == 1
    assert result["observations"][0]["result"]["timezone"] == "Asia/Shanghai"
    assert result["final_answer"] == "当前时区是 Asia/Shanghai。"


def test_discovered_read_is_described_before_execution():
    decisions = Decisions(
        Decision(action="search_tools", query="账号设置"),
        Decision(action="read_api", tool_name="get_settings", arguments={}),
        Decision(action="final_answer", answer="已查到账号设置。"),
    )
    calls = []

    result = run(
        "我的账号设置是什么？",
        AutonomousContext(decisions, lambda name, args: calls.append(name) or {}),
    )

    assert calls == ["get_settings"]
    assert result["read_count"] == 1
    assert any(item["name"] == "get_settings" for item in result["described_tools"])


def test_autonomous_loop_rejects_undiscovered_tools():
    calls = []
    undiscovered = Decisions(
        Decision(action="search_tools", query="账号设置"),
        Decision(action="describe_tools", names=["list_events"]),
    )
    result = run(
        "账号设置", AutonomousContext(undiscovered, lambda *_: calls.append(1))
    )
    assert "没能完成查询" in result["final_answer"]
    assert calls == []


def test_empty_search_stops_and_repeated_search_can_recover():
    empty = run(
        "无效工具",
        AutonomousContext(
            Decisions(
                Decision(action="search_tools", query="zzzzzz_unknown_capability")
            ),
            lambda *_: {},
        ),
    )
    assert "没能找到合适" in empty["final_answer"]
    assert empty["iteration"] == 1

    repeated = run(
        "查询设置",
        AutonomousContext(
            Decisions(
                *(Decision(action="search_tools", query="账号设置") for _ in range(3)),
                Decision(action="final_answer", answer="请说明要查看哪项设置。"),
            ),
            lambda *_: {},
        ),
    )
    assert repeated["final_answer"] == "请说明要查看哪项设置。"
    assert repeated["iteration"] == 4
    assert repeated["read_count"] == 0


def test_discovered_write_cannot_be_used_as_read():
    calls = []
    result = run(
        "修改昵称",
        AutonomousContext(
            Decisions(
                Decision(action="search_tools", query="修改昵称"),
                Decision(action="read_api", tool_name="set_settings", arguments={}),
                Decision(action="final_answer", answer="请确认要修改的昵称。"),
            ),
            lambda *_: calls.append(1),
        ),
    )
    assert result["final_answer"] == "请确认要修改的昵称。"
    assert calls == []


def test_autonomous_loop_stops_duplicate_reads_and_budgets():
    calls = []
    duplicate = Decisions(
        Decision(action="search_tools", query="账号设置"),
        Decision(action="describe_tools", names=["get_settings"]),
        Decision(action="read_api", tool_name="get_settings", arguments={}),
        Decision(action="read_api", tool_name="get_settings", arguments={}),
        Decision(action="final_answer", answer="设置已读取。"),
    )

    result = run(
        "重复查询",
        AutonomousContext(duplicate, lambda *args: calls.append(args) or {}),
    )
    assert result["final_answer"] == "设置已读取。"
    assert len(calls) == 1

    budget = Decisions(Decision(action="search_tools", query="账号设置"))
    result = run(
        "预算",
        AutonomousContext(budget, lambda *_: {}, max_iterations=0),
    )
    assert "这次没能完成查询" in result["final_answer"]


def test_autonomous_loop_retrieves_knowledge_and_proposes_writes():
    decisions = Decisions(
        Decision(action="retrieve_knowledge", query="保单号码"),
        Decision(action="search_tools", query="修改昵称"),
        Decision(action="describe_tools", names=["set_settings"]),
        Decision(
            action="propose_actions",
            actions=[
                {
                    "tool_name": "set_settings",
                    "arguments": {"body": {"nickname": "小安"}},
                    "description": "把昵称改成小安",
                }
            ],
        ),
    )
    saver = InMemorySaver()
    config = {"configurable": {"thread_id": "test-plan"}}
    result = run(
        "查保单并改昵称",
        AutonomousContext(
            decisions,
            lambda *_: {},
            retriever=lambda query: [{"title": "保单", "content": query}],
        ),
        checkpointer=saver,
        config=config,
    )

    assert result["knowledge"][0]["title"] == "保单"
    assert result["__interrupt__"][0].value["kind"] == "action_plan"

    resumed = run(
        "查保单并改昵称",
        AutonomousContext(decisions, lambda *_: {}),
        checkpointer=saver,
        config=config,
        command=Command(resume={"approved": True}),
    )
    assert resumed["approval"] == {"approved": True}
    assert resumed["proposed_actions"][0]["tool_name"] == "set_settings"


def test_knowledge_budget_stops_before_another_retrieval():
    calls = []
    result = run(
        "查文档",
        AutonomousContext(
            Decisions(
                Decision(action="retrieve_knowledge", query="一"),
                Decision(action="retrieve_knowledge", query="二"),
            ),
            lambda *_: {},
            retriever=lambda query: calls.append(query) or [{"content": query}],
            max_knowledge=1,
        ),
    )
    assert calls == ["一"]
    assert result["knowledge_count"] == 1
    assert "资料中的完整答案" in result["final_answer"]


def test_public_web_search_keeps_server_owned_sources_and_stops_second_search(
    monkeypatch,
):
    searches = []
    monkeypatch.setattr(
        autonomous_workflow,
        "search_web",
        lambda args: (
            searches.append(args)
            or [
                {
                    "title": "出行",
                    "url": "https://example.com/travel",
                    "content": "护照",
                }
            ]
        ),
    )
    result = run(
        "联网查出行建议",
        AutonomousContext(
            Decisions(
                Decision(action="web_search", query="出行建议"),
                Decision(action="final_answer", answer="出行带好护照。"),
            ),
            lambda *_: {},
        ),
    )
    assert searches == [{"query": "出行建议"}]
    assert result["web_results"][0]["url"] == "https://example.com/travel"
    assert result["final_answer"] == "出行带好护照。"

    repeated = run(
        "联网查出行建议",
        AutonomousContext(
            Decisions(
                Decision(action="web_search", query="出行建议"),
                Decision(action="web_search", query="再查一次"),
                Decision(action="final_answer", answer="请参考已有搜索结果。"),
            ),
            lambda *_: {},
        ),
    )
    assert repeated["final_answer"] == "请参考已有搜索结果。"
    assert len(searches) == 2


def test_web_search_can_rebuild_a_pending_checklist_without_internal_read(monkeypatch):
    monkeypatch.setattr(
        autonomous_workflow,
        "search_web",
        lambda _: [
            {
                "title": "旅行准备",
                "url": "https://example.com/travel",
                "content": "建议携带转换插头",
            }
        ],
    )
    decisions = Decisions(
        Decision(action="web_search", query="旅行准备清单"),
        Decision(action="read_api", tool_name="get_checklist", arguments={}),
        Decision(
            action="propose_actions",
            actions=[
                {
                    "tool_name": "create_checklist",
                    "arguments": {
                        "body": {
                            "title": "旅行准备清单",
                            "items": ["证件与钱包", "转换插头"],
                        }
                    },
                }
            ],
        ),
    )
    result = run(
        "参考网上信息补充尚未创建的旅行准备清单",
        AutonomousContext(
            decisions,
            lambda *_: (_ for _ in ()).throw(AssertionError("不应读取应用内数据")),
        ),
        checkpointer=InMemorySaver(),
        config={"configurable": {"thread_id": "web-checklist-revision"}},
    )

    plan = result["__interrupt__"][0].value["actions"]
    assert plan[0]["tool_name"] == "create_checklist"
    assert plan[0]["arguments"]["body"]["items"][-1] == "转换插头"


def test_web_search_rejects_private_terms_and_internal_data(monkeypatch):
    searches = []
    monkeypatch.setattr(
        autonomous_workflow, "search_web", lambda args: searches.append(args)
    )
    result = run(
        "联网查我的邮箱",
        AutonomousContext(
            Decisions(Decision(action="web_search", query="me@example.com")),
            lambda *_: {},
        ),
    )
    assert "私人信息" in result["final_answer"] and not searches

    result = run(
        "先看我的待办再联网搜索",
        AutonomousContext(
            Decisions(
                Decision(action="retrieve_knowledge", query="待办"),
                Decision(action="web_search", query="待办建议"),
            ),
            lambda *_: {},
            retriever=lambda _: [{"content": "私人待办"}],
        ),
    )
    assert "应用内数据" in result["final_answer"] and not searches
