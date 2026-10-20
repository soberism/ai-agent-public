"""显式启用后，在 ai_agent_test 中回放全新 Agent Run 场景。"""

import os
from datetime import datetime, timedelta
from pathlib import Path
from runpy import run_path
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
from backend.features.assistant.agent_tasks import execute_plan, execute_run

eval_code = run_path(
    str(Path(__file__).resolve().parents[1] / "infra" / "assistant_eval.py")
)
cases = eval_code["load_cases"]()
replay = eval_code["replay"]

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_MODEL") != "1",
    reason="显式 RUN_LIVE_MODEL=1 才调用真实模型",
)


def isolated_api(cloud, monkeypatch, before_confirm=None, read_tools=None):
    register(cloud)
    original_decide = agent_tasks.decide

    def traced_decide(state):
        decision = original_decide(state)
        print(f"Agent decision: {decision.action}")
        return decision

    monkeypatch.setattr(agent_tasks, "decide", traced_decide)
    if read_tools is not None:
        original_inspect = agent_tasks.inspect

        def traced_inspect(name, *args, **kwargs):
            read_tools.append(name)
            return original_inspect(name, *args, **kwargs)

        monkeypatch.setattr(agent_tasks, "inspect", traced_inspect)
    monkeypatch.setattr(agent_runs.run_task, "delay", execute_run)
    monkeypatch.setattr(agent_runs.resume_task, "delay", execute_plan)

    class ClientAPI:
        def request(self, method, path, body=None):
            if path.endswith("/resume") and before_confirm:
                before_confirm()
            response = cloud.request(method, path, json=body)
            assert response.status_code < 400, (
                path,
                response.status_code,
                response.text,
            )
            return response.json()

        def wait(self, run_id, timeout):
            return self.request("GET", f"/api/agent/runs/{run_id}")

    return ClientAPI()


@pytest.mark.parametrize("case_id", [f"OPEN-0{n}" for n in range(1, 6)])
def test_new_open_question_transport(cloud, monkeypatch, case_id):
    result = replay(isolated_api(cloud, monkeypatch), cases[case_id], 60, False)
    assert all(step["result"] == "review" for step in result["steps"]), result
    print(f"{case_id}: {result['steps'][0]['actual']['answer']}")


def test_new_multiturn_todo_business_result(cloud, monkeypatch):
    def todos():
        response = cloud.get("/api/todos")
        assert response.status_code == 200
        return response.json()["items"]

    api = isolated_api(cloud, monkeypatch, before_confirm=lambda: assert_empty(todos()))
    assert todos() == []
    result = replay(api, cases["FLOW-01"], 60, True)
    assert all(step["result"] == "review" for step in result["steps"]), result
    assert action_tools(result["steps"][1]["actual"]["run_id"]) == ["create_todo"]
    created = todos()
    assert len(created) == 1 and "买牛奶" in created[0]["title"], (result, created)
    print(f"FLOW-01: {created[0]['title']}")


def test_new_daily_todos_business_result(cloud, monkeypatch):
    def todos():
        response = cloud.get("/api/todos")
        assert response.status_code == 200
        return response.json()["items"]

    api = isolated_api(cloud, monkeypatch, before_confirm=lambda: assert_empty(todos()))
    result = replay(api, cases["GAP-01"], 60, True)
    assert all(step["result"] == "review" for step in result["steps"]), result
    assert action_tools(result["steps"][0]["actual"]["run_id"]) == [
        "create_daily_todos"
    ]
    created = todos()
    assert len(created) == 5, (result, created)
    assert all("喝水" in item["title"] for item in created)
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    next_monday = today + timedelta(days=7 - today.weekday())
    assert {item["due_date"] for item in created} == {
        (next_monday + timedelta(days=offset)).isoformat() for offset in range(5)
    }
    assert all(item["due_time"] == "09:00" for item in created)
    print(f"GAP-01: created {len(created)} daily todos")


def test_new_bulk_event_delete_business_result(cloud, monkeypatch):
    event_ids = []

    def assert_unchanged():
        assert all(
            cloud.get(f"/api/calendar/events/{event_id}").status_code == 200
            for event_id in event_ids
        )

    api = isolated_api(cloud, monkeypatch, before_confirm=assert_unchanged)
    for day in ("2026-10-02", "2026-10-06", "2026-10-08"):
        response = cloud.post(
            "/api/calendar/events",
            json={
                "title": f"评估日程{day[-2:]}",
                "start_date": day,
                "start_time": "10:00",
                "end_date": day,
                "end_time": "11:00",
            },
        )
        assert response.status_code == 201, response.text
        event_ids.append(response.json()["id"])
    result = replay(api, cases["GAP-02"], 60, True)
    assert all(step["result"] == "review" for step in result["steps"]), result
    assert action_tools(result["steps"][0]["actual"]["run_id"]) == ["delete_events"]
    assert [
        cloud.get(f"/api/calendar/events/{event_id}").status_code
        for event_id in event_ids
    ] == [404, 404, 200]
    print("GAP-02: deleted only two in-range events")


def assert_empty(items):
    assert items == [], f"确认前已有待办写入: {len(items)}"


def action_tools(run_id):
    with Session(engine) as session:
        return list(
            session.scalars(
                select(AgentAction.tool_name)
                .where(AgentAction.run_id == UUID(run_id))
                .order_by(AgentAction.position)
            )
        )
