import hashlib
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.api.routes.document_review import accept as accept_review
from backend.api.schemas import ERROR_RESPONSES
from backend.core.security import DB, APIError, Principal
from backend.db.document_models import DocumentReviewItem
from backend.db.models import CalendarEvent, Todo, utcnow
from backend.db.parity_models import DailyDump, VoiceSession
from backend.features.sharing.access import inherit_sharing, visible_condition

router = APIRouter(
    prefix="/api/workflows", tags=["完整工作流"], responses=ERROR_RESPONSES
)


class Transcript(BaseModel):
    transcript: str = Field(min_length=1, max_length=4000)


@router.post("/voice-sessions", status_code=201)
def start_voice(user: Principal, session: DB):
    row = VoiceSession(owner_id=user.id, turns=[])
    session.add(row)
    session.commit()
    return {"id": row.id, "status": row.status, "turns": row.turns}


def owned_voice(session, user, value):
    row = session.scalar(
        select(VoiceSession).where(
            VoiceSession.id == value, VoiceSession.owner_id == user.id
        )
    )
    if row is None:
        raise APIError(404, "VOICE_SESSION_NOT_FOUND", "语音会话不存在")
    return row


@router.post("/voice-sessions/{session_id}/turns")
def voice_turn(session_id: UUID, body: Transcript, user: Principal, session: DB):
    row = owned_voice(session, user, session_id)
    reply = "我记下了。你可以继续说，结束后我会汇总；需要改动事项时仍会让你确认。"
    row.turns = [
        *row.turns,
        {"role": "user", "content": body.transcript, "at": utcnow().isoformat()},
        {"role": "assistant", "content": reply, "at": utcnow().isoformat()},
    ]
    session.commit()
    return {"id": row.id, "status": row.status, "turns": row.turns}


@router.post("/voice-sessions/{session_id}/end")
def end_voice(session_id: UUID, user: Principal, session: DB):
    row = owned_voice(session, user, session_id)
    row.status, row.ended_at = "ended", utcnow()
    row.summary = (
        "；".join(turn["content"] for turn in row.turns[-5:]) or "本次通话没有有效内容"
    )
    session.commit()
    return {
        "id": row.id,
        "status": row.status,
        "summary": row.summary,
        "turns": row.turns,
    }


class DumpInput(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class DumpCommit(BaseModel):
    candidates: list[dict]


@router.post("/daily-dumps", status_code=201)
def create_dump(body: DumpInput, user: Principal, session: DB):
    candidates = [
        {"id": str(uuid4()), "type": "todo", "title": value.strip(), "selected": True}
        for value in body.text.replace("；", "\n").splitlines()
        if value.strip()
    ]
    row = DailyDump(owner_id=user.id, source_text=body.text, candidates=candidates)
    session.add(row)
    session.commit()
    return {"id": row.id, "status": row.status, "candidates": candidates}


@router.post("/daily-dumps/{dump_id}/commit")
def commit_dump(dump_id: UUID, body: DumpCommit, user: Principal, session: DB):
    row = session.scalar(
        select(DailyDump)
        .where(DailyDump.id == dump_id, visible_condition(DailyDump, user.id))
        .with_for_update()
    )
    if row is None:
        raise APIError(404, "DUMP_NOT_FOUND", "整理草稿不存在")
    if row.status == "committed":
        return {"id": row.id, "created": []}
    created = []
    for value in body.candidates:
        if not value.get("selected"):
            continue
        key = uuid4()
        title = str(value.get("title", "")).strip()
        if not 1 <= len(title) <= 15:
            raise APIError(422, "TITLE_INVALID", "标题必须为1至15个字符")
        todo = Todo(
            owner_id=row.owner_id,
            title=title,
            description="来自脑内整理",
            timezone=user.timezone,
            status="ongoing",
            create_key=key,
            create_fingerprint=hashlib.sha256(str(key).encode()).hexdigest(),
        )
        session.add(todo)
        session.flush()
        inherit_sharing(session, "daily_dump", row.id, "todo", todo.id)
        created.append({"id": str(todo.id), "title": title, "url": f"/todos/{todo.id}"})
    row.status = "committed"
    row.candidates = body.candidates
    session.commit()
    return {"id": row.id, "created": created}


@router.get("/conflicts/{event_id}/suggestions")
def conflict_suggestions(event_id: UUID, user: Principal, session: DB):
    event = session.scalar(
        select(CalendarEvent).where(
            CalendarEvent.id == event_id, visible_condition(CalendarEvent, user.id)
        )
    )
    if event is None:
        raise APIError(404, "EVENT_NOT_FOUND", "日程不存在")
    duration = event.ends_at - event.starts_at
    suggestions = []
    for hours in (-2, -1, 1, 2):
        start = event.starts_at + timedelta(hours=hours)
        end = start + duration
        clash = session.scalar(
            select(CalendarEvent.id)
            .where(
                visible_condition(CalendarEvent, user.id),
                CalendarEvent.id != event.id,
                CalendarEvent.starts_at < end,
                CalendarEvent.ends_at > start,
            )
            .limit(1)
        )
        if not clash:
            suggestions.append({"starts_at": start, "ends_at": end})
    return {"event_id": event.id, "suggestions": suggestions[:3]}


class MoveEvent(BaseModel):
    starts_at: datetime
    ends_at: datetime


@router.post("/conflicts/{event_id}/apply")
def apply_conflict(event_id: UUID, body: MoveEvent, user: Principal, session: DB):
    event = session.scalar(
        select(CalendarEvent)
        .where(CalendarEvent.id == event_id, visible_condition(CalendarEvent, user.id))
        .with_for_update()
    )
    if event is None:
        raise APIError(404, "EVENT_NOT_FOUND", "日程不存在")
    if session.scalar(
        select(CalendarEvent.id)
        .where(
            visible_condition(CalendarEvent, user.id),
            CalendarEvent.id != event.id,
            CalendarEvent.starts_at < body.ends_at,
            CalendarEvent.ends_at > body.starts_at,
        )
        .limit(1)
    ):
        raise APIError(409, "EVENT_CONFLICT", "所选时间仍有冲突")
    event.starts_at, event.ends_at, event.updated_at = (
        body.starts_at,
        body.ends_at,
        utcnow(),
    )
    session.commit()
    return {"id": event.id, "url": f"/calendar/{event.id}/edit"}


class BatchReview(BaseModel):
    item_ids: list[UUID]
    action: Literal["accept", "ignore"]


@router.post("/document-review/batch")
def batch_review(body: BatchReview, user: Principal, session: DB):
    rows = list(
        session.scalars(
            select(DocumentReviewItem).where(
                visible_condition(DocumentReviewItem, user.id),
                DocumentReviewItem.id.in_(body.item_ids),
            )
        )
    )
    results = []
    for row in rows:
        if body.action == "ignore":
            row.status = "ignored"
            results.append({"id": str(row.id), "status": "ignored"})
        else:
            value = accept_review(row.id, user, session)
            results.append(
                {
                    "id": str(row.id),
                    "status": value.status,
                    "target_url": value.target_url,
                }
            )
    session.commit()
    return {"results": results}
