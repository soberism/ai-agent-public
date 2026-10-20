"""Validate native batch plan arguments against complete current-run reads."""

import re

from backend.features.assistant.plan_targets import collective_request, repair


def check_batch_coverage(state, actions):
    prompt = state["prompt"]
    daily_request = re.sub(
        r'[「“"].*?[」”"]|标题(?:为|是|叫|：|:)\s*[^，。]+', "", prompt
    )
    if re.search(r"每天|每日", daily_request) and any(
        action["tool_name"] == "create_todo" for action in actions
    ):
        return repair(
            state,
            ["create_daily_todos"],
            "请使用create_daily_todos保留用户要求的起止日期与时刻；日期范围不明确时先澄清，不能用单条create_todo代替每天创建",
            "daily-create",
        )
    if collective_request(prompt) is not None or re.search(r"待办|清单|提醒", prompt):
        return None
    if not (
        re.search(r"删|删除", prompt)
        and re.search(r"全部|所有|都", prompt)
        and "日程" in prompt
    ):
        return None
    mutations = [
        a for a in actions if a["tool_name"] in {"delete_event", "delete_events"}
    ]
    if not mutations:
        return None
    batches = [a for a in mutations if a["tool_name"] == "delete_events"]
    scopes = {
        (a["arguments"]["body"]["date_from"], a["arguments"]["body"]["date_to"])
        for a in batches
    }
    # A range-wide request binds to one complete read, never a guessed or partial list.
    reads = [
        observation
        for observation in state["observations"]
        if observation["tool_name"] == "list_events"
        and isinstance(observation.get("result"), dict)
        and observation["result"].get("complete") is True
        and not observation["result"].get("error")
        and observation["result"].get("total_count")
        == len(observation["result"].get("items", []))
        and (
            observation.get("arguments", {}).get("query", {}).get("date_from"),
            observation.get("arguments", {}).get("query", {}).get("date_to"),
        )
        in scopes
    ]
    if len(mutations) == 1 and len(batches) == 1 and reads:
        actual = [str(value) for value in batches[0]["arguments"]["body"]["event_ids"]]
        expected_sets = [
            {str(item["id"]) for item in read["result"]["items"]} for read in reads
        ]
        if len(actual) == len(set(actual)) and all(
            set(actual) == values for values in expected_sets
        ):
            return None
    return repair(
        state,
        ["list_events", "delete_events"],
        "先用list_events完整查询用户要求的日期范围，再用一项delete_events绑定相同date_from/date_to及完整event_ids；不能只选部分ID、重复ID或只删除一条",
        "range-delete",
    )
