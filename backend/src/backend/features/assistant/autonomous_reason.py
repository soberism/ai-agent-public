"""Select the next action without carrying execution state across turns."""

import re

from langgraph.runtime import Runtime

from backend.features.assistant.autonomous_guards import (
    finish,
    incomplete_query,
    preflight,
)
from backend.features.assistant.autonomous_types import (
    AutonomousContext,
    AutonomousState,
)


def reason(state: AutonomousState, runtime: Runtime[AutonomousContext]):
    warning = preflight(state["prompt"])
    if warning:
        return finish(warning)
    if (
        re.fullmatch(
            r"(?:那就|就)?(?:帮我)?(?:创建|新建|安排)(?:一个|一份)?吧?[。！! ]*",
            state["prompt"],
        )
        and state["history"]
        and state["history"][-1]["role"] == "assistant"
        and re.search(r"餐食计划|菜单安排|哪一餐", state["history"][-1]["content"])
    ):
        return finish("可以，请告诉我想安排哪一天、哪一餐、吃什么。")
    if state["iteration"] >= runtime.context.max_iterations:
        return incomplete_query(state)
    decision = runtime.context.decide(state)
    if state.get("web_results") and decision.action in {
        "read_api",
        "retrieve_knowledge",
        "web_search",
    }:
        decision = runtime.context.decide(
            {**state, "stalled_on": "web-search-complete"}
        )
        if decision.action in {"read_api", "retrieve_knowledge", "web_search"}:
            return finish("联网搜索后不能读取应用内数据或再次搜索，请分开提问。")
    return {
        "requires_current_data": state.get("requires_current_data", False)
        or decision.requires_current_data,
        "resolved_request": decision.resolved_request
        or state.get("resolved_request", ""),
        "decision": decision.model_dump(mode="json"),
        "iteration": state["iteration"] + 1,
        "final_answer": decision.answer if decision.action == "final_answer" else "",
    }
