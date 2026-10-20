"""Account-wide atomic request budgets and serialized admission of conversation runs."""

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from backend.core.security import DB, APIError, Principal, redis, settings
from backend.db.agent_models import AgentRun
from backend.db.models import User

LIMIT = """
local wait = 0
for i,key in ipairs(KEYS) do
  if tonumber(redis.call('GET', key) or '0') >= tonumber(ARGV[i]) then
    wait = math.max(wait, math.max(1, redis.call('TTL', key)))
  end
end
if wait > 0 then return wait end
for i,key in ipairs(KEYS) do
  local n = redis.call('INCR', key)
  if n == 1 then redis.call('EXPIRE', key, tonumber(ARGV[i + #KEYS])) end
end
return 0
"""


def charge(owner_id, kind, store=None):
    store = redis if store is None else store
    prefix = f"{settings.redis_namespace}ai-quota:{owner_id}:{kind}:"
    wait = store.eval(
        LIMIT,
        2,
        prefix + "minute",
        prefix + "day",
        getattr(settings, f"ai_{kind}_per_minute"),
        getattr(settings, f"ai_{kind}_per_day"),
        60,
        86400,
    )
    if wait:
        raise APIError(
            429,
            "AI_RATE_LIMITED",
            "AI使用已达到当前额度，请稍后再试",
            headers={"Retry-After": str(wait)},
        )


def enforce(request: Request, user: Principal, session: DB):
    if request.method != "POST":
        yield
        return
    path = request.url.path.rstrip("/")
    conversation = path == "/api/agent/runs" or (
        path.startswith("/api/agent/runs/") and path.endswith("/resume")
    )
    legacy = path == "/api/assistant/messages"
    transcription = path == "/api/assistant/transcriptions" or (
        path.startswith("/api/assistant/voice-memos/") and path.endswith("/transcribe")
    )
    if conversation or legacy or transcription:
        try:
            session.execute(
                select(User.id).where(User.id == user.id).with_for_update(nowait=True)
            )
        except OperationalError as error:
            if getattr(error.orig, "sqlstate", None) != "55P03":
                raise
            raise APIError(
                409, "AI_BUSY", "还有一个AI请求正在处理中，请稍后再试"
            ) from None
        active = session.scalar(
            select(func.count())
            .select_from(AgentRun)
            .where(
                AgentRun.owner_id == user.id, AgentRun.status.in_(("queued", "running"))
            )
        )
        if active >= settings.ai_max_active_runs:
            raise APIError(
                409, "AI_BUSY", "还有一个AI任务正在处理中，请完成或取消后再试"
            )
        charge(user.id, "transcription" if transcription else "chat")
    yield
