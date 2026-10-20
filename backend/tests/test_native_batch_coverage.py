from copy import deepcopy
from uuid import uuid4

import pytest

from backend.features.assistant import autonomous_plan
from backend.features.assistant.access import observation_references
from backend.features.assistant.autonomous_types import initial_state
from backend.features.assistant.plan_batches import check_batch_coverage

RANGE = {"date_from": "2026-11-01", "date_to": "2026-11-30"}


def event_plan():
    ids = [str(uuid4()) for _ in range(3)]
    state = initial_state("删除11月份所有日程")
    state["observations"] = [
        {
            "tool_name": "list_events",
            "arguments": {"query": RANGE},
            "result": {
                "complete": True,
                "total_count": len(ids),
                "items": [{"id": identifier} for identifier in ids],
            },
        }
    ]
    actions = [
        {
            "tool_name": "delete_events",
            "arguments": {"body": {**RANGE, "event_ids": ids}},
        }
    ]
    return state, actions


@pytest.mark.parametrize(
    "mode",
    ["missing", "duplicate", "extra", "unqueried", "partial", "wrong_range", "failed"],
)
def test_range_delete_rejects_missing_or_unverified_targets(mode):
    state, actions = event_plan()
    assert check_batch_coverage(state, actions) is None
    body = actions[0]["arguments"]["body"]
    if mode == "missing":
        body["event_ids"] = body["event_ids"][:1]
    elif mode == "duplicate":
        body["event_ids"].append(body["event_ids"][0])
    elif mode == "extra":
        body["event_ids"].append(str(uuid4()))
    elif mode == "unqueried":
        state["observations"] = []
    elif mode == "partial":
        state["observations"][0]["result"]["complete"] = False
    elif mode == "wrong_range":
        body["date_to"] = "2026-11-20"
    elif mode == "failed":
        state["observations"][0]["result"]["error"] = "timeout"
    assert check_batch_coverage(state, actions)["stalled_on"].startswith(
        "invalid-plan:"
    )


def test_single_delete_cannot_replace_range_wide_request():
    state, actions = event_plan()
    action = {
        "tool_name": "delete_event",
        "arguments": {"event_id": actions[0]["arguments"]["body"]["event_ids"][0]},
    }
    assert check_batch_coverage(state, [action])


def test_named_subset_delete_is_not_expanded_to_entire_month():
    state, actions = event_plan()
    state["prompt"] = "删除这些日程"
    actions[0]["arguments"]["body"]["event_ids"] = actions[0]["arguments"]["body"][
        "event_ids"
    ][:1]
    assert check_batch_coverage(state, actions) is None


def test_repair_then_complete_range_delete_reaches_real_plan_boundary(monkeypatch):
    state, actions = event_plan()
    state["decision"] = {"action": "propose_actions", "actions": deepcopy(actions)}
    state["decision"]["actions"][0]["arguments"]["body"]["event_ids"] = actions[0][
        "arguments"
    ]["body"]["event_ids"][:1]
    monkeypatch.setattr(autonomous_plan, "interrupt", lambda value: {})
    result = autonomous_plan.propose(state)
    assert "proposed_actions" not in result
    state.update(result)
    state["decision"]["actions"] = actions
    assert len(autonomous_plan.propose(state)["proposed_actions"]) == 1


def test_daily_creation_cannot_silently_become_a_single_todo():
    state = initial_state("11月1日至11月3日每天9点创建待办喝水")
    assert check_batch_coverage(
        state,
        [
            {
                "tool_name": "create_todo",
                "arguments": {"body": {"title": "喝水", "due_date": "2026-11-01"}},
            }
        ],
    )
    assert (
        check_batch_coverage(
            state,
            [
                {
                    "tool_name": "create_daily_todos",
                    "arguments": {
                        "body": {"title": "喝水", **RANGE, "due_time": "09:00"}
                    },
                }
            ],
        )
        is None
    )


def test_checklist_children_never_become_top_level_checklist_targets():
    parent, child = str(uuid4()), str(uuid4())
    refs = observation_references(
        [
            {
                "tool_name": "get_checklist",
                "result": {
                    "id": parent,
                    "title": "旅行",
                    "items": [{"id": child, "title": "牙刷"}],
                },
            }
        ]
    )
    assert [(item["kind"], item["id"]) for item in refs] == [("checklist", parent)]


@pytest.mark.parametrize("completed", [True, False])
def test_native_bulk_checklist_visits_every_child_and_commits_once(
    monkeypatch, completed
):
    from types import SimpleNamespace

    from backend.api.routes import planning

    parent = SimpleNamespace(id=uuid4())
    children = [SimpleNamespace(completed=not completed) for _ in range(3)]

    class Session:
        commits = 0

        def scalars(self, _):
            return children

        def commit(self):
            self.commits += 1

    session = Session()
    monkeypatch.setattr(planning, "owned_checklist", lambda *_: parent)
    monkeypatch.setattr(
        planning, "checklist_output", lambda *_: {"count": len(children)}
    )
    result = planning.bulk_checklist(
        parent.id, SimpleNamespace(completed=completed), object(), session
    )
    assert all(item.completed is completed for item in children)
    assert session.commits == 1 and result["count"] == 3


@pytest.mark.parametrize(
    "prompt",
    [
        "创建一条待办「每天检查邮箱」，不设截止日期",
        "创建待办，标题是每天检查邮箱，不设截止日期",
    ],
)
def test_literal_daily_title_is_not_forced_into_recurring_creation(prompt):
    state = initial_state(prompt)
    assert (
        check_batch_coverage(
            state,
            [
                {
                    "tool_name": "create_todo",
                    "arguments": {"body": {"title": "每天检查邮箱"}},
                }
            ],
        )
        is None
    )
