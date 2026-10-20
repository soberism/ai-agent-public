from datetime import date as Date
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from backend.api.schemas import Input


class PreferenceCreate(Input):
    label: str = Field(min_length=1, max_length=100)
    kind: Literal["preference", "allergy", "budget"]

    @field_validator("label")
    @classmethod
    def nonblank_label(cls, value):
        if not value.strip():
            raise ValueError("请输入偏好或限制")
        return value.strip()


class PreferenceOut(BaseModel):
    id: UUID
    label: str
    kind: str


class MealCreate(Input):
    title: str = Field(default="", max_length=15)
    checklist_id: UUID | None = None
    shopping_list_id: UUID | None = None
    schedule_text: str | None = Field(default=None, max_length=15)
    date: Date | None = None
    meal_type: Literal["breakfast", "lunch", "dinner", "snack"] | None = None
    diners: int | None = Field(default=None, ge=1, le=100)
    dish: str = Field(min_length=1, max_length=100)
    notes: str | None = Field(default=None, max_length=1000)
    preferences: list[PreferenceCreate] = Field(default_factory=list, max_length=20)


class MealOut(BaseModel):
    title: str
    id: UUID
    schedule_text: str | None = None
    date: Date | None
    meal_type: str | None
    diners: int | None
    dish: str
    notes: str | None
    status: str = "draft"
    calendar_url: str | None = None
    shopping_url: str | None = None
    preferences: list[PreferenceOut] = Field(default_factory=list)


class PantryCreate(Input):
    name: str = Field(min_length=1, max_length=100)
    quantity: float = Field(gt=0, le=100000)
    unit: str = Field(default="", max_length=20)


class PantryOut(BaseModel):
    id: UUID
    name: str
    quantity: float
    unit: str


class MealList(BaseModel):
    items: list[MealOut]
    preferences: list[PreferenceOut]
    pantry: list[PantryOut]


class ShoppingItemCreate(Input):
    name: str = Field(min_length=1, max_length=100)
    quantity: float = Field(gt=0, le=100000)
    unit: str = Field(default="", max_length=20)
    category: str = Field(default="", max_length=50)


class ShoppingItemPatch(Input):
    purchased: bool


class ShoppingItemOut(BaseModel):
    id: UUID
    name: str
    quantity: float
    unit: str
    category: str
    origin: str
    purchased: bool


class ShoppingListOut(BaseModel):
    id: UUID
    meal_id: UUID | None = None
    title: str
    items: list[ShoppingItemOut]
    status: str = "draft"
    checklist_url: str | None = None


class ShoppingListsOut(BaseModel):
    items: list[ShoppingListOut]


class ShoppingListCreate(Input):
    title: str = Field(min_length=1, max_length=15)

    @field_validator("title")
    @classmethod
    def nonblank_title(cls, value):
        if not value.strip():
            raise ValueError("请输入清单名称")
        return value.strip()


class AppointmentCreate(Input):
    patient_name: str = Field(min_length=1, max_length=100)
    institution: str = Field(min_length=1, max_length=150)
    service_type: str = Field(min_length=1, max_length=100)
    preferred_at: datetime
    fee_note: str | None = Field(default=None, max_length=1000)

    @field_validator("preferred_at")
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None:
            raise ValueError("时间必须包含时区")
        return value


class AppointmentOut(BaseModel):
    id: UUID
    patient_name: str
    institution: str
    service_type: str
    preferred_at: datetime
    status: str
    fee_note: str | None
    external_receipt: None = None
    calendar_url: str | None
    todo_url: str | None


class AppointmentList(BaseModel):
    items: list[AppointmentOut]


class LifeCapabilities(BaseModel):
    delivery: bool = False
    payment: bool = False
    medical_booking: bool = False
