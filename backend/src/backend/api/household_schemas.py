from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from backend.api.schemas import EmailInput, Input


class NameInput(Input):
    name: str = Field(max_length=100)

    @field_validator("name")
    @classmethod
    def valid_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("名称不能为空")
        return value


class HouseholdCreate(NameInput):
    pass


class HouseholdOut(BaseModel):
    id: UUID
    name: str
    role: str
    member_count: int


class MemberOut(BaseModel):
    id: UUID
    account_id: UUID | None
    display_name: str
    email: str
    role: str
    status: str
    permissions: list[str] = []


class InvitationCreate(EmailInput):
    role: Literal["member"] = "member"


class InvitationOut(BaseModel):
    id: UUID
    email: str
    role: str
    status: str
    expires_at: datetime | None


class MemberPatch(Input):
    role: Literal["admin", "member"] | None = None
    permissions: (
        list[Literal["calendar_read", "todo_update", "document_read"]] | None
    ) = None
    status: Literal["active", "removed"] | None = None


class ProfileCreate(NameInput):
    relationship: str = Field(min_length=1, max_length=50)
    birth_date: date | None = None


class ProfileOut(BaseModel):
    id: UUID
    name: str
    relationship: str
    birth_date: date | None


class PetCreate(NameInput):
    species: str = Field(min_length=1, max_length=50)
    breed: str | None = Field(default=None, max_length=100)


class PetOut(BaseModel):
    id: UUID
    name: str
    species: str
    breed: str | None


class HouseholdDetail(HouseholdOut):
    members: list[MemberOut]
    invitations: list[InvitationOut]
    profiles: list[ProfileOut]
    pets: list[PetOut]


class HouseholdList(BaseModel):
    items: list[HouseholdOut]


class ContactCreate(NameInput):
    relationship: str = Field(default="其他", max_length=50)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=254)


class ContactOut(BaseModel):
    id: UUID
    name: str
    relationship: str
    phone: str | None
    email: str | None
    group_ids: list[UUID]


class ContactList(BaseModel):
    items: list[ContactOut]


class GroupCreate(NameInput):
    contact_ids: list[UUID] = Field(default_factory=list)


class GroupOut(BaseModel):
    id: UUID
    name: str
    contact_ids: list[UUID]


class GroupList(BaseModel):
    items: list[GroupOut]


class NotificationOut(BaseModel):
    id: UUID
    type: str
    title: str
    message: str
    read: bool
    created_at: datetime
    invitation_id: UUID | None


class NotificationList(BaseModel):
    items: list[NotificationOut]
