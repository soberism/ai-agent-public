"""Small guards for ambiguous autonomous plans."""

import re

from langgraph.graph import END

from backend.features.assistant.autonomous_model import same_todo_target
from backend.features.assistant.autonomous_types import AutonomousState, Decision
from backend.features.assistant.capabilities import CAPABILITIES


def finish(message: str):
    return {
        "decision": Decision(action="final_answer", answer=message).model_dump(),
        "final_answer": message,
    }


def incomplete_query(state, *, knowledge=False):
    if knowledge:
        return finish(
            "这次还没能整理出资料中的完整答案。可以再试一次，或告诉我具体的资料名称和想查的内容。"
        )
    decision = state.get("decision") or {}
    names = [item.get("tool_name") for item in state.get("observations", [])]
    names.extend([decision.get("tool_name"), *decision.get("names", [])])
    domains = {CAPABILITIES[name][3] for name in names if name in CAPABILITIES}
    if domains == {"event"}:
        return finish(
            "这次没能完成日程查询。可以再试一次；也可以先查“本月”或“下个月”的安排。"
        )
    return finish("这次没能完成查询。可以再试一次，或告诉我最想先确认的那一项。")


def stall(state: AutonomousState, key: str, message: str):
    if state.get("stalled_on") == key:
        return finish(message)
    return {"stalled_on": key}


def named_todo_mismatch(state, tool_name, result, selected, described):
    if tool_name != "get_todo":
        return None
    requested = re.search(r"[「“]([^」”]+)[」”]\s*(?:这条)?待办", state["prompt"])
    items = result.get("items", []) if isinstance(result, dict) else []
    if not requested or not items:
        return None
    title = items[0].get("title", "")
    if (
        requested[1] == title
        or (
            min(len(requested[1]), len(title)) >= 2
            and (requested[1] in title or title in requested[1])
        )
        or same_todo_target(requested[1], title)
    ):
        return None
    key = f"invalid-read:target-mismatch:get_todo:{requested[1]}"
    if state.get("stalled_on", "").startswith(key):
        return finish(f"没有查到「{requested[1]}」这条待办的详情。")
    return {
        "stalled_on": f"{key}; 本次读取的是另一条待办，请按用户指定的完整标题重新查询",
        "described_tools": [*state["described_tools"], selected][-10:]
        if selected["name"] not in described
        else state["described_tools"],
    }


def after_step(state: AutonomousState):
    return END if state["decision"]["action"] == "final_answer" else "reason"


def oversized_checklist(prompt: str, actions: list[dict]) -> bool:
    if not any(
        item.get("tool_name") in {"create_checklist", "add_checklist_item"}
        for item in actions
    ):
        return False
    count = re.search(
        r"(?:([0-9]+)|([一二三四五六七八九])十([一二三四五六七八九]?))个?条目",
        prompt,
    )
    if not count:
        return False
    digits = "一二三四五六七八九"
    requested = (
        int(count[1])
        if count[1]
        else (digits.index(count[2]) + 1) * 10
        + (digits.index(count[3]) + 1 if count[3] else 0)
    )
    return requested > 50


def preflight(prompt: str) -> str | None:
    if re.search(r"创建|新建|添加", prompt) and oversized_checklist(
        prompt, [{"tool_name": "create_checklist"}]
    ):
        return "单个清单最多包含 50 个条目，请拆分后再创建。"
    if (
        re.search(r"昨天|前天", prompt)
        and re.search(r"明天|后天", prompt)
        and re.search(r"安排|创建|新建", prompt)
        and not re.search(r"改|挪|移|调整", prompt)
    ):
        return "你同时提到了过去和未来的时间，请确认会议具体安排在哪一天、几点。"
    return None
