"""Answer-linked follow-up options."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class Suggestion(BaseModel):
    id: UUID
    source_run_id: UUID
    label: str
    type: Literal["follow_up", "navigate"]
    intent: str
    target_kind: Literal["todo", "event", "reminder", "checklist"]
    target_id: UUID
    target_title: str
    draft: str | None = None
    url: str | None = None
