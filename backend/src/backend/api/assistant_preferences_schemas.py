from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AssistantPreferencesPatch(Input):
    custom_instructions: str | None = Field(default=None, max_length=2000)
    memory_enabled: bool | None = None

    @field_validator("custom_instructions")
    @classmethod
    def clean_instructions(cls, value: str | None):
        if value is None:
            raise ValueError("自定义指令不能为空")
        return value.strip()


class AssistantPreferencesOut(BaseModel):
    custom_instructions: str
    memory_enabled: bool
    updated_at: datetime | None


class MemoryCreate(Input):
    content: str = Field(min_length=1, max_length=500)

    @field_validator("content")
    @classmethod
    def clean_content(cls, value: str):
        value = value.strip()
        if not value:
            raise ValueError("记忆内容不能为空")
        return value


class MemoryPatch(Input):
    content: str | None = Field(default=None, min_length=1, max_length=500)
    enabled: bool | None = None

    @field_validator("content")
    @classmethod
    def clean_content(cls, value: str | None):
        if value is None:
            raise ValueError("记忆内容不能为空")
        value = value.strip()
        if not value:
            raise ValueError("记忆内容不能为空")
        return value


class MemoryOut(BaseModel):
    id: UUID
    content: str
    source: Literal["user", "assistant"]
    enabled: bool
    created_at: datetime
    updated_at: datetime


class TranscriptionInput(Input):
    audio_base64: str = Field(min_length=1, max_length=12_000_000)
    mime_type: Literal["audio/webm", "audio/mp4", "audio/ogg"]


class TranscriptionOut(BaseModel):
    transcript: str
