import json
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.core.security import APIError, settings

THREAD_SECONDS = 1800


class ThreadMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class ThreadItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    title: str = Field(min_length=1, max_length=100)
    due_date: str | None = None
    due_time: str | None = None
    status: str
    kind: str = "todo"
    url: str | None = None


class ThreadState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner_id: UUID
    messages: list[ThreadMessage]
    last_results: list[ThreadItem] = Field(default_factory=list)


def key(thread_id: UUID) -> str:
    return f"{settings.redis_namespace}assistant:thread:{thread_id}"


def create(
    store,
    owner_id: UUID,
    thread_id: UUID | None = None,
    messages: list[dict] | None = None,
    last_results: list[dict] | None = None,
) -> UUID:
    thread_id = thread_id or uuid4()
    state = ThreadState(
        owner_id=owner_id,
        messages=messages or [],
        last_results=last_results or [],
    )
    store.set(key(thread_id), state.model_dump_json(), ex=THREAD_SECONDS)
    return thread_id


def load(store, thread_id: UUID, owner_id: UUID) -> ThreadState:
    try:
        state = ThreadState.model_validate_json(store.get(key(thread_id)))
    except ValidationError, TypeError:
        state = None
    if state is None or state.owner_id != owner_id:
        raise APIError(410, "THREAD_EXPIRED", "对话已过期，请重新开始")
    return state


def remember(
    store,
    thread_id: UUID,
    state: ThreadState,
    user_message: str,
    assistant_message: str,
    last_results: list[ThreadItem] | None = None,
):
    messages = [
        *state.messages,
        ThreadMessage(role="user", content=user_message),
        ThreadMessage(role="assistant", content=assistant_message),
    ]
    store.set(
        key(thread_id),
        json.dumps(
            {
                "owner_id": str(state.owner_id),
                "messages": [m.model_dump() for m in messages],
                "last_results": [
                    item.model_dump(mode="json")
                    for item in (
                        state.last_results if last_results is None else last_results
                    )
                ],
            }
        ),
        ex=THREAD_SECONDS,
    )
