from types import SimpleNamespace

from pydantic import SecretStr

from backend.features.assistant import graph


def setup_model(monkeypatch, outputs):
    seen = []
    calls = iter(outputs)

    def create(**kwargs):
        seen.append(kwargs["messages"])
        name, arguments = next(calls)
        if name is None:
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=arguments, tool_calls=[])
                    )
                ]
            )
        if isinstance(name, list):
            tool_calls = [
                SimpleNamespace(function=SimpleNamespace(name=n, arguments=a))
                for n, a in zip(name, arguments, strict=True)
            ]
        else:
            tool_calls = [
                SimpleNamespace(
                    function=SimpleNamespace(name=name, arguments=arguments)
                )
            ]
        message = SimpleNamespace(
            content=None,
            tool_calls=tool_calls,
        )
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    monkeypatch.setattr(graph, "OpenAI", lambda **_: client)
    monkeypatch.setattr(graph.settings, "llm_base_url", "https://example.test/v1")
    monkeypatch.setattr(graph.settings, "llm_model", "test-model")
    monkeypatch.setattr(graph.settings, "llm_api_key", SecretStr("test-key"))
    return seen


def test_reads_before_one_confirmed_write(monkeypatch):
    seen = setup_model(
        monkeypatch,
        [
            (
                "inspect_before_action",
                '{"feature":"list_events","payload":{"query":{"date_from":"2026-09-21","date_to":"2026-09-27"}}}',
            ),
            (
                "feature_create_event",
                '{"body":{"title":"聚餐","start_date":"2026-09-23","start_time":"19:00","end_date":"2026-09-23","end_time":"21:00"}}',
            ),
        ],
    )
    reads = []
    intent = graph.interpret(
        "看看这周日程，找个晚上安排聚餐",
        reader=lambda name, payload: (
            reads.append((name, payload))
            or '{"items":[],"message":"本周没有已安排日程"}'
        ),
    )
    assert intent.action == "feature" and intent.feature == "create_event"
    assert len(reads) == 1 and reads[0][0] == "list_events"
    assert "本周没有已安排日程" in seen[1][-1]["content"]


def test_read_loop_is_bounded(monkeypatch):
    setup_model(
        monkeypatch,
        [("inspect_before_action", '{"feature":"list_events","payload":{}}')] * 5,
    )
    reads = []
    intent = graph.interpret(
        "安排日程", reader=lambda name, payload: reads.append(name) or "{}"
    )
    assert intent.action == "clarify"
    assert len(reads) == 1


def test_write_cannot_be_disguised_as_read(monkeypatch):
    setup_model(
        monkeypatch,
        [("inspect_before_action", '{"feature":"create_event","payload":{}}')],
    )
    intent = graph.interpret("先创建日程再看看", reader=lambda *_: "{}")
    assert intent.action == "clarify"


def test_parallel_read_calls_are_synthesized(monkeypatch):
    seen = setup_model(
        monkeypatch,
        [
            (
                ["feature_list_households", "feature_list_events"],
                ["{}", '{"query":{"date_from":"2026-09-21","date_to":"2026-09-27"}}'],
            ),
            (None, "仅能根据你可见的日程判断，无法确认成员私人安排。"),
        ],
    )
    reads = []
    intent = graph.interpret(
        "看看我爱我家的家庭成员这周空闲时间",
        reader=lambda name, payload: reads.append(name) or '{"items":[]}',
    )
    assert intent.action == "respond"
    assert reads == ["list_households", "list_events"]
    assert "list_households" in seen[1][-1]["content"]
    assert "list_events" in seen[1][-1]["content"]


def test_parallel_batch_with_write_is_rejected(monkeypatch):
    setup_model(
        monkeypatch,
        [(["feature_list_events", "feature_create_event"], ["{}", "{}"])],
    )
    reads = []
    intent = graph.interpret(
        "同时查询并创建", reader=lambda name, payload: reads.append(name) or "{}"
    )
    assert intent.action == "clarify"
    assert reads == []


def test_removal_request_keeps_reading_until_members_are_listed(monkeypatch):
    setup_model(
        monkeypatch,
        [
            ("feature_list_households", "{}"),
            ("feature_get_household", '{"household_id":"我爱我家"}'),
            (None, "我爱我家可移出的成员是张三。要移出哪位？"),
        ],
    )
    reads = []
    intent = graph.interpret(
        "我想删除我爱我家的家庭成员",
        reader=lambda name, payload: reads.append((name, payload)) or "{}",
    )
    assert intent.action == "respond"
    assert [name for name, _ in reads] == ["list_households", "get_household"]


def test_selected_member_leads_to_confirmed_write_intent(monkeypatch):
    setup_model(
        monkeypatch,
        [
            ("feature_get_household", '{"household_id":"我爱我家"}'),
            (
                "feature_edit_member",
                '{"household_id":"我爱我家","member_id":"张三","body":{"status":"removed"}}',
            ),
        ],
    )
    reads = []
    intent = graph.interpret(
        "张三",
        history=[
            {"role": "user", "content": "我想删除我爱我家的家庭成员"},
            {
                "role": "assistant",
                "content": "我爱我家可移出的成员是张三。你想移出的是张三吗？",
            },
        ],
        reader=lambda name, payload: reads.append((name, payload)) or "{}",
    )
    assert reads == [("get_household", {"household_id": "我爱我家"})]
    assert intent.action == "feature" and intent.feature == "edit_member"
    assert intent.payload["body"] == {"status": "removed"}


def test_completed_todo_query_does_not_enter_write_discovery(monkeypatch):
    setup_model(monkeypatch, [("query_todos", '{"status":"completed"}')])
    intent = graph.interpret(
        "我有哪些已完成的待办？",
        reader=lambda *_: (_ for _ in ()).throw(AssertionError("不应重复查询")),
    )
    assert intent.action == "query_todos"
