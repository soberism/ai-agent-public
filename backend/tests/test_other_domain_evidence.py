"""完整列表、原生字段、范围和权限边界。"""

import json
from uuid import UUID, uuid4

import pytest
from helpers import register
from sqlalchemy.orm import Session

from backend.api.routes import assistant_native_reads as native
from backend.api.routes.assistant_read_steps import inspect
from backend.db.models import User
from backend.db.session import engine
from backend.features.assistant.answer_claims import AnswerClaim
from backend.features.assistant.answer_evidence import LIST_DOMAINS
from backend.features.assistant.autonomous_types import initial_state
from backend.features.assistant.claim_verification import verify

OTHER_LISTS = {
    k: v
    for k, v in LIST_DOMAINS.items()
    if k
    not in {
        "list_todos",
        "query_todos",
        "list_events",
        "list_all_events",
        "list_checklists",
        "list_meals",
    }
}


@pytest.mark.parametrize("tool,domain", OTHER_LISTS.items())
@pytest.mark.parametrize("size", [0, 25])
def test_native_lists_keep_all_items_and_reject_wrong_claims(
    monkeypatch, tool, domain, size
):
    rows = [
        {"id": str(uuid4()), "name": f"测试条目{i}", "quantity": 3} for i in range(size)
    ]
    _, model = native.contract(tool)
    monkeypatch.setattr(native, "contract", lambda _: (lambda **kw: rows, model))
    result = json.loads(inspect(tool, {}, None, None, None, uuid4()))
    assert result["complete"] and len(result["items"]) == size
    assert result["total_count"] == size
    state = initial_state("查询列表")
    state["observations"] = [{"tool_name": tool, "arguments": {}, "result": result}]
    claim = AnswerClaim(
        kind="count", domain=domain, value=size, evidence_ids=["read-1"]
    )
    accepted, errors = verify(state, [claim])
    assert not errors
    if size:
        assert "测试条目0" in accepted[0] and "仅展示前20项" in accepted[0]
    assert verify(state, [claim.model_copy(update={"domain": "todo"})])[1]
    assert verify(state, [claim.model_copy(update={"scope": {"status": "completed"}})])[
        1
    ]
    result["complete"] = False
    assert verify(state, [claim])[1]


@pytest.mark.parametrize(
    "tool,field,value",
    [
        ("get_preferences", "memory_enabled", True),
        ("get_preferences", "custom_instructions", "先给结论"),
        ("get_settings", "timezone", "Asia/Shanghai"),
        ("get_todo", "description", "测试描述"),
        ("get_meal", "dish", "测试菜品"),
        ("get_sharing", "scope", "private"),
        ("get_shopping_detail", "purchased", True),
        ("list_materials", "review_count", 2),
        ("get_household", "birth_date", "2000-01-01"),
        ("get_household", "relationship", "家人"),
        ("get_household", "species", "猫"),
    ],
)
def test_scalar_fields_keep_domain_and_subject_binding(tool, field, value):
    from backend.features.assistant.capabilities import CAPABILITIES

    state = initial_state("查询字段")
    state["observations"] = [
        {"tool_name": tool, "arguments": {}, "result": {"id": "target", field: value}}
    ]
    claim = AnswerClaim(
        kind="field",
        domain=CAPABILITIES[tool][3],
        scope={"household_id": "target"} if tool == "get_household" else {},
        subject_id="target",
        path=f"/{field}",
        value=value,
        evidence_ids=["read-1"],
    )
    assert not verify(state, [claim])[1]
    assert verify(state, [claim.model_copy(update={"subject_id": "other"})])[1]
    assert verify(state, [claim.model_copy(update={"value": "伪造值"})])[1]


def test_search_terms_cannot_be_relabelled_as_another_scope():
    state = initial_state("查询材料")
    state["observations"] = [
        {
            "tool_name": "search_business",
            "arguments": {"q": "保单"},
            "result": {"items": [{"id": "one", "title": "保单"}]},
        }
    ]
    claim = AnswerClaim(
        kind="field",
        domain="search",
        subject_id="one",
        path="/items/0/title",
        value="保单",
        scope={"q": "保单"},
        evidence_ids=["read-1"],
    )
    assert not verify(state, [claim])[1]
    assert verify(state, [claim.model_copy(update={"scope": {"q": "发票"}})])[1]


def test_cloud_native_reads_use_existing_account_permissions(cloud):
    owner, _ = register(cloud)
    for path, body in [
        ("/api/life/pantry", {"name": "私有库存", "quantity": 1}),
        ("/api/life/preferences", {"label": "私有偏好", "kind": "preference"}),
        ("/api/assistant/memories", {"content": "私有记忆"}),
        ("/api/assistant/voice-memos", {"transcript": "私有语音"}),
        ("/api/life/shopping-lists", {"title": "私有采购"}),
        ("/api/households", {"name": "私有家庭"}),
    ]:
        response = cloud.post(path, json=body)
        assert response.status_code == 201, response.text
    cloud.cookies.clear()
    reader, _ = register(cloud)
    with Session(engine) as session:
        user = session.get(User, UUID(reader["id"]))
        for name in OTHER_LISTS:
            data = json.loads(inspect(name, {}, None, user, session, uuid4()))
            assert data["items"] == [] and data["total_count"] == 0, name
        user = session.get(User, UUID(owner["id"]))
        data = json.loads(inspect("list_pantry", {}, None, user, session, uuid4()))
        assert data["items"][0]["name"] == "私有库存"


@pytest.mark.parametrize(
    "tool,key,kind",
    [
        ("list_preferences", "label", "preference"),
        ("list_pantry", "name", "pantry"),
        ("list_voice_memos", "transcript", "voice_memo"),
        ("list_memories", "content", "memory"),
        ("list_materials", "name", "document"),
    ],
)
def test_native_evidence_retains_all_permission_recheck_references(tool, key, kind):
    from backend.features.assistant.access import observation_references

    rows = [{"id": str(uuid4()), key: f"测试{i}", "kind": "allergy"} for i in range(25)]
    refs = observation_references([{"tool_name": tool, "result": {"items": rows}}])
    assert len(refs) == 25
    assert all(ref["kind"] == kind for ref in refs)
    assert [r["id"] for r in refs] == [r["id"] for r in rows]


def test_native_todo_and_reminder_keep_existing_suggestions():
    from backend.features.assistant.answer_suggestions import from_observations

    todo = {"id": str(uuid4()), "title": "测试待办", "status": "ongoing"}
    result = from_observations(uuid4(), [{"tool_name": "get_todo", "result": todo}])
    assert result[0]["target_id"] == todo["id"]
    reminder = {
        "id": str(uuid4()),
        "status": "scheduled",
        "remind_at": "2026-12-01T01:00:00Z",
    }
    result = from_observations(
        uuid4(),
        [
            {
                "tool_name": "list_reminders",
                "result": {"items": [reminder], "total_count": 1, "complete": True},
            }
        ],
    )
    assert result and all(r["target_id"] == reminder["id"] for r in result)


def test_review_references_keep_each_items_real_domain():
    from backend.features.assistant.access import observation_references

    todo, event = str(uuid4()), str(uuid4())
    refs = observation_references(
        [
            {
                "tool_name": "review_plan",
                "result": {
                    "details": {
                        "ongoing": [{"id": todo, "title": "测试待办"}],
                        "events": [{"id": event, "title": "测试日程"}],
                    }
                },
            }
        ]
    )
    assert {(r["kind"], r["id"]) for r in refs} == {("todo", todo), ("event", event)}
