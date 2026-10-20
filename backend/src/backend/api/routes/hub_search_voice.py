from zoneinfo import ZoneInfo

from sqlalchemy import String, cast, func, literal, or_, select

from backend.api.hub_schemas import SearchItem
from backend.db.cross_system_models import VoiceMemo
from backend.features.sharing.access import visible_condition


def search_voice(session, user, terms):
    created = VoiceMemo.created_at
    if session.get_bind().dialect.name == "postgresql":
        created = func.timezone(user.timezone, created)
    matches = or_(
        *(VoiceMemo.transcript.ilike(term, escape="\\") for term in terms),
        *(cast(created, String).ilike(term, escape="\\") for term in terms),
        *(literal("录音 语音 语音备忘").ilike(term, escape="\\") for term in terms),
    )
    rows = session.scalars(
        select(VoiceMemo)
        .where(visible_condition(VoiceMemo, user.id), matches)
        .order_by(VoiceMemo.created_at.desc(), VoiceMemo.id)
    )
    results = []
    for row in rows:
        date = row.created_at.astimezone(ZoneInfo(user.timezone)).strftime(
            "%Y-%m-%d %H:%M"
        )
        results.append(
            SearchItem(
                id=row.id,
                kind="voice_memo",
                title=f"{'录音' if row.mime_type else '语音备忘'} · {date}",
                detail=row.transcript[:160] or "未转文字，可播放录音",
                url=f"/voice-memos#voice-memo-{row.id}",
            )
        )
    return results
