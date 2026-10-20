"""Structured claims are the only source of published business facts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class AnswerClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["count", "field", "quote", "execution"]
    evidence_ids: list[str] = Field(min_length=1, max_length=20)
    domain: str = Field(default="", max_length=40)
    scope: dict = Field(default_factory=dict)
    path: str = Field(default="", max_length=200)
    subject_id: str = Field(default="", max_length=255)
    value: JsonValue
