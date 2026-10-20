"""在专用账号预置对象，验证操作类型、范围、确认前后状态和重复确认。"""

import json
import os
from datetime import datetime
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from helpers import register
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.routes import agent_runs
from backend.db.agent_models import AgentAction
from backend.db.session import engine
from backend.features.assistant import agent_tasks

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_MODEL") != "1", reason="显式启用真实模型"
)
OUTPUT = Path(__file__).parent / "results" / "assistant_priority_fixes_2026-10-16.jsonl"


@pytest.fixture
def agent(cloud, monkeypatch, request):
    register(cloud)
    monkeypatch.setattr(agent_runs.run_task, "delay", agent_tasks.execute_run)
    monkeypatch.setattr(agent_runs.resume_task, "delay", agent_tasks.execute_plan)
    thread = cloud.post("/api/assistant/threads", json={"fresh": True}).json()[
        "thread_id"
    ]
    traces = []
    original = agent_tasks.run_graph

    def traced(*args, **kwargs):
        result = original(*args, **kwargs)
        traces.append(
            {
                key: result.get(key)
                for key in (
                    "observations",
                    "decision",
                    "proposed_actions",
                    "knowledge",
                    "web_results",
                )
            }
        )
        return result

    monkeypatch.setattr(agent_tasks, "run_graph", traced)

    def send(prompt=None, run=None):
        if prompt is not None:
            response = cloud.post(
                "/api/agent/runs", json={"thread_id": thread, "prompt": prompt}
            )
        else:
            response = cloud.post(
                f"/api/agent/runs/{run['id']}/resume",
                json={
                    "plan_version": run["plan_version"],
                    "selected_action_ids": [
                        a["id"] for a in run["actions"] if a["status"] == "proposed"
                    ],
                },
            )
        assert response.status_code < 400, response.text
        actual = response.json()
        actual = cloud.get(f"/api/agent/runs/{actual['id']}").json()
        with Session(engine) as db:
            tools = [
                {"tool_name": a.tool_name, "arguments": a.arguments}
                for a in db.scalars(
                    select(AgentAction)
                    .where(AgentAction.run_id == UUID(actual["id"]))
                    .order_by(AgentAction.position)
                )
            ]
        with OUTPUT.open("a") as output:
            output.write(
                json.dumps(
                    {
                        "case": request.node.name,
                        "attempt": os.getenv("PRIORITY_EVAL_ATTEMPT", "1"),
                        "prompt": prompt,
                        "run": actual,
                        "tools": tools,
                        "traces": traces,
                    },
                    ensure_ascii=False,
                    default=str,
                )
                + "\n"
            )
        return actual, tools

    send.traces = traces
    return send


