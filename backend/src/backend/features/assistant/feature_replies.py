"""Readable business results and confirmation previews, without model claims."""

from uuid import uuid4

from fastapi.encoders import jsonable_encoder

from backend.api.schemas import AssistantItem, AssistantReply
from backend.features.assistant.capabilities import CAPABILITIES, ENTRIES

LABELS = {
    "body": "内容",
    "query": "条件",
    "title": "标题",
    "description": "说明",
    "text": "随手记",
    "transcript": "备忘文字",
    "name": "名称",
    "date": "日期",
    "schedule_text": "餐食安排",
    "dish": "菜品",
    "diners": "用餐人数",
    "notes": "备注",
    "meal_type": "餐次",
    "preferences": "偏好",
    "label": "偏好内容",
    "kind": "类型",
    "quantity": "数量",
    "unit": "单位",
    "status": "状态",
    "start_date": "开始日期",
    "start_time": "开始时间",
    "end_date": "结束日期",
    "end_time": "结束时间",
    "due_date": "截止日期",
    "due_time": "截止时间",
    "date_from": "起始日期",
    "date_to": "结束日期",
    "location": "地点",
    "recurrence": "重复",
    "recurrence_until": "重复截止日期",
    "scope": "共享范围",
    "member_ids": "指定成员",
    "nickname": "昵称",
    "timezone": "时区",
    "custom_instructions": "自定义指令",
    "memory_enabled": "启用记忆",
    "content": "记忆内容",
    "enabled": "启用",
    "role": "角色",
    "permissions": "权限",
    "email": "邮箱",
    "decision": "邀请决定",
    "target_type": "转换类型",
    "candidates": "待办候选",
    "selected": "已选择",
    "type": "类型",
    "todo_id": "待办",
    "item_id": "清单项",
    "event_id": "日程",
    "checklist_id": "清单",
    "meal_id": "餐食",
    "material_id": "材料",
    "folder_id": "目录",
    "memo_id": "备忘",
    "dump_id": "随手记",
    "preference_id": "偏好",
    "household_id": "家庭",
    "member_id": "成员",
    "invitation_id": "邀请",
    "resource_id": "事项",
    "memory_id": "记忆",
    "id": "对象",
    "summary": "概览",
    "completed_todos": "已完成待办",
    "ongoing_todos": "进行中待办",
    "events": "日程",
    "checklists": "清单",
    "open_checklist_items": "未勾选清单项",
    "organize": "待整理",
    "overdue": "逾期",
    "unscheduled": "未设日期",
    "conflicts": "时间冲突",
    "households": "家庭",
    "remind_date": "提醒日期",
    "remind_time": "提醒时间",
    "remind_at": "提醒时间",
    "display_name": "成员名称",
    "relationship": "关系",
    "birth_date": "生日",
    "species": "种类",
    "breed": "品种",
    "household_name": "家庭名称",
    "error_message": "失败原因",
    "review_count": "待审核数量",
    "editable": "可编辑",
    "pinned": "已置顶",
    "audio_url": "录音入口",
    "file": "文件",
    "photo": "照片",
    "voice": "语音",
    "reminder": "提醒",
    "disabled": "已关闭",
    "app_only": "仅应用内",
    "delivery": "提醒渠道",
    "member_count": "成员数",
    "count": "数量",
    "details": "详情",
    "left": "冲突事项一",
    "right": "冲突事项二",
    "starts_at": "开始时间",
    "ends_at": "结束时间",
    "items": "事项",
    "pantry": "库存",
    "folders": "目录",
    "members": "成员",
    "invitations": "邀请",
    "total_count": "清单项总数",
    "completed_count": "已勾选数量",
    "breakfast": "早餐",
    "lunch": "午餐",
    "dinner": "晚餐",
    "snack": "加餐",
    "private": "仅自己",
    "household": "全家庭",
    "all": "全部",
    "none": "无",
    "ongoing": "进行中",
    "completed": "已完成",
    "scheduled": "已安排",
    "cancelled": "已取消",
    "uploaded": "已上传",
    "ready": "已就绪",
    "partial": "部分完成",
    "failed": "失败",
    "pending": "待处理",
    "owner": "创建者",
    "available": "可访问",
    "draft": "草稿",
    "planned": "已计划",
    "converted": "已转换",
    "committed": "已转待办",
    "allergy": "过敏限制",
    "budget": "预算",
    "preference": "偏好",
    "todo": "待办",
    "event": "日程",
    "accept": "接受",
    "reject": "拒绝",
    "removed": "移出",
    "active": "有效",
    "admin": "管理员",
    "member": "成员",
    "daily": "每天",
    "weekly": "每周",
    "day": "日",
    "week": "周",
    "range": "范围",
}


