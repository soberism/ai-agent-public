"""Validated, user-approved write plans for the autonomous graph."""

from langgraph.types import interrupt

from backend.features.assistant import tool_registry
from backend.features.assistant.autonomous_guards import finish, oversized_checklist
from backend.features.assistant.autonomous_types import AutonomousState, Decision
from backend.features.assistant.feature_tools import parse_arguments
from backend.features.assistant.plan_batches import check_batch_coverage
from backend.features.assistant.plan_targets import check_target_coverage


def propose(state: AutonomousState):
    decision = Decision.model_validate(state["decision"])
    if oversized_checklist(state["prompt"], decision.actions):
        return finish("单个清单最多包含 50 个条目，请拆分后再创建。")
    if state["web_results"] and (
        len(decision.actions) != 1
        or decision.actions[0].get("tool_name") != "create_checklist"
    ):
        return finish("联网搜索后只能生成一项待确认的清单草稿。")

    described = {item["name"]: item for item in state["described_tools"]}
    discovered = {item["name"]: item for item in state["discovered_tools"]}
    validated = []
    for item in decision.actions:
        name = item.get("tool_name", "")
        arguments = dict(item.get("arguments", {}))
        if name == "invite_family_member":
            name = "invite_member"
            if "body" not in arguments:
                arguments = {
                    "household_id": arguments.get("household_id"),
                    "body": {
                        key: arguments[key]
                        for key in ("email", "role")
                        if key in arguments
                    },
                }
        if name in {
            "toggle_checklist_item",
            "check_checklist_item",
            "mark_checklist_item",
        }:
            name = "check_item"
            if "completed" in arguments and "body" not in arguments:
                arguments["body"] = {"completed": arguments.pop("completed")}
        selected = described.get(name) or discovered.get(name)
        if selected is None:
            try:
                selected = tool_registry.describe(name)
            except ValueError:
                return finish(
                    "这次没能生成可确认的操作方案，未执行这项操作。可以换个说法再试一次。"
                )
        if not selected or selected["mode"] != "write":
            return finish(
                "这次没能生成可确认的操作方案，未执行这项操作。可以换个说法再试一次。"
            )
        if name not in described:
            described[name] = selected
        try:
            arguments = parse_arguments(name, arguments).model_dump(
                mode="json", exclude_unset=True
            )
        except ValueError as error:
            key = f"invalid-plan:{name}"
            if state.get("stalled_on", "").startswith(key):
                return finish(
                    "这次还没能整理好操作方案，未执行这项操作。可以重试，或补充要修改的事项及具体内容。"
                )
            return {
                "described_tools": list(described.values())[-10:],
                "stalled_on": f"{key}: {str(error)[:350]}",
            }
        validated.append(
            {
                "tool_name": name,
                "arguments": arguments,
                "description": str(item.get("description", ""))[:800],
            }
        )
    mismatch = check_target_coverage(state, validated) or check_batch_coverage(
        state, validated
    )
    if mismatch:
        return mismatch
    approval = interrupt({"kind": "action_plan", "actions": validated})
    return {
        "proposed_actions": validated,
        "approval": approval,
        "final_answer": "我已整理好操作计划，请确认要执行的项目。",
    }