def meal(cloud, title, dish, preferences=None):
    response = cloud.post(
        "/api/life/meal-plans",
        json={
            "schedule_text": title,
            "date": datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat(),
            "meal_type": "dinner",
            "dish": dish,
            "diners": 4,
            "preferences": preferences or [],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def shopping(cloud):
    response = cloud.post("/api/life/shopping-lists", json={"title": "早餐补货"})
    assert response.status_code == 201, response.text
    path = f"/api/life/shopping-lists/{response.json()['id']}"
    for name in ("鸡蛋", "燕麦"):
        added = cloud.post(
            path + "/items",
            json={"name": name, "quantity": 1},
        )
        assert added.status_code == 201, added.text
    return path


def approve(agent, run):
    actual, _ = agent(run=run)
    assert actual["status"] == "completed", actual
    assert all(a["status"] == "completed" for a in actual["actions"]), actual


@pytest.mark.parametrize(
    "prompt",
    [
        "以后给我安排吃的，记得我对花生过敏。",
        "以后给我安排吃的，记得我对花生过敏。以我刚补充的要求为准。",
    ],
)
def test_long_term_allergy_is_global_not_a_single_meal(cloud, agent, prompt):
    meal(cloud, "周六咖喱饭", "咖喱饭")
    meal(cloud, "周日晚餐", "番茄牛腩")
    baseline = cloud.get("/api/life/meal-plans").json()
    run, tools = agent(prompt)
    assert run["status"] == "waiting", run
    assert [t["tool_name"] for t in tools] == ["add_preference"], tools
    assert cloud.get("/api/life/meal-plans").json() == baseline
    approve(agent, run)
    actual = cloud.get("/api/life/meal-plans").json()
    assert len(actual["preferences"]) == 1
    assert actual["preferences"][0]["kind"] == "allergy"
    assert "花生" in actual["preferences"][0]["label"]
    assert actual["items"] == baseline["items"]


def test_single_meal_preference_does_not_change_global_or_other_meal(cloud, agent):
    target = meal(
        cloud, "周六咖喱饭", "咖喱饭", [{"label": "少盐", "kind": "preference"}]
    )
    other = meal(cloud, "周日晚餐", "番茄牛腩")
    baseline = cloud.get("/api/life/meal-plans").json()
    run, tools = agent("只给“周六咖喱饭”这顿加少辣要求，别改我的长期饮食偏好。")
    assert run["status"] == "waiting", run
    assert len(tools) == 1 and tools[0]["tool_name"] in {
        "add_meal_preference",
        "edit_meal",
    }, tools
    assert cloud.get("/api/life/meal-plans").json() == baseline
    approve(agent, run)
    actual = cloud.get("/api/life/meal-plans").json()
    rows = {r["id"]: r for r in actual["items"]}
    assert rows[other["id"]]["preferences"] == []
    assert any("少辣" in p["label"] for p in rows[target["id"]]["preferences"])
    assert any(p["label"] == "少盐" for p in rows[target["id"]]["preferences"])
    assert actual["preferences"] == []


def test_unneeded_shopping_item_is_deleted_not_marked_purchased(cloud, agent):
    path = shopping(cloud)
    baseline = cloud.get(path).json()
    run, tools = agent("“早餐补货”里燕麦不用买了，划掉这项，只处理一次。")
    assert run["status"] == "waiting", run
    assert [t["tool_name"] for t in tools] == ["delete_shopping_item"], tools
    assert cloud.get(path).json() == baseline
    approve(agent, run)
    actual = cloud.get(path).json()
    assert [item["name"] for item in actual["items"]] == ["鸡蛋"]
    assert not actual["items"][0]["purchased"]
    duplicate = cloud.post(
        f"/api/agent/runs/{run['id']}/resume",
        json={
            "plan_version": run["plan_version"],
            "selected_action_ids": [a["id"] for a in run["actions"]],
        },
    )
    assert duplicate.status_code == 409
    assert cloud.get(path).json() == actual


def test_confirm_shopping_does_not_mark_all_items_purchased(cloud, agent):
    path = shopping(cloud)
    baseline = cloud.get(path).json()
    run, tools = agent("“早餐补货”都核对好了，帮我确认这张单，只处理一次。")
    assert run["status"] == "waiting", run
    assert [t["tool_name"] for t in tools] == ["confirm_shopping"], tools
    assert cloud.get(path).json() == baseline
    approve(agent, run)
    actual = cloud.get(path).json()
    assert actual["status"] == "planned"
    assert actual["items"] == baseline["items"]


@pytest.mark.parametrize("suffix", ["。", "，只处理一次。"])
def test_unsupported_weekly_reminder_clarifies_without_single_write(
    cloud, agent, suffix
):
    run, tools = agent("每周日晚八点提醒我清理冰箱" + suffix)
    assert run["status"] == "completed" and tools == [], run
    assert "每周" in run["final_answer"]
    assert cloud.get("/api/todos").json()["items"] == []
    assert (
        cloud.get(
            "/api/calendar/events",
            params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
        ).json()["items"]
        == []
    )


def test_meal_calendar_action_retains_link_and_other_meal(cloud, agent):
    target = meal(cloud, "周日午餐蘑菇烩饭", "蘑菇烩饭")
    other = meal(cloud, "周日晚餐", "番茄牛腩")
    baseline = cloud.get("/api/life/meal-plans").json()
    run, tools = agent("把“周日午餐蘑菇烩饭”加入日历。")
    assert run["status"] == "waiting", run
    assert [t["tool_name"] for t in tools] == ["confirm_meal"], tools
    assert cloud.get("/api/life/meal-plans").json() == baseline
    approve(agent, run)
    assert cloud.get(f"/api/life/meal-plans/{target['id']}").json()["calendar_url"]
    assert (
        cloud.get(f"/api/life/meal-plans/{other['id']}").json()["calendar_url"] is None
    )
    assert (
        len(
            cloud.get(
                "/api/calendar/events",
                params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
            ).json()["items"]
        )
        == 1
    )


def test_expression_preference_is_saved_after_confirmation(cloud, agent):
    run, tools = agent("以后回答我尽量先给结论，再给步骤。")
    assert run["status"] == "waiting", run
    assert [t["tool_name"] for t in tools] == ["set_preferences"], tools
    approve(agent, run)
    actual = cloud.get("/api/assistant/preferences").json()
    assert (
        "结论" in actual["custom_instructions"]
        and "步骤" in actual["custom_instructions"]
    )


def test_explicit_todo_request_generates_valid_plan(cloud, agent):
    run, tools = agent("下个月 3 号上午十点提醒我给植物换盆。")
    assert run["status"] == "waiting", run
    assert [t["tool_name"] for t in tools] == ["create_todo"], tools
    assert cloud.get("/api/todos").json()["items"] == []
    approve(agent, run)
    items = cloud.get("/api/todos").json()["items"]
    assert len(items) == 1 and "换盆" in items[0]["title"]
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    expected = today.replace(
        year=today.year + (today.month == 12), month=today.month % 12 + 1, day=3
    )
    assert (
        items[0]["due_date"] == expected.isoformat() and items[0]["due_time"] == "10:00"
    )
