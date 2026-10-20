"""576条回放的合成业务对象；只由隔离测试准备器调用。"""

import hashlib
from datetime import UTC, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from backend.db.cross_system_models import VoiceMemo
from backend.db.document_models import DocumentFolder, DocumentMaterial
from backend.db.life_models import LifePreference, MealPlan, PantryItem, ShoppingList
from backend.db.models import (
    AssistantMemory,
    CalendarEvent,
    Checklist,
    ChecklistItem,
    Reminder,
    Todo,
)
from backend.db.parity_models import DailyDump

ZONE = ZoneInfo("Asia/Shanghai")


def day(value, anchor):
    value = value or "+1"
    monday = anchor - timedelta(days=anchor.weekday())
    names = {
        name: monday + timedelta(days=i)
        for i, name in enumerate(
            (
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
            )
        )
    }
    names.update(
        next_monday=monday + timedelta(days=7),
        next_tuesday=monday + timedelta(days=8),
        last_week=monday - timedelta(days=3),
    )
    if value in names:
        return names[value]
    if value.startswith(("+", "-")):
        return anchor + timedelta(days=int(value))
    return datetime.fromisoformat(value).date()


def seed_row(db, user, spec, anchor, folders):
    kind, title = spec["kind"], spec["title"]
    due = day(spec.get("date"), anchor)
    at = datetime.combine(due, time(10), ZONE).astimezone(UTC)
    base = {"owner_id": user.id}
    if kind == "todo":
        status = spec.get("status", "ongoing")
        row = Todo(
            **base,
            title=title,
            description="合成回放测试对象",
            due_date=due,
            due_time=time(10),
            due_at=at,
            timezone="Asia/Shanghai",
            status=status,
            completed_at=at if status == "completed" else None,
            create_key=uuid4(),
            create_fingerprint="eval-seed",
        )
    elif kind == "event":
        row = CalendarEvent(
            **base,
            title=title,
            description="合成回放测试日程",
            location="测试会议室",
            timezone="Asia/Shanghai",
            starts_at=at,
            ends_at=at + timedelta(hours=1),
            source="app",
            status="scheduled",
        )
    elif kind in {"checklist", "shopping"}:
        row = Checklist(**base, title=title, pinned=False)
        db.add(row)
        db.flush()
        items = []
        for i, item in enumerate(spec.get("items", ["目标事项", "旁观事项"])):
            item = {"title": item} if isinstance(item, str) else item
            entry = ChecklistItem(
                checklist_id=row.id,
                title=item["title"],
                completed=item.get("completed", False),
                position=i,
            )
            db.add(entry)
            db.flush()
            items.append(
                {
                    "id": str(entry.id),
                    "name": entry.title,
                    "quantity": 1,
                    "unit": "件",
                    "category": "测试",
                    "purchased": entry.completed,
                }
            )
        if kind == "shopping":
            row = ShoppingList(
                **base,
                title=title,
                unified_checklist_id=row.id,
                items=items,
                status="draft",
            )
    elif kind == "meal":
        row = MealPlan(
            **base,
            title=title,
            schedule_text=title,
            meal_date=due,
            meal_type=spec.get("meal_type", "dinner"),
            dish=spec.get("dish", "咖喱饭"),
            diners=spec.get("diners", 3),
            preferences=[
                {"id": str(uuid4()), "label": p, "kind": "preference"}
                for p in spec.get("preferences", [])
            ],
            ingredients=[],
            status="draft",
        )
    elif kind == "preference":
        row = LifePreference(
            **base, label=title, kind=spec.get("category", "preference")
        )
    elif kind == "pantry":
        row = PantryItem(
            **base,
            name=title,
            quantity=spec.get("quantity", 2),
            unit=spec.get("unit", "盒"),
        )
    elif kind == "memory":
        row = AssistantMemory(**base, content=title, enabled=True)
    elif kind == "folder":
        row = DocumentFolder(**base, name=title)
    elif kind == "material":
        content = spec.get(
            "text", f"脱敏测试材料 {title}。仅用于回放，不包含真实个人资料。"
        )
        binary = content.encode()
        row = DocumentMaterial(
            **base,
            name=title,
            folder_id=folders.get((user.id, spec.get("folder"))),
            kind="file",
            media_type="text/plain",
            content=binary,
            size=len(binary),
            content_hash=hashlib.sha256(binary).hexdigest(),
            extracted_text=content,
            status="ready",
        )
    elif kind == "voice":
        row = VoiceMemo(
            **base,
            transcript="" if spec.get("audio") else title,
            status="uploaded" if spec.get("audio") else "ready",
        )
        if spec.get("created"):
            row.created_at = datetime.combine(
                day(spec["created"], anchor), time(9), ZONE
            )
        if spec.get("audio"):
            from pathlib import Path

            row.audio = (
                Path(__file__).parent / "fixtures" / "assistant_eval_voice.ogg"
            ).read_bytes()
            row.mime_type = "audio/ogg"
    elif kind == "dump":
        row = DailyDump(
            **base,
            source_text=title,
            candidates=[
                {"id": str(uuid4()), "title": title, "selected": True, "type": "todo"}
            ],
            status="draft",
        )
    elif kind == "reminder":
        subject = spec.get("subject", "todo")
        target = seed_row(db, user, {"kind": subject, "title": title}, anchor, folders)
        row = Reminder(
            **base,
            todo_id=target.id if subject == "todo" else None,
            event_id=target.id if subject == "event" else None,
            remind_at=at,
            timezone="Asia/Shanghai",
            status="disabled"
            if spec.get("status") == "cancelled"
            else spec.get("status", "scheduled"),
        )
    else:
        raise ValueError(f"未实现准备类型：{kind}")
    db.add(row)
    db.flush()
    if spec.get("deleted"):
        db.delete(row)
        db.flush()
    return row
