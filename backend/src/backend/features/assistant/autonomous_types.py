"""Serializable contracts for the autonomous read-only graph."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, NotRequired, TypedDict

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.features.assistant.answer_claims import AnswerClaim


class ProposedAction(TypedDict):
    tool_name: str
    arguments: dict
    description: NotRequired[str]


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal[
        "search_tools",
        "describe_tools",
        "read_api",
        "retrieve_knowledge",
        "web_search",
        "propose_actions",
        "final_answer",
        "revise_answer",
    ]
    answer_kind: Literal[
        "conversation", "clarification", "business", "document", "execution"
    ] = "conversation"
    claims: list[AnswerClaim] = Field(default_factory=list, max_length=60)
    requested_domains: list[str] = Field(default_factory=list, max_length=20)
    requires_current_data: bool = False
    resolved_request: str = Field(default="", max_length=1000)
    query: str = Field(default="", max_length=300)
    names: list[str] = Field(default_factory=list, max_length=10)
    tool_name: str = Field(default="", max_length=100)
    arguments: dict = Field(default_factory=dict)
    actions: list[ProposedAction] = Field(default_factory=list, max_length=10)
    answer: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def required_value(self):
        required = {
            "search_tools": bool(self.query.strip()),
            "describe_tools": bool(self.names),
            "read_api": bool(self.tool_name),
            "retrieve_knowledge": bool(self.query.strip()),
            "web_search": bool(self.query.strip()),
            "propose_actions": bool(self.actions),
            "final_answer": bool(self.answer.strip()) or bool(self.claims),
            "revise_answer": bool(self.answer.strip()),
        }
        if not required[self.action]:
            raise ValueError("决策缺少必要参数")
        return self


class AutonomousState(TypedDict):
    history_prepared: NotRequired[bool]
    requires_current_data: bool
    prompt: str
    resolved_request: str
    conversation_summary: str
    history: list[dict[str, str]]
    discovered_tools: list[dict]
    described_tools: list[dict]
    observations: list[dict]
    knowledge: list[dict]
    web_results: list[dict]
    proposed_actions: list[dict]
    approval: dict
    seen_reads: list[str]
    search_retries: int
    stalled_on: str
    iteration: int
    read_count: int
    knowledge_count: int
    claim_retries: int
    decision: dict
    final_answer: str
    timezone: str
    custom_instructions: str
    memories: list[str]
    last_results: list[dict]
    task_context: dict


DecisionMaker = Callable[[AutonomousState], Decision]
Reader = Callable[[str, dict], object]
Retriever = Callable[[str], list[dict]]


@dataclass(frozen=True)
class AutonomousContext:
    decide: DecisionMaker
    reader: Reader
    retriever: Retriever = lambda _: []
    max_iterations: int = 18
    max_reads: int = 20
    max_knowledge: int = 3


def initial_state(prompt: str, history=None, **context_data):
    return {
        "requires_current_data": False,
        "prompt": prompt,
        "resolved_request": "",
        "conversation_summary": "",
        "history": history or [],
        "discovered_tools": [],
        "described_tools": [],
        "observations": [],
        "knowledge": [],
        "web_results": [],
        "proposed_actions": [],
        "approval": {},
        "seen_reads": [],
        "search_retries": 0,
        "stalled_on": "",
        "iteration": 0,
        "read_count": 0,
        "knowledge_count": 0,
        "claim_retries": 0,
        "decision": {},
        "final_answer": "",
        "timezone": "Asia/Shanghai",
        "custom_instructions": "",
        "memories": [],
        "last_results": [],
        "task_context": {},
        **context_data,
    }
