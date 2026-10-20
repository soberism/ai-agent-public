import re
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.api.suggestion_schemas import Suggestion


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmailInput(Input):
    email: str

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        value = value.strip().lower()
        try:
            validate_email(value, check_deliverability=False)
        except EmailNotValidError:
            raise ValueError("请输入有效的邮箱") from None
        if len(value) > 254:
            raise ValueError("邮箱最多254个字符")
        return value


class Login(EmailInput):
    password: Annotated[str, Field(min_length=12, max_length=128)]


class VerificationSent(BaseModel):
    expires_in: int = 600
    retry_after: int = 60


class Register(Login):
    verification_code: str = Field(pattern=r"^[0-9]{6}$")
    confirm_password: Annotated[str, Field(min_length=12, max_length=128)]

    @model_validator(mode="after")
    def confirmed(self):
        if self.password != self.confirm_password:
            raise ValueError("两次密码输入不一致")
        return self


class PasswordChange(Input):
    current_password: Annotated[str, Field(min_length=12, max_length=128)]
    new_password: Annotated[str, Field(min_length=12, max_length=128)]
    confirm_password: Annotated[str, Field(min_length=12, max_length=128)]

    @model_validator(mode="after")
    def confirmed(self):
        if self.new_password != self.confirm_password:
            raise ValueError("两次密码输入不一致")
        if self.new_password == self.current_password:
            raise ValueError("新密码不能与原密码相同")
        return self


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: str
    nickname: str | None
    timezone: str


class TodoCreate(Input):
    title: str
    description: str | None = Field(default=None, max_length=2000)
    due_date: date | None = None
    due_time: str | None = None

    @field_validator("title")
    @classmethod
    def title_valid(cls, value):
        value = value.strip()
        if not 1 <= len(value) <= 15:
            raise ValueError("请输入1至15个字符的待办标题")
        return value

    @field_validator("description")
    @classmethod
    def description_valid(cls, value):
        return value or None

    @field_validator("due_date", mode="before")
    @classmethod
    def date_valid(cls, value):
        if value is not None and (
            not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
        ):
            raise ValueError("请选择有效的日期")
        if isinstance(value, str) and (value < "0002-01-01" or value > "9999-12-30"):
            raise ValueError("请选择0002年1月1日至9999年12月30日的日期")
        return value

    @field_validator("due_time")
    @classmethod
    def time_valid(cls, value):
        if value is not None and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("请选择有效的时间")
        return value

    @model_validator(mode="after")
    def date_time_valid(self):
        if self.due_time and not self.due_date:
            raise ValueError("设置截止时间前请选择日期")
        return self


class TodoDailyCreate(Input):
    title: str
    description: str | None = Field(default=None, max_length=2000)
    date_from: date
    date_to: date
    due_time: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")

    @field_validator("title")
    @classmethod
    def title_valid(cls, value):
        value = value.strip()
        if not 1 <= len(value) <= 15:
            raise ValueError("请输入1至15个字符的待办标题")
        return value

    @model_validator(mode="after")
    def range_valid(self):
        days = (self.date_to - self.date_from).days
        if days < 0 or days >= 50:
            raise ValueError("日期范围须为连续1至50天")
        return self


class TodoPatch(TodoCreate):
    title: str = (
        None  # omitted differs from explicit null; validator below rejects null
    )
    status: Literal["ongoing", "completed"] = None

    @model_validator(mode="before")
    @classmethod
    def patch_valid(cls, values):
        if not isinstance(values, dict):
            return values
        if not values:
            raise ValueError("请提供要修改的字段")
        if any(k in values and values[k] is None for k in ("title", "status")):
            raise ValueError("标题和状态不能为空")
        return values

    @model_validator(mode="after")
    def date_time_valid(self):
        if (
            "due_date" in self.model_fields_set
            and self.due_date is None
            and self.due_time
        ):
            raise ValueError("设置截止时间前请选择日期")
        return self


class TodoOut(BaseModel):
    id: UUID
    title: str
    description: str | None
    due_date: date | None
    due_time: str | None
    timezone: str
    due_at: datetime | None
    status: Literal["ongoing", "completed"]
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    is_overdue: bool
    source: Literal["app"] = "app"
    assignee_id: UUID


class TodoQuery(Input):
    status: Literal["ongoing", "completed"] = "ongoing"
    due: Literal["all", "overdue", "today", "tomorrow", "next7", "future", "none"] = (
        "all"
    )
    date_from: date | None = None
    date_to: date | None = None
    due_time: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=2048)

    @model_validator(mode="after")
    def filter_valid(self):
        if self.status == "completed" and self.due == "overdue":
            raise ValueError("已完成分组不支持逾期筛选")
        if (self.date_from is None) != (self.date_to is None):
            raise ValueError("日期范围必须完整")
        if self.date_from and (self.date_from > self.date_to or self.due != "all"):
            raise ValueError("日期范围无效")
        return self


class TodoList(BaseModel):
    items: list[TodoOut]
    next_cursor: str | None
    server_time: datetime


class AssistantMessage(Input):
    thread_id: UUID
    message: str = Field(min_length=1, max_length=1000)

    @field_validator("message")
    @classmethod
    def message_valid(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("请输入想交给助手的内容")
        return value


class AssistantThreadStart(Input):
    fresh: bool = False


class AssistantItem(BaseModel):
    id: UUID
    title: str
    due_date: date | None = None
    due_time: str | None = None
    status: str
    kind: str = "todo"
    url: str | None = None


class AssistantReply(BaseModel):
    kind: Literal["result", "clarify", "confirm", "success", "message"]
    message: str
    items: list[AssistantItem] = []
    action_token: str | None = None
    action_label: str | None = None
    suggestions: list[Suggestion] = Field(default_factory=list)


class AssistantUserEntry(BaseModel):
    role: Literal["user"]
    message: str


class AssistantReplyEntry(BaseModel):
    id: UUID | None = None
    role: Literal["assistant"]
    reply: AssistantReply


class AssistantThread(BaseModel):
    thread_id: UUID
    expires_at: datetime
    entries: list[AssistantUserEntry | AssistantReplyEntry] = []


class ErrorDetail(BaseModel):
    code: str
    message: str
    fields: dict[str, str] | None = None


class ErrorOut(BaseModel):
    error: ErrorDetail


ERROR_RESPONSES = {
    code: {"model": ErrorOut, "description": message}
    for code, message in {
        401: "登录失效或凭据错误",
        403: "请求来源校验失败",
        404: "该待办不存在或无法访问",
        409: "账号或请求标识冲突",
        410: "临时对话已过期",
        415: "请使用JSON请求",
        422: "字段或游标无效",
        429: "操作过于频繁",
        503: "服务暂不可用",
        500: "服务发生异常",
    }.items()
}
