"""Project only this run's authorized reads into stable evidence records."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from backend.features.assistant.capabilities import CAPABILITIES

LIST_DOMAINS = {
    "list_todos": "todo",
    "query_todos": "todo",
    "list_events": "event",
    "list_all_events": "event",
    "list_checklists": "checklist",
    "list_meals": "meal",
    "list_preferences": "preference",
    "list_pantry": "pantry",
    "list_voice_memos": "voice_memo",
    "list_memories": "memory",
    "list_reminders": "reminder",
    "list_materials": "document",
    "list_households": "household",
    "list_shopping": "shopping",
}
REVIEW_FIELDS = {
    "completed_todos": ("todo", "completed"),
    "ongoing_todos": ("todo", "ongoing"),
    "events": ("event", ""),
    "checklists": ("checklist", ""),
}


def scope_for(query, timezone):
    scope = {
        key: value
        for key, value in query.items()
        if key not in {"limit", "cursor"} and value is not None
    }
    due = scope.pop("due", "all")
    today = datetime.now(ZoneInfo(timezone)).date()
    if due in {"today", "tomorrow", "next7"}:
        start = today + timedelta(days=1 if due == "tomorrow" else 0)
        scope.update(
            date_from=start.isoformat(),
            date_to=(start + timedelta(days=6 if due == "next7" else 0)).isoformat(),
        )
    elif due != "all":
        scope["due"] = due
    return scope


def catalog(state):
    timezone = state.get("timezone", "Asia/Shanghai")
    records = {}
    for index, observation in enumerate(state["observations"], 1):
        tool = observation.get("tool_name", "")
        result = observation.get("result")
        if not isinstance(result, dict):
            continue
        query = observation.get("arguments", {}).get("query", {})
        if tool == "query_todos":
            query = observation.get("arguments", {})
        if tool == "search_business":
            query = {"q": observation.get("arguments", {}).get("q")}
        query = {**query, **(observation.get("arguments", {}).get("filters") or {})}
        if tool == "list_all_events":
            query = {"range": "all"}
        if tool == "get_household":
            query = {"household_id": str(result.get("id", ""))}
        scope = scope_for(query, timezone)
        if tool in {"list_todos", "query_todos"}:
            scope.setdefault("status", "ongoing")
        domain = (
            LIST_DOMAINS.get(tool)
            or (CAPABILITIES.get(tool) or (None, None, None, ""))[3]
        )
        records[f"read-{index}"] = {
            "source": "business",
            "tool": tool,
            "domain": domain,
            "scope": scope,
            "result": result,
            "success": not result.get("error")
            and result.get("status", "success") not in {"error", "failed", "partial"},
        }
    for source, values in (
        ("document", state["knowledge"]),
        ("web", state.get("web_results", [])),
    ):
        for index, value in enumerate(values, 1):
            records[f"{source}-{index}"] = {
                "source": source,
                "result": value,
                "success": True,
            }
    return records


def pointer(value, path):
    if not path.startswith("/"):
        raise ValueError("字段必须使用JSON Pointer")
    ancestors = []
    for token in path[1:].split("/"):
        ancestors.append(value)
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list):
            if not token.isdecimal() or str(int(token)) != token:
                raise ValueError("无效的列表字段路径")
            value = value[int(token)]
        else:
            value = value[token]
    return value, ancestors


def count_source(record, domain, scope):
    result, tool = record["result"], record["tool"]
    if not record["success"] or result.get("complete") is not True:
        raise ValueError("查询失败或不完整，不能证明总数")
    if tool == "review_plan":
        fields = [
            field
            for field, (kind, status) in REVIEW_FIELDS.items()
            if kind == domain and status == scope.get("status", "")
        ]
        if len(fields) != 1:
            raise ValueError("回顾统计类型或状态不匹配")
        value = result.get("summary", {}).get(fields[0])
        if type(value) is not int or value < 0:
            raise ValueError("缺少可信统计字段")
        return value, None
    if tool == "get_household" and domain == "household_member":
        items = result.get("members")
        if not isinstance(items, list):
            raise ValueError("家庭详情缺少完整成员列表")
        result = {"items": items, "total_count": len(items)}
    elif LIST_DOMAINS.get(tool) != domain:
        raise ValueError("查询业务类型不匹配")
    items, total = result.get("items"), result.get("total_count")
    if not isinstance(items, list) or type(total) is not int or total != len(items):
        raise ValueError("总数与完整列表不一致")
    if not items:
        return 0, set()
    if any(not isinstance(item, dict) or not item.get("id") for item in items):
        raise ValueError("列表缺少可去重的对象ID")
    ids = [str(item["id"]) for item in items]
    if len(set(ids)) != len(ids):
        raise ValueError("列表中存在重复对象")
    return len(ids), set(ids)
