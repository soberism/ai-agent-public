"""连续会话性能采样的合成数据及功能问题。"""

from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from eval_seed_family import seed_family
from eval_seed_rows import seed_row
from eval_seed_setup import dependencies
from helpers import register
from sqlalchemy.orm import Session

from backend.db.models import AssistantProfile, User
from backend.db.session import engine
from backend.features.assistant.rag import refresh_material

GROUPS = {
    "普通问答": ["你好", "简单解释一下什么是时间管理", "你能帮我做哪些事？"],
    "待办": ["有什么待办", "买牛奶什么时候到期？", "明天有哪些未完成待办？"],
    "日程": ["现在有什么日程", "全部时间日程呢", "明天的项目会议在哪里？"],
    "清单": [
        "我有哪些清单",
        "旅行准备清单里有哪些东西？",
        "旅行准备清单还有哪些没勾选？",
    ],
    "餐食": ["查看餐食计划", "待确认是什么意思", "明晚意面计划是几个人吃？"],
    "采购": ["有哪些购物清单", "早餐补货清单有哪些商品？", "早餐补货哪些已经买了？"],
    "库存": ["家里还有哪些食材", "牛奶还有多少？", "鸡蛋的库存单位是什么？"],
    "饮食偏好": ["我有哪些饮食限制", "我有没有花生过敏的记录？", "我有哪些口味偏好？"],
    "语音备忘": [
        "有什么语音备忘",
        "这些备忘的状态是什么意思",
        "把备忘的文字内容列出来",
    ],
    "家庭": ["我有几个家庭", "家庭成员都有谁？", "小林在家庭里是什么角色？"],
    "共享": [
        "项目会议现在谁可以看？",
        "查看项目会议的共享范围",
        "有哪些可选的家庭共享对象？",
    ],
    "材料": ["我有哪些材料", "保修说明在哪里？", "保修说明里的保修期限是多久？"],
    "材料目录": [
        "创建一个叫新增性能资料的目录",
        "把家电资料目录改名为性能归档",
        "删除家电资料目录",
    ],
    "长期记忆": [
        "你记住了我哪些生活习惯",
        "我保存的习惯有哪些？",
        "新增一条长期记忆：我每天早上散步。",
    ],
    "设置": ["我现在的昵称是什么", "我的时区是什么", "长期记忆功能现在开启了吗？"],
    "提醒": [
        "有哪些已启用的应用内提醒",
        "提醒测试事项的提醒时间是什么？",
        "给明天的项目会议提前十分钟设置一个应用内提醒",
    ],
    "计划回顾": ["回顾本周的计划", "本周有多少未完成待办？", "本周已完成多少待办？"],
    "随手记": [
        "记一条随手记：下周需要整理书柜。",
        "把整理书柜的随手记转成待办",
        "再记一条随手记：有空检查窗户。",
    ],
    "全局搜索": ["在应用里搜索买牛奶", "搜索旅行准备", "帮我找一下保修说明"],
    "连接入口": ["打开连接管理", "如何上传材料", "我想修改登录密码，去哪里？"],
    "联网": [
        "查一下上海现在的天气",
        "联网查一下北京今天的空气质量",
        "周末在家可以做些什么放松？",
    ],
    "操作计划": [
        "明天上午九点提醒我浇花",
        "明天下午三点安排全家开会一小时",
        "创建一份露营准备清单",
    ],
}


def seed(cloud):
    primary, _ = register(cloud)
    cookies = dict(cloud.cookies)
    cloud.cookies.clear()
    other, _ = register(cloud)
    cloud.cookies.clear()
    cloud.cookies.update(cookies)
    anchor = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    available = dependencies()
    with Session(engine) as db:
        user = db.get(User, UUID(primary["id"]))
        user.nickname = "性能测试者"
        user.timezone = "Asia/Shanghai"
        db.add(
            AssistantProfile(
                owner_id=user.id, custom_instructions="", memory_enabled=True
            )
        )
        seed_family(
            db,
            {"A": user, "B": db.get(User, UUID(other["id"]))},
            {"title": "性能测试家庭", "member_name": "小林"},
            False,
        )
        folders = {}
        objects = [
            {"kind": "todo", "title": "买牛奶", "date": "+1"},
            {"kind": "todo", "title": "整理书桌", "date": "+0", "status": "completed"},
            {"kind": "event", "title": "项目会议", "date": "+1"},
            {
                "kind": "checklist",
                "title": "旅行准备",
                "items": ["身份证", {"title": "充电器", "completed": True}],
            },
            {
                "kind": "meal",
                "title": "明晚意面计划",
                "date": "+1",
                "dish": "番茄意面",
                "diners": 3,
            },
            {
                "kind": "shopping",
                "title": "早餐补货",
                "items": ["牛奶", {"title": "燕麦", "completed": True}],
            },
            {"kind": "pantry", "title": "牛奶", "quantity": 2, "unit": "盒"},
            {"kind": "pantry", "title": "鸡蛋", "quantity": 6, "unit": "个"},
            {"kind": "preference", "title": "花生", "category": "allergy"},
            {"kind": "preference", "title": "少盐", "category": "preference"},
            {"kind": "voice", "title": "周末检查窗户"},
            {"kind": "voice", "title": "买一盆绿植"},
            {"kind": "memory", "title": "我习惯晚上阅读"},
            {"kind": "dump", "title": "下周整理书柜"},
            {"kind": "reminder", "title": "提醒测试事项", "date": "+1"},
            {"kind": "folder", "title": "家电资料"},
            {
                "kind": "material",
                "title": "保修说明",
                "folder": "家电资料",
                "text": "性能回放专用合成材料：测试电器保修期限为三年。",
            },
        ]
        for spec in objects:
            row = seed_row(db, user, spec, anchor, folders)
            if spec["kind"] == "voice":
                row.status = "draft"
            if spec["kind"] == "folder":
                folders[(user.id, spec["title"])] = row.id
            if spec["kind"] == "material" and available["embedding"]:
                refresh_material(db, row)
        db.commit()
    return available
