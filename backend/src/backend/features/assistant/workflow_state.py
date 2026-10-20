"""State shared by the assistant's parser and bounded read loop."""

from collections.abc import Callable
from typing import NotRequired, TypedDict


class State(TypedDict):
    message: str
    history: list[dict[str, str]]
    last_results: list[dict]
    custom_instructions: str
    memories: list[str]
    intent: object
    timezone: str
    reader: NotRequired[Callable[[str, dict], str] | None]
    observation: NotRequired[str]
    reads: NotRequired[int]
    stop: NotRequired[bool]
    seen_reads: NotRequired[list[str]]
