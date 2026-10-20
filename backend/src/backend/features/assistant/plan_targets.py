"""Match collective mutations to the preceding authorized result set."""

import re

from backend.features.assistant import tool_registry
from backend.features.assistant.feature_targets import PARAM_KINDS

KINDS = {"待办": "todo", "日程": "event", "清单": "checklist", "提醒": "reminder"}
OPERATIONS = (
    (r"删(?:除|掉)?", "delete", {}),
    (r"(?:标记为|标记|设为)?(?:已)?完成|勾选|全部勾选", "complete", {}),
    (r"取消完成|恢复未完成|取消勾选|标记未完成", "uncomplete", {}),
    (
        r"(?:设为|改为|改成|设置为|设成)?(?:仅自己可见|自己可见|私有)",
        "share",
        {"scope": "private"},
    ),
    (
        r"(?:设为|改为|改成|设置为|设成)?(?:家庭可见|全家庭可见)",
        "share",
        {"scope": "household"},
    ),
    (r"(?:共享给|分享给).+", "share", {}),
    (r"关闭(?:提醒)?|停用(?:提醒)?", "disable", {}),
    (r"开启(?:提醒)?|启用(?:提醒)?", "enable", {}),
    (r"(?:改到|调整到).+", "edit", {}),
)


def collective_request(prompt):
    match = re.fullmatch(
        r"(?:那就|那么|帮我)?(?:把)?(?:这些|它们|刚才查到的)?"
        r"(?P<kind>待办|日程|清单|提醒)?(?:都|全部|所有|全都|统统)"
        r"(?P<after_kind>待办|日程|清单|提醒)?(?:都)?(?P<verb>.+?)(?:吧|了|一下)?[。！! ]*",
        prompt.strip(),
    )
    if not match:
        return None
    for pattern, operation, changes in OPERATIONS:
        if re.fullmatch(pattern, match["verb"]):
            return operation, KINDS.get(match["kind"] or match["after_kind"]), changes
    return None


def named_request(state):
    prompt = state["prompt"]
    if re.search(
        r"不要|别|除了|除外|只|保留|保持|不改|不动|改名|重命名|名字|标题|叫|复制|创建|新建|添加",
        prompt,
    ):
        return None
    candidates = state.get("last_results", [])
    if not candidates:
        return None
    labels = sorted({item["title"] for item in candidates}, key=len, reverse=True)
    mentioned = set(re.findall("|".join(map(re.escape, labels)), prompt))
    rows = [item for item in candidates if item["title"] in mentioned]
    if len({item["title"] for item in rows}) != len(rows):
        return None
    if len(rows) < 2:
        return None
    names = "|".join(re.escape(item["title"]) for item in rows)
    if not re.search(rf"(?:{names})[」”]?[、和及与][「“]?(?:{names})", prompt):
        return None
    verbs = (
        (r"删(?:除|掉)?", "delete", {}),
        (r"取消完成|取消勾选", "uncomplete", {}),
        (r"完成|勾选", "complete", {}),
        (r"仅自己可见|自己可见", "share", {"scope": "private"}),
        (r"家庭可见|共享|分享", "share", {}),
        (r"关闭|停用", "disable", {}),
        (r"开启|启用", "enable", {}),
        (r"改到|调整到", "edit", {}),
    )
    operation_text = prompt
    for item in rows:
        operation_text = operation_text.replace(item["title"], "")
    found = [
        (operation, changes)
        for pattern, operation, changes in verbs
        if re.search(pattern, operation_text)
    ]
    if any(operation == "uncomplete" for operation, _ in found):
        found = [
            (operation, changes)
            for operation, changes in found
            if operation != "complete"
        ]
    if len(found) != 1:
        return None
    operation, changes = found[0]
    return (operation, None, changes), rows


