from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from backend.api.schemas import Input


class SearchItem(BaseModel):
    id: UUID
    kind: str
    title: str
    detail: str = ""
    url: str


class SearchMailDetail(BaseModel):
    subject: str
    body: str
    sender: str | None = None
    created_at: datetime


class SearchResult(BaseModel):
    items: list[SearchItem]


class HubSummary(BaseModel):
    pending_reviews: int
    pending_assignments: int
    failed_emails: int
    connection_issues: int
    pending_voice_memos: int


class AssignmentInput(Input):
    household_id: UUID
    assignee_id: UUID


class AssignmentFeedback(Input):
    status: Literal["completed", "rejected"]
    note: str = Field(default="", max_length=500)


class AssignmentOut(BaseModel):
    todo_id: UUID
    household_id: UUID
    assignee_id: UUID
    status: str
    note: str = ""


class AssignmentItem(AssignmentOut):
    title: str
    owner_id: UUID


class ObjectLinkInput(Input):
    household_id: UUID
    subject_type: Literal["profile", "pet"]
    subject_id: UUID


class HouseholdInput(Input):
    household_id: UUID


class MailCapabilities(BaseModel):
    imap: bool
    smtp: bool
    third_party_calendar: Literal[False] = False
    notification_channels: list[Literal["email"]] = ["email"]


class MailScanResult(BaseModel):
    imported: int
    duplicates: int


class EmailNotificationCreate(Input):
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=2000)


class EmailDeliveryOut(BaseModel):
    id: UUID
    subject: str
    body: str
    status: str
    error_message: str | None
    sent_at: datetime | None
    created_at: datetime


class VoiceMemoCreate(Input):
    transcript: str = Field(min_length=1, max_length=4000)


class VoiceMemoConvert(Input):
    target_type: Literal["todo", "event"]
    title: str = Field(min_length=1, max_length=15)


class VoiceMemoAudioCreate(Input):
    upload_id: UUID
    audio_base64: str = Field(min_length=1, max_length=12_000_000)
    mime_type: Literal["audio/webm", "audio/mp4", "audio/ogg"]


class VoiceMemoOut(BaseModel):
    id: UUID
    transcript: str
    audio_url: str | None = None
    status: str
    target_type: str | None
    target_id: UUID | None
    created_at: datetime


class DocumentSearchItem(BaseModel):
    id: UUID
    name: str
    excerpt: str
    subject_type: str | None
    subject_id: UUID | None
    status: str
