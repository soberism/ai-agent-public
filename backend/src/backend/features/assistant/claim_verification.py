"""Match each claim against current-run evidence, never against answer wording."""

import json
from datetime import date, timedelta

from backend.features.assistant.answer_evidence import catalog, count_source, pointer
from backend.features.assistant.claim_labels import LABELS, STATUSES, display_value


def same(left, right):
    return json.dumps(left, sort_keys=True, ensure_ascii=False) == json.dumps(
        right, sort_keys=True, ensure_ascii=False
    )


def count_value(claim, records):
    sources, intervals = [], []
    partitioned = False
    for record in records:
        if record["source"] != "business":
            raise ValueError("总数必须来自业务查询")
        expected = dict(record["scope"])
        if record["tool"] == "review_plan" and claim.domain == "checklist":
            expected = {}  # The review's checklist counter is global, not date-filtered.
        if record["tool"] == "review_plan" and claim.domain == "todo":
            expected["status"] = claim.scope.get("status")
        if not same(expected, claim.scope):
            filters = {
                k: v for k, v in expected.items() if k not in {"date_from", "date_to"}
            }
            requested = {
                k: v
                for k, v in claim.scope.items()
                if k not in {"date_from", "date_to"}
            }
            if not same(filters, requested):
                raise ValueError("查询筛选条件不匹配")
            start, end = (
                date.fromisoformat(expected["date_from"]),
                date.fromisoformat(expected["date_to"]),
            )
            left, right = (
                date.fromisoformat(claim.scope["date_from"]),
                date.fromisoformat(claim.scope["date_to"]),
            )
            if not left <= start <= end <= right:
                raise ValueError("查询日期不能覆盖结论范围")
            intervals.append((start, end))
            partitioned = True
        else:
            if claim.scope.get("date_from") and claim.scope.get("date_to"):
                intervals.append(
                    (
                        date.fromisoformat(claim.scope["date_from"]),
                        date.fromisoformat(claim.scope["date_to"]),
                    )
                )
        sources.append(count_source(record, claim.domain, claim.scope))
    if partitioned:
        covered = date.fromisoformat(claim.scope["date_from"])
        for start, end in sorted(intervals):
            if start > covered:
                raise ValueError("日期区间存在未查询空缺")
            covered = max(covered, end + timedelta(days=1))
        if covered <= date.fromisoformat(claim.scope["date_to"]):
            raise ValueError("日期区间未查询完整")
        if any(ids is None for _, ids in sources):
            raise ValueError("跨区间合并需要对象ID去重")
        value = len(set().union(*(ids for _, ids in sources)))
    else:
        if len({count for count, _ in sources}) != 1:
            raise ValueError("同范围查询数量冲突")
        sets = [ids for _, ids in sources if ids is not None]
        if sets and any(ids != sets[0] for ids in sets):
            raise ValueError("同范围查询对象冲突")
        value = sources[0][0]
    if not same(value, claim.value):
        raise ValueError("结论数量与查询结果不一致")
    label = (
        display_value(claim.domain, "status", claim.scope["status"])
        if claim.scope.get("status") is not None
        else ""
    ) + LABELS.get(claim.domain, claim.domain)
    start, end = claim.scope.get("date_from"), claim.scope.get("date_to")
    period = f"{start}至{end}，" if start and end else "查询范围内，"
    if claim.scope.get("range") == "all":
        period = "全部时间，"
    return f"{period}{label}{value}项。" + count_details(claim, records)


