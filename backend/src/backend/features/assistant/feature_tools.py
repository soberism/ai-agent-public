"""Generate bounded tool contracts from the allowlisted existing route inputs."""

from datetime import date
from functools import lru_cache
from importlib import import_module
from inspect import Parameter, signature
from typing import Literal, get_type_hints
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, create_model

from backend.api.routes.sharing import SharingSettings
from backend.features.assistant.capabilities import CAPABILITIES, ENTRIES
from backend.features.assistant.feature_edits import EDIT_MODELS, partial_input
from backend.features.assistant.read_filters import FILTER_TOOLS, ReadFilters


class Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=15)
    selected: bool = True
    type: Literal["todo"] = "todo"


class CommitInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidates: list[Candidate] = Field(min_length=1, max_length=50)


class AssistantSharingSettings(SharingSettings):
    household_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="家庭范围或成员范围必填；使用实时查询得到的ID或完整家庭名称",
    )
    member_ids: list[str] = Field(
        default_factory=list,
        max_length=200,
        description="成员范围必填；使用家庭详情中的成员account_id",
    )


@lru_cache
def contract(name):
    route, *_ = CAPABILITIES[name]
    module, function = route.split(".")
    if module == "household_invitations":
        import_module("backend.api.routes.households")
    handler = getattr(import_module(f"backend.api.routes.{module}"), function)
    hints = get_type_hints(handler)
    fields = {}
    for key, param in signature(handler).parameters.items():
        if key in {"user", "session"} or (
            name in {"create_todo", "create_daily_todos"}
            and key in {"response", "idempotency_key"}
        ):
            continue
        annotation = hints[key]
        default = ... if param.default is Parameter.empty else param.default
        if annotation is UUID:
            annotation = str
            default = Field(
                default=default,
                min_length=1,
                max_length=255,
                description="实时查询得到的ID或对象的完整标题；不得编造ID",
            )
        if name in EDIT_MODELS and key == "body":
            annotation = partial_input(name)
        if name == "review_plan" and key == "query":
            annotation = create_model(
                "AssistantReviewRange",
                __config__=ConfigDict(extra="forbid"),
                date_from=(date, ...),
                date_to=(date, ...),
            )
        if name == "commit_dump" and key == "body":
            annotation = CommitInput
        if name == "set_sharing" and key == "body":
            annotation = AssistantSharingSettings
        if name == "decide_invitation" and key == "decision":
            annotation = Literal["accept", "reject"]
        if key == "kind":
            annotation = Literal[
                "todo",
                "event",
                "checklist",
                "meal",
                "material",
                "voice_memo",
                "daily_dump",
                "pantry",
                "preference",
                "reminder",
                "shopping",
            ]
        fields[key] = (annotation, default)
    if name in FILTER_TOOLS:
        fields["filters"] = (ReadFilters | None, None)
    model = create_model(
        f"Feature_{name}", __config__=ConfigDict(extra="forbid"), **fields
    )
    return handler, model


def parse_arguments(name, payload):
    _, model = contract(name)
    if set(model.model_fields) == {"body"} and "body" not in payload:
        payload = {"body": payload}
    return model.model_validate(payload)


def feature_tools():
    tools = []
    for name, (_, label, readonly, _, _) in CAPABILITIES.items():
        if name == "create_checklist":
            continue
        _, model = contract(name)
        schema = model.model_json_schema()

        # Nested route models occasionally use BaseModel's permissive default.
        def forbid(value):
            if isinstance(value, dict):
                if value.get("type") == "object":
                    value["additionalProperties"] = False
                for child in value.values():
                    forbid(child)
            elif isinstance(value, list):
                for child in value:
                    forbid(child)

        forbid(schema)
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": f"feature_{name}",
                    "description": label
                    + (
                        "，实时读取当前可访问数据"
                        if readonly
                        else "，先展示参数并经用户确认才执行"
                    ),
                    "parameters": schema,
                },
            }
        )
    tools.append(
        {
            "type": "function",
            "function": {
                "name": "open_feature",
                "description": "提供已开放功能入口；上传文件、录音、播放、下载、账号管理等需用户在页面操作，不能声称已执行",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "feature": {"type": "string", "enum": list(ENTRIES)}
                    },
                    "required": ["feature"],
                    "additionalProperties": False,
                },
            },
        }
    )
    return tools
