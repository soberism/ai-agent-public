import base64
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.api.hub_schemas import (
    VoiceMemoAudioCreate,
    VoiceMemoConvert,
    VoiceMemoCreate,
    VoiceMemoOut,
)
from backend.api.schemas import ERROR_RESPONSES
from backend.core.security import DB, APIError, Principal
from backend.db.cross_system_models import VoiceMemo
from backend.db.models import CalendarEvent, Todo, utcnow
from backend.features.assistant.request_limits import enforce
from backend.features.sharing.access import inherit_sharing, visible_condition
from backend.features.sharing.cleanup import delete_resource

router = APIRouter(
    prefix="/api/assistant/voice-memos",
    tags=["语音备忘"],
    responses=ERROR_RESPONSES,
    dependencies=[Depends(enforce)],
)


def output(row):
    result = VoiceMemoOut.model_validate(row, from_attributes=True)
    if row.mime_type:
        result.audio_url = f"/api/assistant/voice-memos/{row.id}/audio"
    return result


@router.get("", response_model=list[VoiceMemoOut])
def listing(user: Principal, session: DB):
    return [
        output(row)
        for row in session.scalars(
            select(VoiceMemo)
            .where(visible_condition(VoiceMemo, user.id))
            .order_by(VoiceMemo.created_at.desc())
        )
    ]


@router.post("", response_model=VoiceMemoOut, status_code=201)
def create(body: VoiceMemoCreate, user: Principal, session: DB):
    row = VoiceMemo(owner_id=user.id, transcript=body.transcript.strip())
    session.add(row)
    session.commit()
    return output(row)


def owned(memo_id, user, session):
    row = session.scalar(
        select(VoiceMemo).where(
            VoiceMemo.id == memo_id, visible_condition(VoiceMemo, user.id)
        )
    )
    if row is None:
        raise APIError(404, "VOICE_MEMO_NOT_FOUND", "语音备忘不存在或无法访问")
    return row


def decode_audio(body):
    try:
        audio = base64.b64decode(body.audio_base64, validate=True)
    except ValueError:
        raise APIError(422, "INVALID_AUDIO", "录音格式无效，请重新录制") from None
    if not audio or len(audio) > 8 * 1024 * 1024:
        raise APIError(422, "INVALID_AUDIO", "录音不能为空且不得超过 8MB")
    valid = {
        "audio/webm": audio.startswith(b"\x1a\x45\xdf\xa3"),
        "audio/ogg": audio.startswith(b"OggS"),
        "audio/mp4": len(audio) >= 12 and audio[4:8] == b"ftyp",
    }
    if not valid.get(body.mime_type):
        raise APIError(422, "INVALID_AUDIO", "录音内容与格式不匹配")
    return audio


@router.post("/audio", response_model=VoiceMemoOut, status_code=201)
def create_audio(body: VoiceMemoAudioCreate, user: Principal, session: DB):
    audio = decode_audio(body)
    existing = session.get(VoiceMemo, body.upload_id)
    if existing:
        return replay_audio(existing, body, user, audio)
    row = VoiceMemo(
        id=body.upload_id,
        owner_id=user.id,
        transcript="",
        audio=audio,
        mime_type=body.mime_type,
    )
    session.add(row)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.get(VoiceMemo, body.upload_id)
        if existing is None:
            raise
        return replay_audio(existing, body, user, audio)
    return output(row)


def replay_audio(row, body, user, audio):
    if row.owner_id != user.id or row.mime_type != body.mime_type or row.audio != audio:
        raise APIError(409, "UPLOAD_CONFLICT", "录音保存标识冲突，请重新录制")
    return output(row)


@router.get("/{memo_id}/audio")
def playback(
    memo_id: UUID,
    user: Principal,
    session: DB,
    range_header: str | None = Header(default=None, alias="Range"),
):
    row = owned(memo_id, user, session)
    if row.audio is None:
        raise APIError(404, "AUDIO_NOT_FOUND", "这条备忘没有录音")
    audio = row.audio
    headers = {
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
        "Accept-Ranges": "bytes",
    }
    if range_header is None:
        return Response(audio, media_type=row.mime_type, headers=headers)
    try:
        if not range_header.startswith("bytes=") or "," in range_header:
            raise ValueError
        start_text, end_text = range_header[6:].split("-")
        start = int(start_text) if start_text else max(0, len(audio) - int(end_text))
        end = (
            min(int(end_text), len(audio) - 1)
            if start_text and end_text
            else len(audio) - 1
        )
        if (
            start < 0
            or start >= len(audio)
            or end < start
            or (not start_text and int(end_text) <= 0)
        ):
            raise ValueError
    except ValueError:
        return Response(
            status_code=416,
            headers={**headers, "Content-Range": f"bytes */{len(audio)}"},
        )
    headers["Content-Range"] = f"bytes {start}-{end}/{len(audio)}"
    return Response(
        audio[start : end + 1],
        status_code=206,
        media_type=row.mime_type,
        headers=headers,
    )


@router.post("/{memo_id}/transcribe", response_model=VoiceMemoOut)
def transcribe_memo(memo_id: UUID, user: Principal, session: DB):
    from backend.api.assistant_preferences_schemas import TranscriptionInput
    from backend.api.routes.assistant_preferences import transcribe

    row = owned(memo_id, user, session)
    if row.transcript:
        return output(row)
    if row.audio is None:
        raise APIError(422, "AUDIO_NOT_FOUND", "这条备忘没有录音")
    result = transcribe(
        TranscriptionInput(
            audio_base64=base64.b64encode(row.audio).decode(),
            mime_type=row.mime_type,
        ),
        user,
    )
    row.transcript = result.transcript[:4000]
    row.updated_at = utcnow()
    session.commit()
    return output(row)


@router.delete("/{memo_id}", status_code=204)
def remove(memo_id: UUID, user: Principal, session: DB):
    row = owned(memo_id, user, session)
    delete_resource(session, row)
    session.commit()
    return Response(status_code=204)


@router.post("/{memo_id}/convert", response_model=VoiceMemoOut)
def convert(memo_id: UUID, body: VoiceMemoConvert, user: Principal, session: DB):
    row = session.scalar(
        select(VoiceMemo)
        .where(VoiceMemo.id == memo_id, visible_condition(VoiceMemo, user.id))
        .with_for_update()
    )
    if row is None:
        raise APIError(404, "VOICE_MEMO_NOT_FOUND", "语音备忘不存在或无法访问")
    if row.target_id:
        return output(row)
    if not row.transcript.strip():
        raise APIError(422, "TRANSCRIPT_REQUIRED", "请先转文字再生成待办或日程")
    if body.target_type == "todo":
        target = Todo(
            owner_id=row.owner_id,
            title=body.title,
            description=row.transcript,
            due_date=None,
            due_time=None,
            due_at=None,
            timezone=user.timezone,
            status="ongoing",
            completed_at=None,
            create_key=uuid4(),
            create_fingerprint=uuid4().hex,
        )
    else:
        start = datetime.now(ZoneInfo(user.timezone)).replace(
            second=0, microsecond=0
        ) + timedelta(hours=1)
        target = CalendarEvent(
            owner_id=row.owner_id,
            title=body.title,
            description=row.transcript,
            location=None,
            source="voice",
            status="scheduled",
            timezone=user.timezone,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
        )
    session.add(target)
    session.flush()
    inherit_sharing(session, "voice_memo", row.id, body.target_type, target.id)
    row.status = "converted"
    row.target_type = body.target_type
    row.target_id = target.id
    row.updated_at = utcnow()
    session.commit()
    return output(row)
