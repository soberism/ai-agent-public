"""首批 Agent Run 对话回放；默认只做夹具校验，不连接服务。"""

import argparse
import json
import os
import time
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
TERMINAL = {"completed", "failed", "cancelled", "waiting"}
UNHELPFUL_FALLBACKS = (
    "已达到自主查询上限",
    "这次没能找到合适的查询或操作方式",
    "这次还没能确认你要查或要处理的具体事项",
    "这次没能找到适合的查询方式",
    "这次还没能生成修改方案",
    "这次没能确定要查询的具体内容",
    "这次查到的内容较多",
    "这次找到的资料内容较多",
    "这次没能生成可确认的操作方案",
    "这次还没能整理好操作方案",
    "这次还没能核实你要的信息",
    "这次没能从网上核实你问的信息",
    "这次没能完成查询",
    "这次没能完成日程查询",
    "这次还没能整理出资料中的完整答案",
    "请明确说明需要联网搜索",
    "没有找到与问题匹配的已开放工具",
)


def load_cases():
    fixture = json.loads((FIXTURES / "assistant_eval_cases.json").read_text())
    selected = {case["id"]: case for case in fixture["cases"]}
    assert len(fixture["cases"]) == 576
    assert len(selected) == 576, "全部用例必须有 576 个不同 ID"
    for case in selected.values():
        assert case["steps"] and all("expect" in step for step in case["steps"])
        assert all(("user" in step) != ("ui_action" in step) for step in case["steps"])
    return selected


