import re
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.api.schemas import Input


class TitleInput(Input):
    title: str

    @field_validator("title")
    @classmethod
    def valid_title(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("标题不能为空")
        return value


class ChecklistCreate(TitleInput):
    title: str = Field(max_length=15)


class ChecklistItemCreate(TitleInput):
    title: str = Field(max_length=15)


class ChecklistWithItemsCreate(ChecklistCreate):
    items: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("items")
    @classmethod
    def valid_items(cls, values):
        return [ChecklistItemCreate(title=value).title for value in values]


class ChecklistItemPatch(Input):
    completed: bool


class ChecklistItemOut(BaseModel):
    id: UUID
    title: str
    completed: bool
    position: int


class ChecklistOut(BaseModel):
    meal_id: UUID | None = None
    id: UUID
    title: str
    items: list[ChecklistItemOut]
    completed_count: int
    total_count: int
    created_at: datetime
    updated_at: datetime
    source: Literal["app"] = "app"
    assignee_id: UUID
    pinned: bool = False
    shared_household_ids: list[UUID] = []


class ChecklistBulk(Input):
    completed: bool


class ChecklistShareInput(Input):
    household_id: UUID


class ChecklistList(BaseModel):
    items: list[ChecklistOut]


class ReminderCreate(Input):
    todo_id: UUID | None = Field(
        default=None,
        description="必须与 event_id 恰好提供一个；先查询待办取得真实 ID",
    )
    event_id: UUID | None = Field(
        default=None,
        description="必须与 todo_id 恰好提供一个；先查询日程取得真实 ID",
    )
    remind_date: date
    remind_time: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")

    @field_validator("remind_date", mode="before")
    @classmethod
    def valid_date(cls, value):
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("请选择有效提醒日期")
        return value

    @model_validator(mode="after")
    def one_subject(self):
        if (self.todo_id is None) == (self.event_id is None):
            raise ValueError("提醒必须关联一个待办或日程")
        return self


class ReminderPatch(Input):
    status: Literal["scheduled", "disabled"]


class ReminderOut(BaseModel):
    id: UUID
    todo_id: UUID | None
    event_id: UUID | None
    remind_at: datetime
    timezone: str
    status: Literal["scheduled", "disabled"]
    delivery: Literal["app_only"] = "app_only"
