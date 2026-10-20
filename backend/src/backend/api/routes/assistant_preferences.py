import base64
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from openai import OpenAIError
from sqlalchemy import select

from backend.api.assistant_preferences_schemas import (
    AssistantPreferencesOut,
    AssistantPreferencesPatch,
    MemoryCreate,
    MemoryOut,
    MemoryPatch,
    TranscriptionInput,
    TranscriptionOut,
)
from backend.api.schemas import ERROR_RESPONSES
from backend.core.security import DB, APIError, Principal, settings
from backend.db.models import AssistantMemory, AssistantProfile, utcnow
from backend.features.assistant.preferences import sensitive
from backend.features.assistant.request_limits import enforce
from backend.features.assistant.transcription import recognize

router = APIRouter(
    prefix="/api/assistant",
    tags=["AI助手偏好"],
    responses=ERROR_RESPONSES,
    dependencies=[Depends(enforce)],
)


def preferences_out(profile: AssistantProfile | None) -> AssistantPreferencesOut:
    return AssistantPreferencesOut(
        custom_instructions=profile.custom_instructions if profile else "",
        memory_enabled=profile.memory_enabled if profile else True,
        updated_at=profile.updated_at if profile else None,
    )


def memory_out(memory: AssistantMemory) -> MemoryOut:
    return MemoryOut.model_validate(memory, from_attributes=True)


def owned_memory(session, owner_id, memory_id) -> AssistantMemory:
    memory = session.scalar(
        select(AssistantMemory).where(
            AssistantMemory.id == memory_id, AssistantMemory.owner_id == owner_id
        )
    )
    if memory is None:
        raise APIError(404, "MEMORY_NOT_FOUND", "这条记忆不存在或无法访问")
    return memory


@router.get("/preferences", response_model=AssistantPreferencesOut)
def get_preferences(user: Principal, session: DB):
    return preferences_out(session.get(AssistantProfile, user.id))


@router.patch("/preferences", response_model=AssistantPreferencesOut)
def update_preferences(body: AssistantPreferencesPatch, user: Principal, session: DB):
    if not body.model_fields_set:
        raise APIError(422, "VALIDATION_ERROR", "请提供要修改的 AI 偏好")
    profile = session.get(AssistantProfile, user.id)
    if profile is None:
        profile = AssistantProfile(owner_id=user.id)
        session.add(profile)
    for field in body.model_fields_set:
        setattr(profile, field, getattr(body, field))
    profile.updated_at = utcnow()
    session.commit()
    return preferences_out(profile)


@router.get("/memories", response_model=list[MemoryOut])
def list_memories(user: Principal, session: DB):
    return [
        memory_out(value)
        for value in session.scalars(
            select(AssistantMemory)
            .where(AssistantMemory.owner_id == user.id)
            .order_by(AssistantMemory.updated_at.desc(), AssistantMemory.id.desc())
        )
    ]


@router.post("/memories", response_model=MemoryOut, status_code=201)
def create_memory(body: MemoryCreate, user: Principal, session: DB):
    if sensitive(body.content):
        raise APIError(422, "SENSITIVE_MEMORY_REJECTED", "敏感信息不会保存为长期记忆")
    memory = AssistantMemory(owner_id=user.id, content=body.content)
    session.add(memory)
    session.commit()
    return memory_out(memory)


@router.patch("/memories/{memory_id}", response_model=MemoryOut)
def update_memory(memory_id: UUID, body: MemoryPatch, user: Principal, session: DB):
    if not body.model_fields_set:
        raise APIError(422, "VALIDATION_ERROR", "请提供要修改的记忆内容")
    if body.content is not None and sensitive(body.content):
        raise APIError(422, "SENSITIVE_MEMORY_REJECTED", "敏感信息不会保存为长期记忆")
    memory = owned_memory(session, user.id, memory_id)
    for field in body.model_fields_set:
        setattr(memory, field, getattr(body, field))
    memory.updated_at = utcnow()
    session.commit()
    return memory_out(memory)


@router.delete("/memories/{memory_id}", status_code=204)
def delete_memory(memory_id: UUID, user: Principal, session: DB):
    session.delete(owned_memory(session, user.id, memory_id))
    session.commit()
    return Response(status_code=204)


@router.post("/transcriptions", response_model=TranscriptionOut)
def transcribe(body: TranscriptionInput, user: Principal):
    if not all(
        (
            settings.transcription_base_url,
            settings.transcription_api_key.get_secret_value(),
            settings.transcription_model,
        )
    ):
        raise APIError(
            503,
            "VOICE_TRANSCRIPTION_UNAVAILABLE",
            "语音转写服务尚未配置，请改用文字输入",
        )
    try:
        audio = base64.b64decode(body.audio_base64, validate=True)
        if not audio or len(audio) > 8 * 1024 * 1024:
            raise ValueError
        transcript = recognize(audio, settings)
        if not transcript:
            raise APIError(
                503, "VOICE_TRANSCRIPTION_FAILED", "没有识别到可用语音，请重试"
            )
        return TranscriptionOut(transcript=transcript)
    except ValueError, KeyError, base64.binascii.Error:
        raise APIError(422, "INVALID_AUDIO", "录音格式无效，请重新录制") from None
    except OpenAIError:
        raise APIError(
            503, "VOICE_TRANSCRIPTION_FAILED", "语音转写失败，请稍后重试"
        ) from None
