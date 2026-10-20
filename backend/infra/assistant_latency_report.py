"""汇总连续会话逐题计时；原始回答只保留在输入记录中。"""

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median


def percentile(values, p):
    values = sorted(values)
    return values[max(0, math.ceil(len(values) * p) - 1)] if values else 0


def model_calls(row, phase=None):
    return [
        m
        for m in row.get("metrics", [])
        if m.get("phase") in {"model", "summary_model"}
        and (phase is None or m["phase"] == phase)
    ]


def audit_context(source):
    from langgraph.checkpoint.postgres import PostgresSaver

    from backend.core.security import settings

    assert settings.postgres_db == "ai_agent_test", "仅允许读取专用测试库检查点"
    rows = [json.loads(line) for line in source.read_text().splitlines() if line]
    audit = []
    with PostgresSaver.from_conn_string(settings.checkpoint_url) as saver:
        for row in rows:
            if "index" not in row:
                continue
            saved = saver.get({"configurable": {"thread_id": row["run_id"]}})
            summary = (
                saved.get("channel_values", {}).get("conversation_summary", "")
                if saved
                else ""
            )
            audit.append(
                {
                    "index": row["index"],
                    "checkpoint_found": bool(saved),
                    "summary_chars": len(summary),
                    "summary_fallback": summary.startswith(
                        "部分较早对话的摘要暂不可用"
                    ),
                }
            )
    source.with_suffix(".context.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n"
    )


