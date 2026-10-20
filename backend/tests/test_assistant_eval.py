import json
from collections import Counter
from pathlib import Path
from runpy import run_path

from backend.features.assistant.capabilities import CAPABILITIES

namespace = run_path(
    str(Path(__file__).resolve().parents[1] / "infra" / "assistant_eval.py")
)
load_cases = namespace["load_cases"]
structural_check = namespace["structural_check"]
replay = namespace["replay"]


def test_first_batch_is_new_and_confirmation_requires_actions():
    cases = load_cases()
    assert len(cases) == 576
    assert all(
        case_id.startswith(
            (
                "OPEN-",
                "FLOW-",
                "GAP-",
                "NEW-",
                "DIRECT-",
                "PARA-",
                "TURN-",
                "CANCEL-",
                "RETRY-",
                "ACCESS-",
                "XDOMAIN-",
                "OPENX-",
            )
        )
        for case_id in cases
    )
    direct_tools = {
        case["target_tool"]
        for case in cases.values()
        if case["id"].startswith("DIRECT-")
    }
    assert len(direct_tools) == 44
    assert Counter(case_id.split("-")[0] for case_id in cases) == Counter(
        {
            "OPEN": 6,
            "FLOW": 6,
            "GAP": 2,
            "NEW": 36,
            "DIRECT": 44,
            "PARA": 88,
            "TURN": 88,
            "CANCEL": 62,
            "RETRY": 62,
            "ACCESS": 88,
            "XDOMAIN": 40,
            "OPENX": 54,
        }
    )
    historical = json.loads(
        (
            Path(__file__).parent / "fixtures" / "assistant_capability_cases.json"
        ).read_text()
    )["cases"]
    assert not set(cases).intersection(case["id"] for case in historical)
    assert not {
        step["user"]
        for case in cases.values()
        for step in case["steps"]
        if "user" in step
    }.intersection(
        step["user"] for case in historical for step in case["steps"] if "user" in step
    )
    mentioned = {
        tool
        for case in cases.values()
        for step in case["steps"]
        for tool in step["expect"].get("relevant_tools", [])
    }
    # 固定576条夹具早于全部时间日程功能；该新增工具由专门回放覆盖。
    assert mentioned == set(CAPABILITIES) - {"list_all_events"}
    step = {"expect": {"outcome": "pending_confirmation"}}
    run = {"status": "waiting", "actions": [], "plan_version": 1}
    assert not structural_check(step, run)
    run["actions"] = [{"id": "action-1"}]
    assert structural_check(step, run)
    answer_step = {"expect": {"outcome": "answer"}}
    exhausted = {
        "status": "completed",
        "final_answer": "已达到自主查询上限，请缩小问题范围后重试。",
    }
    assert not structural_check(answer_step, exhausted)


def test_repeated_approval_reuses_the_original_plan():
    class FakeAPI:
        def __init__(self):
            self.approvals = []

        def request(self, method, path, body=None):
            if path == "/api/assistant/threads":
                return {"thread_id": "test-thread"}
            if path == "/api/agent/runs":
                return {"id": "run-1"}
            self.approvals.append((path, body))
            if len(self.approvals) == 2:
                raise RuntimeError("HTTP 409: duplicate approval")
            return {"id": "run-1"}

        def wait(self, run_id, timeout):
            if not self.approvals:
                return {
                    "id": run_id,
                    "status": "waiting",
                    "actions": [{"id": "action-1", "status": "proposed"}],
                    "plan_version": 3,
                    "final_answer": None,
                    "sources": [],
                    "error": None,
                }
            return {
                "id": run_id,
                "status": "completed",
                "actions": [],
                "plan_version": 3,
                "final_answer": "已完成",
                "sources": [],
                "error": None,
            }

    api = FakeAPI()
    case = {
        "id": "repeat-check",
        "steps": [
            {"user": "创建测试待办", "expect": {"outcome": "pending_confirmation"}},
            {"ui_action": "approve", "expect": {"outcome": "success"}},
            {"ui_action": "approve_again", "expect": {"outcome": "no_duplicate"}},
        ],
    }
    result = replay(api, case, 1, allow_writes=True)
    assert [step["result"] for step in result["steps"]] == [
        "review",
        "review",
        "review",
    ]
    assert (
        api.approvals
        == [
            (
                "/api/agent/runs/run-1/resume",
                {"plan_version": 3, "selected_action_ids": ["action-1"]},
            )
        ]
        * 2
    )
