"""A small bounded LangGraph loop: decide, read live data, decide again."""

import json
import re
from collections.abc import Callable

from langgraph.graph import END, START, StateGraph

from backend.core.langsmith_tracing import observed
from backend.core.security import APIError
from backend.features.assistant.capabilities import CAPABILITIES
from backend.features.assistant.graph import Intent, parse_node
from backend.features.assistant.workflow_state import State
from backend.features.assistant.workflow_tools import MAX_READS, pending_shared_creation


def route(state: State):
    intent = state["intent"]
    if intent.action in {"inspect_before_action", "inspect_batch"}:
        return "read"
    history = state["history"][-2:]
    choosing_target = history and re.search(
        r"哪.?位|哪.?条|哪个|请选择|想移出|要移出谁", history[-1]["content"]
    )
    context = (
        " ".join([state["message"], *(item["content"] for item in history)])
        if choosing_target
        else state["message"]
    )
    wants_change = re.search(
        r"删除|移出|移除|修改|编辑|更新|创建|新增|添加|设置|勾选|(?<!已)完成|保存|邀请|接受|拒绝|退出",
        context,
    )
    if (
        wants_change or pending_shared_creation(state["message"], state["history"])
    ) and (
        intent.action in {"search_systems", "query_todos"}
        or (
            intent.action == "feature"
            and intent.feature in CAPABILITIES
            and CAPABILITIES[intent.feature][2]
        )
    ):
        return "read"
    return END


def read_node(state: State):
    intent = state["intent"]
    if intent.action == "inspect_batch":
        calls = intent.payload["calls"]
    elif intent.action == "search_systems":
        calls = [
            {
                "feature": intent.action,
                "payload": {"query": intent.query, "target_type": intent.target_type},
            }
        ]
    elif intent.action == "query_todos":
        calls = [
            {
                "feature": intent.action,
                "payload": intent.model_dump(
                    include={"status", "due", "due_time", "date_from", "date_to"},
                    exclude_none=True,
                ),
            }
        ]
    else:
        calls = [{"feature": intent.feature, "payload": intent.payload}]
    if state.get("reads", 0) + len(calls) > MAX_READS or state.get("reader") is None:
        return {
            "intent": Intent(
                action="clarify",
                message="还需要更多实时信息才能可靠处理，请缩小范围后再试。",
            ),
            "stop": True,
        }
    try:
        seen = list(state.get("seen_reads", []))
        observations = []
        for call in calls:
            key = json.dumps(call, ensure_ascii=False, sort_keys=True)
            if key in seen:
                observations.append(f"{call['feature']}: 重复查询已跳过")
                continue
            seen.append(key)
            observations.append(
                f"{call['feature']}: {state['reader'](call['feature'], call['payload'])}"
            )
    except APIError as error:
        if error.status not in (404, 422):
            raise
        return {"intent": Intent(action="clarify", message=error.message), "stop": True}
    previous = state.get("observation", "")
    return {
        "observation": "\n".join([previous, *observations]).strip(),
        "reads": state.get("reads", 0) + len(calls),
        "seen_reads": seen,
    }


def after_read(state: State):
    return END if state.get("stop") else "parse"


builder = StateGraph(State)
builder.add_node("parse", parse_node)
builder.add_node("read", read_node)
builder.add_edge(START, "parse")
builder.add_conditional_edges("parse", route)
builder.add_conditional_edges("read", after_read)
graph = builder.compile()


@observed
def run(state: State, reader: Callable[[str, dict], str] | None = None) -> Intent:
    return graph.invoke({**state, "reader": reader, "reads": 0})["intent"]