class API:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def request(self, method, path, body=None):
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode()
        request = Request(
            self.base_url + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        try:
            with self.opener.open(request, timeout=30) as response:
                raw = response.read()
                return json.loads(raw) if raw else {}
        except HTTPError as error:
            raise RuntimeError(f"HTTP {error.code}: {path}") from None
        except URLError as error:
            raise RuntimeError(f"无法连接服务: {error.reason}") from None

    def wait(self, run_id, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            run = self.request("GET", f"/api/agent/runs/{run_id}")
            if run["status"] in TERMINAL:
                return run
            time.sleep(1)
        raise TimeoutError(f"Run {run_id} 超过 {timeout} 秒")


def observed_outcome(run):
    if run["status"] == "waiting":
        return "pending_confirmation"
    if run["status"] == "cancelled":
        return "cancelled"
    if run["status"] == "failed":
        return "failure"
    if run["status"] == "completed":
        return "answer_or_success"
    return "unknown"


def structural_check(step, run):
    expected = step["expect"]["outcome"]
    actual = observed_outcome(run)
    if any(text in (run.get("final_answer") or "") for text in UNHELPFUL_FALLBACKS):
        return False
    if expected == "pending_confirmation":
        return (
            actual == expected
            and bool(run["actions"])
            and run["plan_version"] is not None
        )
    if expected == "cancelled":
        return actual == "cancelled" or (
            actual == "answer_or_success"
            and not any(a["status"] == "proposed" for a in run["actions"])
        )
    if expected in {"answer", "clarification", "refusal", "navigation", "success"}:
        return actual == "answer_or_success" and bool(run["final_answer"])
    return False


def replay(api, case, timeout, allow_writes):
    thread = api.request("POST", "/api/assistant/threads", {"fresh": True})
    thread_id = thread["thread_id"]
    records = []
    current_run = None
    last_approval = None
    for index, step in enumerate(case["steps"], 1):
        started = time.monotonic()
        if "ui_action" in step:
            action = step["ui_action"]
            if not allow_writes:
                records.append(
                    {
                        "step": index,
                        "result": "blocked",
                        "reason": "写入确认需要隔离环境和 --allow-writes",
                    }
                )
                break
            if action == "approve_again":
                if not last_approval:
                    records.append(
                        {"step": index, "result": "fail", "reason": "没有上次确认请求"}
                    )
                    break
                try:
                    duplicate = api.request("POST", last_approval[0], last_approval[1])
                    duplicate_status = duplicate.get("status", "unknown")
                    if duplicate_status not in TERMINAL:
                        duplicate_status = api.wait(duplicate["id"], timeout)["status"]
                    detail = {"status": duplicate_status}
                except RuntimeError as error:
                    detail = {"error": str(error)}
                records.append(
                    {
                        "step": index,
                        "input": action,
                        "expected": step["expect"],
                        "actual": detail,
                        "latency_ms": round((time.monotonic() - started) * 1000),
                        "result": "review",
                        "reason": "需核对重复提交前后的业务写入次数",
                    }
                )
                continue
            if action not in {"approve", "reject"}:
                records.append(
                    {
                        "step": index,
                        "result": "blocked",
                        "reason": f"未实现的界面操作: {action}",
                    }
                )
                break
            if not current_run or current_run["status"] != "waiting":
                records.append(
                    {"step": index, "result": "fail", "reason": "没有可确认的计划"}
                )
                break
            selected = (
                [
                    item["id"]
                    for item in current_run["actions"]
                    if item["status"] == "proposed"
                ]
                if action == "approve"
                else []
            )
            path = f"/api/agent/runs/{current_run['id']}/resume"
            body = {
                "plan_version": current_run["plan_version"],
                "selected_action_ids": selected,
            }
            if action == "approve":
                last_approval = (path, body)
            current_run = api.request("POST", path, body)
        else:
            current_run = api.request(
                "POST",
                "/api/agent/runs",
                {"thread_id": thread_id, "prompt": step["user"]},
            )
        current_run = api.wait(current_run["id"], timeout)
        records.append(
            {
                "step": index,
                "input": step.get("user", step.get("ui_action")),
                "expected": step["expect"],
                "actual": {
                    "run_id": current_run["id"],
                    "status": current_run["status"],
                    "outcome": observed_outcome(current_run),
                    "answer": current_run["final_answer"],
                    "sources": current_run["sources"],
                    "actions": current_run["actions"],
                    "error": current_run["error"],
                },
                "latency_ms": round((time.monotonic() - started) * 1000),
                "result": "review" if structural_check(step, current_run) else "fail",
            }
        )
        if records[-1]["result"] == "fail":
            break
    return {"id": case["id"], "thread_id": thread_id, "steps": records}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run", action="store_true", help="连接真实 API 回放；默认仅校验夹具"
    )
    parser.add_argument("--ids", help="逗号分隔的用例 ID；默认全部 576 条")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument(
        "--allow-writes", action="store_true", help="仅隔离测试环境可用"
    )
    parser.add_argument(
        "--fixtures-ready", action="store_true", help="已人工预置用例 setup 指定的数据"
    )
    parser.add_argument("--output", type=Path, help="JSONL 报告路径，默认只输出摘要")
    args = parser.parse_args()
    cases = load_cases()
    ids = args.ids.split(",") if args.ids else list(cases)
    unknown = set(ids) - cases.keys()
    parser.error(f"未知用例: {sorted(unknown)}") if unknown else None
    if not args.run:
        print(f"固定回归夹具有效：{len(cases)} 条，不读取历史用例")
        return
    parsed = urlparse(args.base_url)
    if (
        parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.scheme != "http"
    ):
        parser.error("仅允许连接本机 HTTP 服务；请先建立隔离环境隧道")
    if args.allow_writes and os.getenv("ASSISTANT_EVAL_ISOLATED") != "1":
        parser.error(
            "写入回放需先核对测试库、Redis 与队列，并设置 ASSISTANT_EVAL_ISOLATED=1"
        )
    email, password = (
        os.getenv("ASSISTANT_EVAL_EMAIL"),
        os.getenv("ASSISTANT_EVAL_PASSWORD"),
    )
    if not email or not password:
        parser.error(
            "通过 ASSISTANT_EVAL_EMAIL / ASSISTANT_EVAL_PASSWORD 提供专用测试账号"
        )
    api = API(args.base_url)
    api.request("POST", "/api/auth/login", {"email": email, "password": password})
    results = []
    for case_id in ids:
        case = cases[case_id]
        if case.get("setup") and not args.fixtures_ready:
            result = {
                "id": case_id,
                "steps": [],
                "result": "blocked",
                "reason": "需人工预置 fixture: " + case["setup"],
            }
        else:
            try:
                result = replay(api, case, args.timeout, args.allow_writes)
            except (RuntimeError, TimeoutError, KeyError) as error:
                result = {
                    "id": case_id,
                    "steps": [],
                    "result": "fail",
                    "reason": str(error),
                }
        results.append(result)
        status = result.get("result") or (
            result["steps"][-1]["result"] if result["steps"] else "blocked"
        )
        print(f"{case_id}: {status}")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in results)
        )
        print(f"详细记录：{args.output}")
    print("review 表示接口结构正常，语义、工具轨迹和业务状态仍需核验；不计为通过。")


if __name__ == "__main__":
    main()
