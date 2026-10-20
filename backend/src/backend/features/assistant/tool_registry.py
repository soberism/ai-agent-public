"""Progressive discovery for the assistant's existing capability contracts."""

import re
from dataclasses import asdict, dataclass
from functools import lru_cache

from backend.features.assistant.capabilities import CAPABILITIES, ENTRIES
from backend.features.assistant.feature_tools import contract

ALIASES = {
    "list_todos": "有什么待办 有啥待办 待办列表 现有待办",
    "get_household": "家庭成员都有谁 具体成员列出来 成员名单 家人名字 成员详情",
    "create_shared_event": "全家一起 大家的日历 家人日历 家庭共享 家庭可见日程",
    "convert_memo": "语音备忘变成待办 备忘转待办 转成一件待办",
    "edit_todo": "标记完成 完成待办 待办做完",
    "get_sharing": "查看可见范围 谁可以访问 谁能看 当前共享范围",
    "list_events": "指定日期范围 整月 本月日程",
    "list_all_events": "所有日程 全部日程 全部时间日程 不限日期 历史和未来日程",
    "list_meals": "菜单 菜谱 吃什么 餐食安排",
    "list_memories": "我的习惯 生活习惯 日常习惯 已记住的习惯",
    "list_pantry": "家里还有 还剩多少 剩余食材",
    "list_preferences": "忌口 禁忌 不能吃 饮食限制",
    "add_preference": "以后安排吃的 长期饮食偏好 花生过敏 忌口 饮食限制",
    "delete_shopping_item": "不用买了 不要这项 移除商品 划掉购物项",
    "confirm_shopping": "确认采购单 核对购物单 计划采购",
    "set_sharing": "设置可见范围 改为可见 设为可见 自己可见 家庭可见 家人可见 指定成员可见 共享 分享",
}

USAGE = {
    "list_all_events": "读取全部时间当前账号可访问的日程，无需日期参数；明确不限时间时使用，不要分年轮询，最多完整返回50条，超限明确提示",
    "list_events": "查询明确日期范围的日程，date_from和date_to必填且最多366天；全部时间查询请改用list_all_events",
    "list_households": "只列出家庭名称和成员人数，不含具体成员姓名；成员名单必须继续get_household",
    "get_household": "按household_id读取完整家庭详情，members提供真实成员display_name和role；可用于列出成员名单，不得声称无法查看名字",
    "create_event": "创建私人日程；不会共享到家庭，家庭可见的新日程请用create_shared_event",
    "create_shared_event": "新建共享给全家、家人或大家日历的日程；先list_households取得家庭ID，不能用私人create_event替代",
    "convert_memo": "将已有语音备忘转待办或日程，使用memo_id及body.target_type/title；保留来源关联，不是commit_dump或create_dump",
    "commit_dump": "仅将已有随手记daily_dump转待办，dump_id不能使用语音备忘ID",
    "create_dump": "新建随手记草稿，不会把已有语音备忘转换为待办",
    "delete_preference": "删除长期饮食偏好，preference_id来自list_preferences，不是删除AI记忆或本餐偏好",
    "delete_meal_preference": "删除指定餐食meal_id的本餐偏好，不能用长期delete_preference或delete_memory替代",
    "create_todo": "创建带截止时间的待办；普通“某时提醒我做某事”保存为带截止日期的待办，不能声称设置了独立应用内提醒",
    "add_preference": "保存长期饮食偏好或过敏限制，影响以后的餐食；不是某一餐的偏好",
    "add_meal_preference": "仅修改指定meal_id的本餐偏好，不能代替长期饮食限制",
    "edit_meal": "修改餐食字段；body.preferences会替换整份本餐偏好，追加一条偏好请用add_meal_preference以保留旧偏好",
    "add_memory": "保存一般长期记忆；饮食限制请用add_preference，表达风格请用set_preferences",
    "delete_shopping_item": "移除不再需要购买的商品，不是标记已买到",
    "delete_checklist_item": "删除不再需要的清单项，不是勾选已完成",
    "check_item": "更新已完成或未完成状态，不删除项目",
    "confirm_shopping": "将采购单标记为已计划，不改变任何商品的已买状态",
    "bulk_checklist": "更新全部条目的完成状态，不是确认采购单",
    "create_reminder": "仅支持关联真实待办或日程的单次提醒，不支持每周重复",
    "confirm_meal": "将已有餐食关联到日历并保留关联，不是独立创建日程",
    "create_shopping": "只创建空采购单，参数body.title；取得真实ID后另添加商品",
}

