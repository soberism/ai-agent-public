from langgraph.checkpoint.memory import InMemorySaver

from backend.features.assistant.autonomous_types import AutonomousContext, Decision
from backend.features.assistant.autonomous_workflow import run


def test_email_followup_recovers_invite_alias_and_requires_household():
    choices = iter(
        [
            Decision(
                action="propose_actions",
                actions=[
                    {
                        "tool_name": "invite_family_member",
                        "arguments": {"email": "person@example.com", "role": "member"},
                    }
                ],
            ),
            Decision(action="read_api", tool_name="list_households", arguments={}),
            Decision(
                action="propose_actions",
                actions=[
                    {
                        "tool_name": "invite_member",
                        "arguments": {
                            "household_id": "我们家",
                            "body": {"email": "person@example.com"},
                        },
                    }
                ],
            ),
        ]
    )
    stalled = []

    def decide(state):
        stalled.append(state["stalled_on"])
        return next(choices)

    result = run(
        "person@example.com",
        AutonomousContext(decide, lambda *_: {"items": [{"name": "我们家"}]}),
        checkpointer=InMemorySaver(),
        config={"configurable": {"thread_id": "invite-followup"}},
    )
    assert stalled[1].startswith("invalid-plan:invite_member")
    assert (
        result["__interrupt__"][0].value["actions"][0]["tool_name"] == "invite_member"
    )