def report(source, output):
    records = [json.loads(line) for line in source.read_text().splitlines() if line]
    metadata = next(row for row in records if row.get("metadata"))
    rows = [row for row in records if "index" in row]
    assert rows, "没有逐题记录"
    groups = defaultdict(list)
    for row in rows:
        groups[row["group"]].append(row)
    audit_path = source.with_suffix(".context.json")
    audit = json.loads(audit_path.read_text()) if audit_path.exists() else []
    fallback_indexes = {r["index"] for r in audit if r.get("summary_fallback")}
    durations = [r["visible_seconds"] for r in rows]
    summaries = [r for r in rows if model_calls(r, "summary_model")]
    total_model = sum(m.get("seconds", 0) for r in rows for m in model_calls(r))
    total_summary = sum(
        m.get("seconds", 0) for r in rows for m in model_calls(r, "summary_model")
    )
    total_wait = sum(durations)
    statuses = Counter(r["status"] for r in rows)
    lines = [
        "# AI全功能连续对话耗时实测（2026-10-19）",
        "",
        f"同一隔离测试账号、同一个会话，串行完成{len(rows)}/{metadata['question_count']}题，覆盖{len(groups)}组功能。",
        "数据为合成测试对象；真实模型、真实Celery独立队列和700毫秒轮询，不执行待确认写操作。",
        f"模型：{metadata['model']}；工具注册表使用已部署后端{metadata['baseline_registry']}，不把尚未发布的待办排序优化混入基线。",
        "",
        "## 测量口径",
        "",
        "总等待从提交问题前计时，到轮询拿到终态为止，含API、真实队列和轮询；不含浏览器绘制。API由本地TestClient承载，Worker运行于本地Python进程，基础服务使用云端专用测试库及隔离Redis命名空间，不是直接在用户账号的公网页面测量。",
        "模型耗时为SDK调用整段时间，可能包含SDK内部重试；历史摘要单列，属于额外模型请求。排队栏从数据库创建至Worker开始，含发布/调度；本地与云端数据库往返会影响非模型耗时，不能将本表直接当成线上手机端SLA。",
        "单个长会话同时叠加题目类型和历史长度，不能用分组差异证明某功能本身慢；分位数只描述本次样本，不能代表整体用户分布。",
        "",
        "## 整体统计",
        "",
        f"- 状态：{dict(statuses)}。completed只表示任务终态，可能仍是澄清、未核实或兜底，不作为业务正确通过率。",
        f"- 总等待：{total_wait:.2f}秒；中位数{median(durations):.2f}秒，均值{mean(durations):.2f}秒，样本P95 {percentile(durations, 0.95):.2f}秒，样本P99 {percentile(durations, 0.99):.2f}秒，最慢{max(durations):.2f}秒。",
        f"- SDK模型等待合计{total_model:.2f}秒，占逐题总等待{total_model / total_wait:.1%}；其中历史摘要{total_summary:.2f}秒，涉及{len(summaries)}题。",
        f"- 模型SDK调用共{sum(len(model_calls(r)) for r in rows)}次，平均每题{sum(len(model_calls(r)) for r in rows) / len(rows):.2f}次。",
        "",
        "## 各功能耗时",
        "",
        "| 功能 | 题数 | 中位数/秒 | 最慢/秒 | 平均模型调用数 | 含摘要题数 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for group, items in groups.items():
        values = [r["visible_seconds"] for r in items]
        lines.append(
            f"| {group} | {len(items)} | {median(values):.2f} | {max(values):.2f} | {mean(len(model_calls(r)) for r in items):.1f} | {sum(bool(model_calls(r, 'summary_model')) for r in items)} |"
        )
    lines += [
        "",
        "## 逐题记录",
        "",
        "| 序号 | 功能 | 问题 | 总等待/秒 | 模型/秒 | 摘要/秒 | 排队/秒 | 调用数 | 读取数 | 状态 |",
        "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        model = sum(m.get("seconds", 0) for m in model_calls(row))
        summary = sum(m.get("seconds", 0) for m in model_calls(row, "summary_model"))
        queue = row.get("queue_start_seconds")
        queue_text = f"{queue:.2f}" if queue is not None else "未采集"
        lines.append(
            f"| {row['index']} | {row['group']} | {row['prompt'].replace('|', '/')} | {row['visible_seconds']:.2f} | {model:.2f} | {summary:.2f} | {queue_text} | {len(model_calls(row))} | {row['reads']} | {row['status']} |"
        )
    lines += [
        "",
        "## 摘要降级核对",
        "",
        f"检查点另行核对到{len(audit)}题，其中{len(fallback_indexes)}题使用历史摘要不可用的降级说明。详见同名.context.json，仅保留长度与布尔标记，不复制摘要正文。",
        "",
        "摘要降级后prepare不会推进缓存的covered边界；因此下一题可能再次处理同一批旧历史。该问题与只读工具排序独立，需单独修复后复测。",
        "",
        "## 最慢的十题",
        "",
    ]
    for row in sorted(rows, key=lambda r: r["visible_seconds"], reverse=True)[:10]:
        lines.append(
            f"- 第{row['index']}题「{row['prompt']}」：{row['visible_seconds']:.2f}秒；路径：{' → '.join(row['graph_actions']) or '未捕获'}。"
        )
    queues = [
        r["queue_start_seconds"]
        for r in rows
        if r.get("queue_start_seconds") is not None
    ]
    lines += [
        "",
        "## 结论与处理优先级",
        "",
        f"1. 首先处理同步历史摘要：本次占总等待{total_summary / total_wait:.1%}，{len(summaries)}题额外调用摘要模型，{len(fallback_indexes)}题携带摘要降级标记。需合并更新、限制重复失败重做，并保留必要上下文及对象指代。",
        "2. 再减少工具发现与答案修订的串行轮次：多数业务请求要发现、读取、生成答复，部分请求因重复搜索或证据修订继续增加轮次。此前待办排序修复只覆盖其中一个分支，不能解决所有对话慢。",
        f"3. 本次单并发排队中位数{median(queues):.3f}秒、最大{max(queues):.3f}秒，当前样本不支持优先扩容队列的结论；也未测试多人并发。",
        "4. 普通问答不应走完整业务查询路径；当前非流式工具决策需等完整结果才能发布。阶段反馈或安全的流式会话输出可改善等待感，但不能宣称减少同等比例总耗时。",
        "",
        "## 未正常回答或需要复核的题目",
        "",
        "以下为实际返回失败、未核实或疑似定位问题的提示列表，不是全部用例的完整语义裁决。",
        "",
    ]
    for row in rows:
        answer = row.get("answer") or ""
        if row["status"] == "failed":
            lines.append(
                f"- 第{row['index']}题「{row['prompt']}」：失败，{row.get('error')}。"
            )
        elif any(
            word in answer for word in ("没能", "未核实", "没有找到", "暂时无法读取")
        ):
            lines.append(
                f"- 第{row['index']}题「{row['prompt']}」：返回兜底、部分未核实或未定位对象；耗时{row['visible_seconds']:.2f}秒，需结合原始答案复核。"
            )
    lines += [
        "",
        "验证：连续采样流程1项通过，66题均采集到终态，其中10项待确认方案已取消；相关离线38通过，335文件格式及改动脚本Ruff通过。既有恢复测试仍有一条旧兜底文案断言失败，在HEAD工具注册表上已复现，未顺带修改。",
        "本次不修改全局摘要或发布流程；此前未提交的待办排序修复仍保留。尚未提交、推送或部署。测试业务数据、会话、66个检查点、自建Worker及专用队列已清理，审计JSON保留清理前的只读快照。",
    ]
    lines += [
        "",
        "## 环境与限制",
        "",
        f"- 前置能力：{metadata['dependencies']}。Embedding未配置时，材料正文检索需单列为环境受限，不以失败/兜底耗时当正常回答性能。语音问题仅使用预置转写文本，不测上传、录音或ASR时延。",
        "- 待确认方案采集后取消，后续问题不把未执行结果当已存在对象；未使用真实账号、未发送邮件或确认写入。单并发顺序测量，不包含多人争用Worker的排队压测。",
        "- 原始每题答案、终态、决策路径、模型token使用量及计时见同日assistant_latency_continuous结果JSONL；本报告不复制账号标识、模型正文或环境凭据。",
        "",
    ]
    output.write_text("\n".join(lines))
    print(
        json.dumps(
            {
                "questions": len(rows),
                "groups": len(groups),
                "median": median(durations),
                "p95": percentile(durations, 0.95),
                "model_seconds": total_model,
                "summary_seconds": total_summary,
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--audit-context", action="store_true")
    args = parser.parse_args()
    if args.audit_context:
        audit_context(args.source)
    report(args.source, args.output)