def count_details(claim, records):
    items = {}
    for record in records:
        result = record["result"]
        if record["tool"] == "get_household" and claim.domain == "household_member":
            rows = [
                {**member, "title": member.get("display_name") or "未命名成员"}
                for member in result.get("members", [])
            ]
        elif record["tool"] == "review_plan":
            group = (
                "events"
                if claim.domain == "event"
                else "completed"
                if claim.scope.get("status") == "completed"
                else "ongoing"
            )
            rows = result.get("details", {}).get(group, [])
        else:
            rows = result.get("items", [])
        for row in rows:
            if (
                isinstance(row, dict)
                and row.get("id")
                and (
                    row.get("title")
                    or row.get("name")
                    or row.get("label")
                    or row.get("content")
                    or row.get("transcript")
                    or row.get("remind_at")
                )
            ):
                items[str(row["id"])] = row
    lines = []
    for row in list(items.values())[:20]:
        if claim.domain == "event":
            start = " ".join(
                str(row[k]) for k in ("start_date", "start_time") if row.get(k)
            )
            end = " ".join(str(row[k]) for k in ("end_date", "end_time") if row.get(k))
            timing = "—".join(part for part in (start, end) if part) or "时间未设置"
        elif claim.domain == "meal":
            timing = "；".join(
                str(value)
                for value in (
                    row.get("date") or "日期未设置",
                    STATUSES.get(row.get("meal_type"), row.get("meal_type")),
                    row.get("dish"),
                    f"{row['diners']}人" if row.get("diners") is not None else None,
                    display_value(claim.domain, "status", row["status"], row)
                    if row.get("status") is not None
                    else None,
                )
                if value is not None
            )
        elif claim.domain == "todo":
            timing = (
                " ".join(str(row[k]) for k in ("due_date", "due_time") if row.get(k))
                or "不设截止日期"
            )
        else:
            timing = "；".join(
                f"{LABELS[key]}：{display_value(claim.domain, key, row[key], row)}"
                for key in (
                    "role",
                    "quantity",
                    "unit",
                    "kind",
                    "status",
                    "enabled",
                    "member_count",
                    "total_count",
                    "completed_count",
                )
                if row.get(key) is not None
            )
        title = next(
            (
                row[k]
                for k in (
                    "title",
                    "name",
                    "label",
                    "content",
                    "transcript",
                    "remind_at",
                )
                if row.get(k)
            ),
            "事项",
        )
        line = f"「{title}」" + (f"：{timing}" if timing else "")
        if sum(map(len, lines)) + len(line) > 2400:
            break
        lines.append(line)
    if len(items) > len(lines):
        lines.append(f"仅展示前{len(lines)}项，请缩小查询范围查看其余事项。")
    return "\n" + "\n".join(lines) if lines else ""


def field_value(claim, records):
    if (
        len(records) != 1
        or records[0]["source"] != "business"
        or not records[0]["success"]
    ):
        raise ValueError("对象字段需要一条成功业务证据")
    record = records[0]
    if not same(record["scope"], claim.scope):
        raise ValueError("对象字段的查询范围不匹配")
    value, ancestors = pointer(record["result"], claim.path)
    owner = next(
        (
            item
            for item in reversed(ancestors)
            if isinstance(item, dict) and item.get("id")
        ),
        None,
    )
    domain = record["domain"]
    if record["tool"] == "review_plan" and owner:
        for group in ("completed", "ongoing", "events"):
            if any(
                str(item.get("id")) == str(owner["id"])
                for item in record["result"].get("details", {}).get(group, [])
            ):
                domain = "event" if group == "events" else "todo"
                break
    if domain != claim.domain:
        raise ValueError("对象字段的业务类型不匹配")
    if owner:
        if str(owner["id"]) != claim.subject_id:
            raise ValueError("对象引用不匹配")
    elif claim.subject_id or len(ancestors) != 1:
        raise ValueError("对象引用不匹配")
    owner = owner or {}
    field = claim.path.rsplit("/", 1)[-1]
    if isinstance(value, (dict, list)):
        raise TypeError("请引用具体字段，不能发布原始业务对象")
    if field not in LABELS or not same(value, claim.value):
        raise ValueError("字段不支持或值与原始结果不一致")
    title = (
        owner.get("title")
        or owner.get("name")
        or owner.get("display_name")
        or (owner.get("transcript") or "")[:100]
        or LABELS.get(claim.domain, "该事项")
    )
    if value is None:
        display = "未设置"
    elif isinstance(value, bool):
        display = "是" if value else "否"
    elif isinstance(value, str):
        display = display_value(claim.domain, field, value, owner)
    else:
        display = str(value)
    label = LABELS[field]
    if claim.domain == "event" and field in {"due_date", "due_time"}:
        label = "开始日期" if field == "due_date" else "开始时间"
    return f"「{title}」的{label}：{display}。"


def quote_value(claim, records):
    if len(records) != 1 or records[0]["source"] not in {"document", "web"}:
        raise ValueError("资料结论缺少本轮资料来源")
    result = records[0]["result"]
    text = result.get("content") or result.get("snippet") or result.get("text") or ""
    if (
        not isinstance(claim.value, str)
        or not claim.value
        or len(claim.value) > 1200
        or claim.value not in text
    ):
        raise ValueError("引用与本轮资料原文不一致")
    return f"{result.get('title') or '资料'}：{claim.value}"


def verify(state, claims):
    evidence = catalog(state)
    accepted, errors = [], []
    for index, claim in enumerate(claims, 1):
        try:
            records = [evidence[key] for key in dict.fromkeys(claim.evidence_ids)]
            if claim.kind == "execution":
                raise ValueError("规划阶段没有已执行操作证据；审批不代表执行成功")
            verifier = {
                "count": count_value,
                "field": field_value,
                "quote": quote_value,
            }[claim.kind]
            rendered = verifier(claim, records)
            if rendered not in accepted:
                accepted.append(rendered)
        except ValueError, KeyError, TypeError, IndexError:
            errors.append(
                f"结论{index}缺少匹配的本轮证据：请核对类型、范围、对象、字段值及完整性"
            )
    return accepted, errors
