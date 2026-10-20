"""合并独立账号回放及失败图状态，生成可追溯的中文结果文档。"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tests"))
from eval_seed_checks import inspect_record

ROOT = Path(__file__).parents[2]
FIXTURE = ROOT / "backend/tests/fixtures/assistant_eval_cases.json"


def oracle_notes(case):
    text = "\n".join(step.get("user", "") for step in case["steps"])
    checks = "\n".join(step["expect"].get("check", "") for step in case["steps"])
    notes = []
    for stale, current in (
        ("少盐", "少辣"),
        ("橄榄油", "番茄酱"),
        ("麦片", "燕麦"),
        ("露营", "新车"),
    ):
        if stale in checks and current in text and stale not in text:
            notes.append(
                f"原断言沿用“{stale}”，实际输入已改为“{current}”；按实际输入复核"
            )
    if "create_reminder" in str(case) and ("每周" in text or "给车充电" in text):
        notes.append("原工具预期与普通定时待办或重复提醒的现有契约不一致")
    if "edit_reminder" in str(case) and "改成周六晚八点" in text:
        notes.append("现有提醒编辑仅支持启停，不支持改时间；这是能力/原预期缺口")
    return notes


def load(files, failure_states):
    records = {}
    states = json.loads(failure_states.read_text()) if failure_states.exists() else {}
    for file in files:
        for line_number, line in enumerate(file.read_text().splitlines(), 1):
            record = json.loads(line)
            assert record["id"] not in records, f"重复ID：{record['id']}"
            record["raw_file"] = str(file.resolve().relative_to(ROOT))
            record["raw_line"] = line_number
            for step in record["steps"]:
                run_id = step.get("actual", {}).get("id")
                if not step.get("trace") and run_id in states:
                    step["trace"] = states[run_id]["trace"]
                    step["trace_recovered"] = True
            records[record["id"]] = record
    return records


def evaluate(record, case):
    issues = inspect_record(record)
    notes = record.get("setup", {}).get("fixture_notes", []) + oracle_notes(case)
    for index, step in enumerate(record["steps"], 1):
        trace = step.get("trace") or {}
        decision = trace.get("decision") or {}
        planned = decision.get("actions", [])
        expected = set(step["expected"].get("relevant_tools", []))
        if step.get("actual", {}).get("status") == "failed" and planned:
            actual = {p["tool_name"] for p in planned}
            if expected and not actual & expected:
                issues.append(
                    {
                        "step": index,
                        "category": "失败前误选操作工具",
                        "detail": f"预期相关工具{sorted(expected)}，实际提案{sorted(actual)}",
                    }
                )
        error = step.get("actual", {}).get("error") or ""
        if "向量" in error and not any(i["category"] == "外部环境缺口" for i in issues):
            issues.append({"step": index, "category": "外部环境缺口", "detail": error})
    return {
        "id": case["id"],
        "issues": issues,
        "fixture_notes": notes,
        "automatic_clear": not issues,
        "semantic_review": "自动检查不能代替全量语义验收",
    }


def cell(value, limit=160):
    return str(value).replace("\n", " ").replace("|", "／")[:limit]


def write(files, failure_states, output, summary_file):
    records = load(files, failure_states)
    cases = json.loads(FIXTURE.read_text())["cases"]
    assert set(records) == {c["id"] for c in cases}, (
        f"主用例覆盖不完整：{len(records)}/576"
    )
    assert all(len(records[c["id"]]["steps"]) == len(c["steps"]) for c in cases), (
        "存在未完整采集步骤的用例"
    )
    audits = {c["id"]: evaluate(records[c["id"]], c) for c in cases}
    manual_file = (
        ROOT
        / "backend/tests/results/assistant_eval_seeded_manual_findings_2026-10-16.json"
    )
    if manual_file.exists():
        manual = json.loads(manual_file.read_text())
        for case_id, findings in manual["cases"].items():
            audits[case_id]["issues"].extend(findings)
        for case_id, decision in manual.get("adjudications", {}).items():
            audit = audits[case_id]
            audit["issues"] = [
                issue
                for issue in audit["issues"]
                if issue["category"] not in decision["remove_categories"]
            ]
            audit["fixture_notes"].extend(decision["notes"])
        for audit in audits.values():
            audit["automatic_clear"] = not audit["issues"]
    events = Counter(
        issue["category"] for audit in audits.values() for issue in audit["issues"]
    )
    affected = Counter(
        category
        for audit in audits.values()
        for category in {i["category"] for i in audit["issues"]}
    )
    runs = Counter(
        step.get("actual", {}).get("status", "无Run返回")
        for record in records.values()
        for step in record["steps"]
    )
    summary = {
        "case_count": len(records),
        "step_count": sum(len(r["steps"]) for r in records.values()),
        "model_user_steps": sum("user" in step for c in cases for step in c["steps"]),
        "setup_ready_cases": sum(
            r.get("setup", {}).get("setup_ready", False) for r in records.values()
        ),
        "environment_ready_cases": sum(
            r.get("setup", {}).get("environment_ready", False) for r in records.values()
        ),
        "capture_errors": sum(bool(r.get("capture_error")) for r in records.values()),
        "run_statuses": dict(runs),
        "automatic_clear_cases": sum(a["automatic_clear"] for a in audits.values()),
        "flagged_cases": sum(bool(a["issues"]) for a in audits.values()),
        "category_cases": dict(affected),
        "category_events": dict(events),
        "audits": audits,
    }
    summary_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    lines = [
        "# AI对话576条隔离数据完整复测（2026-10-16）",
        "",
        "> 真实模型及云端测试库；每条独立账号、会话和Redis命名空间。检查未报问题不等于完整语义通过。",
        "",
        "## 覆盖与执行",
        "",
        f"- 主用例：{len(records)}个唯一ID，原始{summary['step_count']}步均采集；用户输入{summary['model_user_steps']}步。采集异常{summary['capture_errors']}条。",
        f"- 数据前置可满足{summary['setup_ready_cases']}条，外部依赖已配置{summary['environment_ready_cases']}条；二者分别统计，不混为业务通过。",
        f"- Run步骤状态：{dict(runs)}。这些是步骤级观测，包含确认后的同一Run重复观测。",
        f"- 检查未报问题{summary['automatic_clear_cases']}条、带问题或待核对标记{summary['flagged_cases']}条。后者包含外部环境、旧用例预期和下游确认未执行，不能当成产品缺陷数。",
        "- 原始576条JSON保持不变；准备清单为assistant_eval_setup.json，实际对象和前后状态保存在各条JSONL记录。原始数据集528条未预置的历史运行与本次口径不同，不计算改善百分比。",
        "",
        "## 自动检查与人工确认分类",
        "",
        "| 分类 | 涉及用例数 | 事件数 |",
        "| --- | ---: | ---: |",
    ]
    lines += [
        f"| {category} | {affected[category]} | {events[category]} |"
        for category in affected
    ]
    lines += [
        "",
        "分类会重叠；‘未生成计划’和‘下游确认未执行’常来自同一处上游问题。具体根因以逐条轨迹和人工复核为准。",
        "",
        "## 全部576条索引",
        "",
        "| ID | 场景 | 自动检查 | 前置/断言备注 | 原始记录 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for case in cases:
        id = case["id"]
        record, audit = records[id], audits[id]
        categories = (
            "、".join(dict.fromkeys(i["category"] for i in audit["issues"]))
            or "未报问题，待语义验收"
        )
        raw = "../" + record["raw_file"]
        lines.append(
            f"| {id} | {cell(case['title'])} | {cell(categories)} | {cell('；'.join(audit['fixture_notes']))} | [JSONL第{record['raw_line']}行]({raw}) |"
        )
    lines += ["", "## 全量对话与业务检查", ""]
    for case in cases:
        record, audit = records[case["id"]], audits[case["id"]]
        lines += [
            f"### {case['id']} {case['title']}",
            "",
            f"前置：数据库准备{'可满足' if record['setup']['setup_ready'] else '存在原条件冲突'}；环境缺口：{'、'.join(record['setup']['dependency_blockers']) or '无已知配置缺口'}。",
        ]
        if audit["fixture_notes"]:
            lines += ["", "原用例备注：" + "；".join(audit["fixture_notes"])]
        for index, step in enumerate(record["steps"], 1):
            actual = step.get("actual", {})
            tools = [a["tool_name"] for a in step.get("actions", [])]
            lines += [
                "",
                f"{index}. 输入：{step['input']}",
                f"   预期：{step['expected']['outcome']}；实际：HTTP {step.get('http_status', '未发送')}／{actual.get('status', step.get('skipped', '无Run'))}；业务变化{len(step.get('business_delta', []))}处；操作：{', '.join(tools) or '无持久化动作'}。",
                "",
                "   回答："
                + (
                    actual.get("final_answer")
                    or actual.get("error")
                    or str(step.get("error") or step.get("skipped") or "无")
                ).replace("\n", "\n   "),
            ]
            sources = actual.get("sources", [])
            if sources:
                lines += [
                    "",
                    "   来源："
                    + "；".join(
                        str(source.get("title") or "资料")
                        + " "
                        + str(source.get("url") or "")
                        for source in sources
                    ),
                ]
        if audit["issues"]:
            lines += ["", "检查标记："] + [
                f"- {'步骤' + str(issue['step']) + '：' if issue.get('step') else ''}{issue['category']}：{issue['detail']}"
                for issue in audit["issues"]
            ]
        lines += [""]
    lines += [
        "## 验证边界",
        "",
        "本报告保存完整对话、状态差异及失败前图状态，但未使用另一个LLM充当评分裁判，也未将结构检查当作全部事实/语义正确。未验证浏览器及独立RabbitMQ Worker，未部署。私有材料正文受embedding未配置限制；实时网页来源的时效性与相关性需单独核对。",
        "",
    ]
    output.write_text("\n".join(lines))
    print(
        json.dumps(
            {key: value for key, value in summary.items() if key != "audits"},
            ensure_ascii=False,
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", type=Path, nargs="+")
    parser.add_argument("--failure-states", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    write(args.files, args.failure_states, args.output, args.summary)


if __name__ == "__main__":
    main()
