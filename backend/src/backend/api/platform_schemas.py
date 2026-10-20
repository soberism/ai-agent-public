from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from backend.api.calendar_schemas import EventOut
from backend.api.schemas import Input, TodoOut


class PlatformSettings(BaseModel):
    id: UUID
    email: str
    nickname: str | None
    timezone: str
    has_todos: bool


class PlatformSettingsPatch(Input):
    nickname: str | None = None
    timezone: str | None = None

    @field_validator("nickname")
    @classmethod
    def valid_nickname(cls, value):
        if value is None:
            return value
        value = value.strip()
        if not 1 <= len(value) <= 30:
            raise ValueError("昵称请输入1至30个字符")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        if value != "Asia/Shanghai":
            raise ValueError("仅支持上海时区（UTC+8），不支持修改")
        return value

    @model_validator(mode="after")
    def valid_patch(self):
        if not self.model_fields_set:
            raise ValueError("请提供要修改的设置")
        if "nickname" in self.model_fields_set and self.nickname is None:
            raise ValueError("昵称不能为空")
        if "timezone" in self.model_fields_set and self.timezone is None:
            raise ValueError("时区不能为空")
        return self


class TodoSummary(BaseModel):
    count: int
    items: list[TodoOut]


class PlatformHome(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    timezone: str
    server_time: datetime
    today: TodoSummary
    overdue: TodoSummary
    recent: list[TodoOut]
    recent_events: list[EventOut]
