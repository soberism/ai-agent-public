"""基于实际前后状态核对可确定的业务语义，不让completed掩盖缺项。"""


def check_semantics(record):
    issues = []
    setup, final = record.get("setup", {}), record.get("after", {})
    main = setup.get("accounts", {}).get("A")
    created_tools = {
        a["tool_name"]
        for step in record["steps"]
        if step["input"] == "approve"
        for a in step.get("actions", [])
        if a["status"] == "completed"
    }
    prompts = "\n".join(
        step["input"]
        for step in record["steps"]
        if step["input"] not in {"approve", "reject", "approve_again"}
    )
    for step in record["steps"]:
        answer = step.get("actual", {}).get("final_answer") or ""
        if record["id"] == "NEW-TODO-01" and "工作会议准备" in answer:
            issues.append(
                {
                    "category": "业务筛选语义错误",
                    "detail": "本周未完成家务结果混入工作会议准备，字段与数量可校验但不符合家务筛选",
                }
            )
        if (
            "上周" in step["input"]
            and "语音" in step["input"]
            and any(name in answer for name in ("范围外备忘", "旁观文字备忘"))
        ):
            issues.append(
                {
                    "category": "业务筛选语义错误",
                    "detail": "上周语音查询列出范围外或当前记录",
                }
            )
    required_items = []
    if "create_shopping" in created_tools:
        if "烧烤采购" in prompts:
            required_items = ["玉米", "木炭"]
        elif "早餐补货" in prompts or "早餐采购" in prompts:
            required_items = ["鸡蛋", "燕麦"]
        rows = [
            r
            for r in final.get("shopping_lists", {}).values()
            if r.get("owner_id") == main and not r["title"].startswith("旁观")
        ]
        if required_items and not any(
            set(required_items)
            <= {
                item["title"]
                for item in final.get("checklist_items", {}).values()
                if item["checklist_id"] == row.get("unified_checklist_id")
            }
            for row in rows
        ):
            issues.append(
                {
                    "category": "创建购物单遗漏商品",
                    "detail": "已执行创建，但实际商品未覆盖用户要求："
                    + "、".join(required_items),
                }
            )
    if (
        created_tools & {"create_checklist", "create_shopping"}
        and "露台整理" in prompts
    ):
        ids = {
            key
            for key, row in final.get("checklists", {}).items()
            if row["title"] == "露台整理"
        }
        names = {
            row["title"]
            for row in final.get("checklist_items", {}).values()
            if row["checklist_id"] in ids
        }
        if not {"花盆", "清洁手套"} <= names:
            issues.append(
                {
                    "category": "创建清单遗漏条目",
                    "detail": "露台整理实际缺少花盆或清洁手套",
                }
            )
    for step in record["steps"]:
        if step["input"] != "approve":
            continue
        tools = {
            a["tool_name"]
            for a in step.get("actions", [])
            if a["status"] == "completed"
        }
        for change in step.get("business_delta", []):
            old, new = change.get("before"), change.get("after")
            if not old or not new:
                continue
            if (
                "confirm_shopping" in tools
                and change["table"] == "shopping_lists"
                and old.get("items") != new.get("items")
            ):
                issues.append(
                    {
                        "category": "采购确认误改商品",
                        "detail": "确认采购同时改变商品内容或购买状态",
                    }
                )
            if (
                tools & {"add_meal_preference", "edit_meal"}
                and change["table"] == "meal_plans"
                and "少辣" in prompts
                and "这顿" in prompts
            ):
                before = {v["label"] for v in old.get("preferences", [])}
                after = {v["label"] for v in new.get("preferences", [])}
                if not before <= after:
                    issues.append(
                        {
                            "category": "追加偏好覆盖原限制",
                            "detail": "追加本餐少辣时丢失原有偏好",
                        }
                    )
            if (
                "edit_event" in tools
                and "地点改成" in prompts
                and change["table"] == "calendar_events"
                and (
                    old.get("starts_at") != new.get("starts_at")
                    or old.get("ends_at") != new.get("ends_at")
                )
            ):
                issues.append(
                    {
                        "category": "仅改地点却改时间",
                        "detail": "修改地点时改变原有起止时间",
                    }
                )
    return issues
