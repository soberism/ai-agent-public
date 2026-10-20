from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from backend.api.schemas import Input


class FolderCreate(Input):
    name: str = Field(max_length=100)

    @field_validator("name")
    @classmethod
    def valid_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("文件夹名称不能为空")
        return value


class FolderOut(BaseModel):
    id: UUID
    name: str
    count: int
    editable: bool = True


class MaterialOut(BaseModel):
    id: UUID
    name: str
    kind: Literal["file", "photo", "email", "voice"]
    status: Literal["uploaded", "processing", "ready", "partial", "failed"]
    created_at: datetime
    folder_id: UUID | None
    error_message: str | None
    review_count: int


class MaterialList(BaseModel):
    items: list[MaterialOut]
    folders: list[FolderOut]


class MaterialPatch(Input):
    folder_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)

    @field_validator("name")
    @classmethod
    def valid_name(cls, value):
        if value is not None:
            value = value.strip()
            if not value or any(char in value for char in "/\\\r\n"):
                raise ValueError("文件名不能为空或包含路径字符")
        return value


class ReviewPatch(Input):
    title: str = Field(min_length=1, max_length=15)


class ReviewOut(BaseModel):
    id: UUID
    material_id: UUID
    material_name: str
    target_type: Literal["todo", "event", "checklist", "reminder", "document"]
    title: str
    evidence: str
    confidence: float
    status: Literal["pending", "accepted", "ignored", "failed"]
    target_url: str | None
    change_kind: str
    previous_value: str | None


class ReviewList(BaseModel):
    items: list[ReviewOut]


class DocumentCapabilities(BaseModel):
    email: bool = False
    local_upload: bool = True
    text_extraction: bool = True
