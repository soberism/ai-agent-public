import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.api.routes import assistant_read_steps as reads
from backend.features.assistant.answer_claims import AnswerClaim
from backend.features.assistant.answer_guard import guard_decision
from backend.features.assistant.autonomous_types import Decision, initial_state
from backend.features.assistant.claim_verification import verify


@pytest.mark.parametrize("size", [0, 1, 25])
def test_meal_adapter_preserves_complete_native_data_and_publishes_count(
    monkeypatch, size
):
    items = [
        {
            "id": str(uuid4()),
            "title": "测试晚餐",
            "date": "2026-10-16",
            "meal_type": "dinner",
            "dish": "番茄牛腩",
            "diners": 4,
            "status": "draft",
        }
        for _ in range(size)
    ]
    monkeypatch.setattr(
        reads,
        "meals",
        lambda *_: SimpleNamespace(
            model_dump=lambda **_: {"items": items, "preferences": [], "pantry": []}
        ),
    )
    result = json.loads(reads.inspect("list_meals", {}, None, None, None, uuid4()))
    assert result["complete"] is True and result["total_count"] == size
    assert len(result["items"]) == size
    state = initial_state("餐食计划有啥")
    state["observations"] = [
        {"tool_name": "list_meals", "arguments": {}, "result": result}
    ]
    claim = AnswerClaim(
        kind="count", domain="meal", value=size, evidence_ids=["read-1"]
    )
    decision = guard_decision(
        state,
        Decision(
            action="final_answer",
            answer_kind="business",
            requested_domains=["meal"],
            claims=[claim],
        ),
    )
    assert decision.action == "final_answer"
    assert f"餐食计划{size}项" in decision.answer
    if size:
        assert all(
            word in decision.answer
            for word in ("番茄牛腩", "晚餐", "4人", "2026-10-16")
        )
        field = AnswerClaim(
            kind="field",
            domain="meal",
            evidence_ids=["read-1"],
            subject_id=items[0]["id"],
            path="/items/0/dish",
            value="番茄牛腩",
        )
        assert not verify(state, [field])[1]
        field.value = "糖醋鱼"
        assert verify(state, [field])[1]
    claim.scope = {"date": "2026-10-16"}
    assert verify(state, [claim])[1]
    claim.scope = {}
    result["complete"] = False
    assert verify(state, [claim])[1]
    result.pop("complete")
    assert verify(state, [claim])[1]


def test_oversized_meal_result_is_rejected_instead_of_claiming_truncated_count(
    monkeypatch,
):
    from backend.core.security import APIError

    monkeypatch.setattr(
        reads,
        "meals",
        lambda *_: SimpleNamespace(
            model_dump=lambda **_: {
                "items": [{"id": str(uuid4()), "title": "测试", "dish": "x" * 15000}],
                "preferences": [],
                "pantry": [],
            }
        ),
    )
    with pytest.raises(APIError):
        reads.inspect("list_meals", {}, None, None, None, uuid4())


def test_native_meal_evidence_excludes_other_accounts_private_meals(cloud):
    from uuid import UUID

    from helpers import register
    from sqlalchemy.orm import Session

    from backend.db.models import User
    from backend.db.session import engine

    register(cloud)
    created = cloud.post(
        "/api/life/meal-plans",
        json={
            "date": "2026-10-16",
            "meal_type": "dinner",
            "dish": "私有测试菜品",
            "diners": 2,
        },
    )
    assert created.status_code == 201, created.text
    cloud.cookies.clear()
    reader, _ = register(cloud)
    with Session(engine) as session:
        user = session.get(User, UUID(reader["id"]))
        result = json.loads(
            reads.inspect("list_meals", {}, None, user, session, uuid4())
        )
    assert result["items"] == [] and result["total_count"] == 0
    assert "私有测试菜品" not in json.dumps(result, ensure_ascii=False)