def expected_tool(kind, operation):
    if operation == "share":
        return "set_sharing", "resource_id"
    if operation in {"complete", "uncomplete"}:
        return {
            "todo": ("edit_todo", "id"),
            "checklist": ("bulk_checklist", "checklist_id"),
        }.get(kind)
    if operation in {"disable", "enable"}:
        return ("edit_reminder", "reminder_id") if kind == "reminder" else None
    prefix = "delete_" if operation == "delete" else "edit_"
    for name, capability in tool_registry.CAPABILITIES.items():
        if not name.startswith(prefix) or capability[2] or capability[3] != kind:
            continue
        fields = tool_registry.contract(name)[1].model_fields
        if "item_id" in fields:
            continue
        for field, domain in PARAM_KINDS.items():
            if domain == kind and field in fields:
                return name, field
    return None


def changed_as_requested(action, operation, changes):
    body = action["arguments"].get("body", {})
    if operation in {"complete", "uncomplete"}:
        done = operation == "complete"
        return (
            body.get("completed") is done
            if action["tool_name"] == "bulk_checklist"
            else body.get("status") == ("completed" if done else "ongoing")
        )
    if operation in {"disable", "enable"}:
        return body.get("status") == (
            "disabled" if operation == "disable" else "scheduled"
        )
    if operation == "share" and not changes:
        return body.get("scope") in {"household", "members"}
    return all(body.get(key) == value for key, value in changes.items())


def repair(state, tools, expected, operation):
    from backend.features.assistant.autonomous_guards import finish

    key = "invalid-plan:target-coverage"
    if state.get("stalled_on", "").startswith(key):
        return finish("批量操作计划尚未完整匹配目标，请明确范围后重试；没有执行操作。")
    described = {item["name"]: item for item in state["described_tools"]}
    for name in tools:
        described[name] = tool_registry.describe(name)
    return {
        "described_tools": list(described.values())[-10:],
        "stalled_on": f"{key}: 批量{operation}计划必须恰好覆盖以下目标，参数也须符合本轮要求，不得遗漏、重复或加入其他对象："
        + expected,
    }


def check_target_coverage(state, actions):
    from backend.features.assistant.autonomous_guards import finish

    request = collective_request(state["prompt"])
    named = named_request(state) if request is None else None
    if request is None and named is None:
        return None
    if named:
        request, rows = named
    else:
        rows = [
            item
            for item in state.get("last_results", [])
            if item.get("reference_origin", "last_result") == "last_result"
        ]
    operation, requested_kind, changes = request
    targets = {
        (item["kind"], str(item["id"])): item
        for item in rows
        if requested_kind is None or item["kind"] == requested_kind
    }
    if not targets:
        return finish("没有可核对的上一轮查询结果，请明确要操作的事项。")
    bindings = {kind: expected_tool(kind, operation) for kind, _ in targets}
    if not all(bindings.values()):
        return finish("上一轮结果包含不支持这项批量操作的类型，请明确需要操作的事项。")
    actual, valid = [], True
    sharing = []
    for action in actions:
        name, args = action["tool_name"], action["arguments"]
        if name == "delete_events" and operation == "delete":
            actual.extend(("event", str(value)) for value in args["body"]["event_ids"])
            continue
        for kind, (tool, field) in bindings.items():
            if name == tool and (name != "set_sharing" or args.get("kind") == kind):
                value = str(args[field])
                matches = [
                    key
                    for key, item in targets.items()
                    if key[0] == kind and value in {key[1], item["title"]}
                ]
                actual.append(matches[0] if len(matches) == 1 else (kind, value))
                valid = valid and changed_as_requested(action, operation, changes)
                if operation == "share":
                    sharing.append(args["body"])
                break
        else:
            actual.append(("unexpected_operation", name))
    valid = valid and (not sharing or all(body == sharing[0] for body in sharing))
    if valid and set(actual) == set(targets) and len(actual) == len(targets):
        return None
    expected = "、".join(
        f"{kind}「{item['title']}」(ID:{identifier})"
        for (kind, identifier), item in targets.items()
    )
    return repair(state, [tool for tool, _ in bindings.values()], expected, operation)
