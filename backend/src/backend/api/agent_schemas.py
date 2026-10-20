from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.api.suggestion_schemas import Suggestion


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RunCreate(Input):
    thread_id: UUID
    prompt: str = Field(min_length=1, max_length=1000)
    source_run_id: UUID | None = None
    suggestion_id: UUID | None = None


class ActionEdit(Input):
    id: UUID
    arguments: dict


class RunResume(Input):
    plan_version: int = Field(ge=1)
    selected_action_ids: list[UUID] = Field(max_length=10)
    edits: list[ActionEdit] = Field(default_factory=list, max_length=10)


class Source(BaseModel):
    title: str
    url: str | None
    excerpt: str | None = None
    chunk_id: str | None = None
    document_version: str | None = None
    locator: dict | None = None


class Action(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    description: str | None
    status: str
    result: dict | None
    error: str | None


class Run(BaseModel):
    id: UUID
    thread_id: UUID
    prompt: str = ""
    parent_plan_id: UUID | None = None
    status: str
    progress: str | None
    final_answer: str | None
    sources: list[Source]
    actions: list[Action]
    plan_version: int | None
    error: str | None
    suggestions: list[Suggestion] = Field(default_factory=list)