OPERATIONS = (
    (r"改.*可见|设.*可见|仅自己可见|分享给|共享给", "set_sharing"),
    (r"标记完成|完成待办|待办做完", "edit_todo"),
    (r"删|移除|去掉", "delete_"),
    (r"修改|编辑|改到|调整|重命名", ("edit_", "rename_", "set_", "update_")),
    (r"创建|新建|添加|加上", ("create_", "add_")),
)


@dataclass(frozen=True)
class ToolSummary:
    name: str
    description: str
    domain: str
    mode: str


@dataclass(frozen=True)
class ToolDescription:
    name: str
    description: str
    domain: str
    mode: str
    input_schema: dict


def terms(value: str) -> set[str]:
    normalized = re.sub(r"[^0-9a-zA-Z_\u4e00-\u9fff]+", " ", value.lower())
    values = {item for item in normalized.split() if item}
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", normalized))
    values.update(chinese[index : index + 2] for index in range(len(chinese) - 1))
    return values


@lru_cache
def summaries() -> tuple[ToolSummary, ...]:
    return tuple(
        ToolSummary(
            name=name,
            description=label + ("；" + USAGE[name] if name in USAGE else ""),
            domain=kind,
            mode="read" if readonly else "write",
        )
        for name, (_, label, readonly, kind, _) in CAPABILITIES.items()
    )


def search(query: str, mode: str | None = None, limit: int = 10) -> list[dict]:
    query_terms = terms(query)
    read_intent = bool(
        re.search(r"看|查|列出|多少|几个|统计|显示|还有|还剩|哪些|有什么|有啥", query)
    )
    write_intent = bool(
        re.search(r"创建|新建|添加|修改|编辑|删|移除|去掉|勾选|保存|设置", query)
    )
    operation = next(
        (prefix for pattern, prefix in OPERATIONS if re.search(pattern, query)), ()
    )
    if operation == "edit_todo" and "清单" in query:
        operation = "check_item"
    ranked = []
    for tool in summaries():
        if mode and tool.mode != mode:
            continue
        entry = CAPABILITIES[tool.name][4]
        aliases = " ".join(label for label, url in ENTRIES.values() if url == entry)
        haystack = f"{tool.name} {tool.description} {tool.domain} {aliases} {ALIASES.get(tool.name, '')}"
        haystack_terms = terms(haystack)
        score = len(query_terms & haystack_terms)
        if query.lower() in haystack.lower():
            score += 4
        if tool.domain.lower() in query.lower():
            score += 2
        if score:
            if read_intent and not write_intent and tool.mode == "read":
                score += 4
                if tool.name.startswith("list_"):
                    score += 1
            elif write_intent and not read_intent and tool.mode == "write":
                score += 4
            if operation and (
                tool.name == operation or tool.name.startswith(operation)
            ):
                score += 6
            if "里" in query and "_item" in tool.name:
                score += 2
            ranked.append((score, tool.name, tool))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    selected = ranked[:limit]
    if write_intent and not any(item[2].mode == "read" for item in selected):
        reader = next((item for item in ranked if item[2].mode == "read"), None)
        if reader and selected:
            selected[-1] = reader
    return [asdict(item[2]) for item in selected]


def describe(name: str) -> dict:
    capability = CAPABILITIES.get(name)
    if capability is None:
        raise ValueError("未知工具")
    _, label, readonly, kind, _ = capability
    _, model = contract(name)
    return asdict(
        ToolDescription(
            name=name,
            description=label + ("；" + USAGE[name] if name in USAGE else ""),
            domain=kind,
            mode="read" if readonly else "write",
            input_schema=model.model_json_schema(),
        )
    )
