"""在权限查询之后筛选原生列表，证据与计数使用同一结果。"""

from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

FILTER_TOOLS = {
    "list_todos",
    "list_events",
    "list_checklists",
    "list_meals",
    "list_preferences",
    "list_pantry",
    "list_voice_memos",
    "list_memories",
    "list_reminders",
    "list_materials",
    "list_households",
    "list_shopping",
}
DATE_FIELDS = {
    "list_todos": "due_date",
    "list_events": "start_date",
    "list_meals": "date",
    "list_voice_memos": "created_at",
    "list_memories": "created_at",
    "list_materials": "created_at",
    "list_reminders": "remind_at",
}
TEXT_FIELDS = ("title", "name", "label", "content", "transcript", "dish", "description")


class ReadFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str | None = Field(default=None, min_length=1, max_length=100)
    exclude_text: str | None = Field(default=None, min_length=1, max_length=100)
    status: str | None = Field(default=None, min_length=1, max_length=40)
    date_from: date | None = None
    date_to: date | None = None
    date_field: (
        Literal["created_at", "date", "due_date", "start_date", "remind_at"] | None
    ) = None

    @model_validator(mode="after")
    def valid_range(self):
        if (self.date_from or self.date_to) and not self.date_field:
            raise ValueError("日期筛选必须指定date_field")
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("开始日期不得晚于结束日期")
        return self


def filter_result(name, data, filters, timezone):
    if filters is None:
        return data
    if name not in FILTER_TOOLS:
        raise ValueError("该查询不支持列表筛选")
    selected = ReadFilters.model_validate(filters)
    if selected.date_field and DATE_FIELDS.get(name) != selected.date_field:
        raise ValueError("该列表不支持所选日期字段")
    rows = data.get("items")
    if not isinstance(rows, list):
        raise TypeError("查询没有可筛选的原生列表")

    if selected.status and any("status" not in row for row in rows):
        raise ValueError("该列表没有可核实的状态字段")
    if (selected.text or selected.exclude_text) and name == "list_reminders":
        raise ValueError("提醒列表不提供关联事项名称，请先查询关联事项")

    def matches(row):
        text = " ".join(str(row.get(key) or "") for key in TEXT_FIELDS).casefold()
        if selected.text and selected.text.casefold() not in text:
            return False
        if selected.exclude_text and selected.exclude_text.casefold() in text:
            return False
        if selected.status and row.get("status") != selected.status:
            return False
        if selected.date_from or selected.date_to:
            raw = row.get(selected.date_field)
            if not raw:
                return False
            if "T" in str(raw):
                value = datetime.fromisoformat(str(raw))
                if value.tzinfo is None:
                    raise ValueError("日期时间缺少时区，无法可靠筛选")
                day = value.astimezone(ZoneInfo(timezone)).date()
            else:
                day = date.fromisoformat(str(raw))
            if selected.date_from and day < selected.date_from:
                return False
            if selected.date_to and day > selected.date_to:
                return False
        return True

    result = {**data, "items": [row for row in rows if matches(row)]}
    # 分页未读全时仍不可把已加载子集声称为筛选后的完整总数。
    result["total_count"] = len(result["items"]) if data.get("complete") else None
    return result
