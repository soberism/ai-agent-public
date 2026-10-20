import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.core.security import APIError
from backend.features.assistant import autonomous_model
from backend.features.assistant.autonomous_types import initial_state


def response(arguments, name="agent_decision"):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    tool_calls=[
                        SimpleNamespace(
                            function=SimpleNamespace(name=name, arguments=arguments)
                        )
                    ]
                )
            )
        ]
    )


def client(monkeypatch, responses):
    create = Mock(side_effect=responses)
    monkeypatch.setattr(
        autonomous_model,
        "settings",
        SimpleNamespace(
            llm_base_url="https://example.com",
            llm_model="test",
            llm_api_key=SimpleNamespace(get_secret_value=lambda: "test"),
        ),
    )
    monkeypatch.setattr(
        autonomous_model,
        "client",
        lambda: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        ),
    )
    return create


def test_invalid_decision_has_one_bounded_repair_and_keeps_write_as_proposal(
    monkeypatch,
):
    valid = {
        "action": "propose_actions",
        "answer_kind": "conversation",
        "actions": [
            {"tool_name": "create_todo", "arguments": {"body": {"title": "换盆"}}}
        ],
    }
    create = client(monkeypatch, [response("{"), response(json.dumps(valid))])
    result = autonomous_model.decide(initial_state("明天提醒我换盆"))
    assert result.action == "propose_actions" and result.actions == valid["actions"]
    assert create.call_count == 2
    assert (
        create.call_args.kwargs["tool_choice"]["function"]["name"] == "agent_decision"
    )


def test_repeated_invalid_decision_stops_without_executing_unknown_tool(monkeypatch):
    create = client(monkeypatch, [response("{}", "unknown_write"), response("{}")])
    with pytest.raises(APIError, match="无效的自主决策"):
        autonomous_model.decide(initial_state("创建待办"))
    assert create.call_count == 2
