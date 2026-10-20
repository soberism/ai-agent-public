import re
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.api.schemas import Input

TIME = r"(?:[01]\d|2[0-3]):[0-5]\d"


class EventCreate(Input):
    title: str
    description: str | None = Field(default=None, max_length=2000)
    location: str | None = Field(default=None, max_length=200)
    start_date: date
    start_time: Annotated[str, Field(pattern=f"^{TIME}$")]
    end_date: date
    end_time: Annotated[str, Field(pattern=f"^{TIME}$")]
    todo_id: UUID | None = None
    recurrence: Literal["none", "daily", "weekly"] = "none"
    recurrence_until: date | None = None
    status: Literal["scheduled", "cancelled"] = "scheduled"

    @field_validator("title")
    @classmethod
    def title_valid(cls, value):
        value = value.strip()
        if not 1 <= len(value) <= 15:
            raise ValueError("请输入1至15个字符的日程标题")
        return value

    @field_validator("description", "location")
    @classmethod
    def blank_to_none(cls, value):
        return value.strip() or None if value else None

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def date_valid(cls, value):
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("请选择有效的日期")
        if value < "0002-01-01" or value > "9999-12-30":
            raise ValueError("请选择0002年1月1日至9999年12月30日的日期")
        return value

    @model_validator(mode="after")
    def range_valid(self):
        if (self.end_date, self.end_time) <= (self.start_date, self.start_time):
            raise ValueError("结束时间必须晚于开始时间")
        if self.recurrence != "none" and self.recurrence_until is None:
            raise ValueError("重复日程必须选择结束日期")
        if self.recurrence_until and (
            self.recurrence_until < self.start_date
            or (self.recurrence_until - self.start_date).days > 365
        ):
            raise ValueError("重复结束日期无效或超过366天")
        return self


class EventPatch(EventCreate):
    pass


class EventOut(BaseModel):
    id: UUID
    title: str
    description: str | None
    location: str | None
    todo_id: UUID | None
    series_id: UUID | None
    source: str
    status: Literal["scheduled", "cancelled"]
    assignee_id: UUID
    start_date: date
    start_time: str
    end_date: date
    end_time: str
    timezone: str
    starts_at: datetime
    ends_at: datetime
    created_at: datetime
    updated_at: datetime


class EventList(BaseModel):
    items: list[EventOut]


class EventQuery(Input):
    date_from: date
    date_to: date

    @model_validator(mode="after")
    def range_valid(self):
        if self.date_from > self.date_to or (self.date_to - self.date_from).days > 365:
            raise ValueError("日期范围无效或超过366天")
        return self


class EventBatchDelete(EventQuery):
    event_ids: list[UUID] = Field(min_length=1, max_length=50)