def describe(value):
    if isinstance(value, dict):
        return "；".join(
            f"{LABELS.get(k, k)}：{describe(v)}"
            for k, v in value.items()
            if k
            not in {
                "id",
                "created_at",
                "updated_at",
                "owner_id",
                "account_id",
                "folder_id",
                "todo_id",
                "event_id",
                "target_id",
                "series_id",
                "household_id",
                "member_ids",
                "event_ids",
                "assignee_id",
                "shared_household_ids",
            }
            and not k.endswith("_url")
            and v is not None
        )
    if isinstance(value, list):
        return "、".join(describe(v) for v in value) or "无"
    if isinstance(value, bool):
        return "是" if value else "否"
    return LABELS.get(str(value), str(value))


def preview(payload, labels):
    return "；".join(
        f"{LABELS.get(k, k)}：{describe(labels.get(k, v))}" for k, v in payload.items()
    )


def rows(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        if "id" in value:
            return [value]
        if "items" in value:
            return value["items"]
        if "households" in value:
            return value["households"]
    return []


def without_member_emails(value):
    if isinstance(value, dict):
        return {
            key: without_member_emails(item)
            for key, item in value.items()
            if key != "email"
        }
    if isinstance(value, list):
        return [without_member_emails(item) for item in value]
    return value


def result_reply(name, value):
    _, label, readonly, kind, entry = CAPABILITIES[name]
    data = jsonable_encoder(value)
    if name == "get_household":
        data = without_member_emails(data)
    values = rows(data)
    if name == "incoming_invitations":
        kind = "invitation"
    if name == "sharing_options":
        kind = "household"
    items = []
    for row in values[:20]:
        if "id" not in row:
            continue
        row_kind = row.get("kind", kind) if name == "search_business" else kind
        title = (
            row.get("household_name")
            or row.get("title")
            or row.get("name")
            or row.get("label")
            or row.get("transcript")
            or label
        )
        url = (
            f"/calendar/{row['id']}/edit"
            if row_kind == "event"
            else f"/checklists/{row['id']}"
            if row_kind == "checklist"
            else f"/todos/{row['id']}"
            if row_kind == "todo"
            else f"/meals/{row['id']}"
            if row_kind == "meal"
            else entry
        )
        if name == "search_business":
            url = row["url"]
        items.append(
            AssistantItem(
                id=row["id"],
                title=title[:100],
                kind=row_kind,
                status=row.get("status", "available"),
                url=url,
                due_date=row.get("due_date")
                or row.get("date")
                or row.get("start_date"),
                due_time=row.get("due_time") or row.get("start_time"),
            )
        )
    detail = describe(data) if data is not None else ""
    # ponytail: chat shows a bounded excerpt; the existing feature page contains full results.
    suffix = (
        "（内容较多，仅展示摘要，请进入功能页查看完整内容。）"
        if len(detail) > 750 or len(values) > 20
        else ""
    )
    message = f"{label}{'结果' if readonly else '已执行'}。" + detail[:750] + suffix
    return AssistantReply(
        kind="result" if readonly else "success", message=message, items=items
    )


def entry_reply(feature):
    label, url = ENTRIES[feature]
    return AssistantReply(
        kind="message",
        message=f"请在{label}页面继续操作。",
        items=[
            AssistantItem(
                id=uuid4(), title=label, kind="navigation", status="available", url=url
            )
        ],
    )
