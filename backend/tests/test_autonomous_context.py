import json
from types import SimpleNamespace

from pydantic import SecretStr

from backend.features.assistant import autonomous_model
from backend.features.assistant.autonomous_workflow import initial_state
from backend.features.assistant.model_input import build_model_input


def test_every_turn_gets_bounded_recent_history_without_automatic_long_term_memory(
    monkeypatch,
):
    seen = []

    def create(**kwargs):
        seen.append(kwargs["messages"])
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        tool_calls=[
                            SimpleNamespace(
                                function=SimpleNamespace(
                                    name="agent_decision",
                                    arguments=json.dumps(
                                        {
                                            "action": "final_answer",
                                            "answer_kind": "conversation",
                                            "answer": "你好",
                                        }
                                    ),
                                )
                            )
                        ]
                    )
                )
            ]
        )

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    monkeypatch.setattr(autonomous_model, "client", lambda: client)
    monkeypatch.setattr(
        autonomous_model.settings, "llm_base_url", "https://example.test/v1"
    )
    monkeypatch.setattr(autonomous_model.settings, "llm_model", "test")
    monkeypatch.setattr(autonomous_model.settings, "llm_api_key", SecretStr("test-key"))

    state = initial_state(
        "明天有什么安排",
        history=[{"role": "user", "content": f"第{i}条历史"} for i in range(25)],
        timezone="Asia/Shanghai",
        custom_instructions="称呼我小周",
        memories=["喜欢早起"],
        last_results=[{"title": "跑步", "status": "ongoing"}],
    )
    assert autonomous_model.decide(state).answer == "你好"
    assert len(seen[0]) == 15
    assert seen[0][-1]["content"] == state["prompt"]
    prompt = seen[0][-2]["content"]
    assert "用户时区" in prompt and "Asia/Shanghai" in prompt
    assert "称呼我小周" in prompt
    assert "喜欢早起" not in prompt
    assert "跑步" in prompt
    assert "第0条历史" not in prompt


def test_reference_input_keeps_both_speakers_as_context_with_separate_current_evidence():
    state = initial_state(
        "第二条呢",
        history=[
            {"role": "user", "content": "查看今天的待办"},
            {"role": "assistant", "content": "今天有两条待办，第二条是买牛奶。"},
        ],
        last_results=[{"index": 2, "id": "todo-id", "title": "买牛奶"}],
    )
    messages = build_model_input(state, "reason")
    assert [item["role"] for item in messages] == ["user", "assistant", "user", "user"]
    assert messages[0]["content"] == "查看今天的待办"
    assert "第二条是买牛奶" in str(messages)
    assert "不是当前业务事实" in messages[-2]["content"]
    assert "todo-id" in messages[-2]["content"]
