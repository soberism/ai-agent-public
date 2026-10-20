import hashlib
import ipaddress
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from argon2 import PasswordHasher
from fastapi import Depends, Request
from redis import Redis
from sqlalchemy.orm import Session

from backend.core.config import Settings
from backend.db.models import User
from backend.db.session import get_session

settings = Settings()
password_hasher = PasswordHasher()
dummy_hash = password_hasher.hash(secrets.token_urlsafe(32))
SESSION_SECONDS = 604800
redis = Redis(
    host=settings.redis_host,
    port=settings.redis_port,
    password=settings.redis_password.get_secret_value(),
    decode_responses=True,
    socket_connect_timeout=3,
    socket_timeout=3,
)


def get_redis():
    return redis


class APIError(Exception):
    def __init__(self, status, code, message, fields=None, headers=None):
        self.status, self.code, self.message = status, code, message
        self.fields, self.headers = fields, headers


def unavailable(message="服务暂不可用，请稍后重试"):
    return APIError(503, "SERVICE_UNAVAILABLE", message)


def session_key(token):
    return settings.redis_namespace + "session:" + token


def client_ip(request):
    direct = request.client.host if request.client else "unknown"
    if direct not in settings.trusted_proxies:
        return direct
    chain = request.headers.get("x-forwarded-for", "").split(",")
    try:
        addresses = [str(ipaddress.ip_address(value.strip())) for value in chain]
    except ValueError:
        return direct
    for address in reversed(addresses):
        if address not in settings.trusted_proxies:
            return address
    return addresses[0] if addresses else direct


LIMIT_SCRIPT = """
local wait = 0
for i,key in ipairs(KEYS) do
  local n = redis.call('INCR', key)
  if n == 1 then redis.call('EXPIRE', key, 900) end
  if n > tonumber(ARGV[i]) then wait = math.max(wait, redis.call('TTL', key)) end
end
return wait
"""


def rate_limit(store, request, email=None):
    buckets = [
        (
            "register:ip:" if email is None else "login:ip:",
            client_ip(request),
            10 if email is None else 30,
        )
    ]
    if email is not None:
        buckets.append(("login:email:", email, 10))
    keys = [
        settings.redis_namespace + kind + hashlib.sha256(value.encode()).hexdigest()
        for kind, value, _ in buckets
    ]
    wait = store.eval(
        LIMIT_SCRIPT, len(keys), *keys, *(limit for _, _, limit in buckets)
    )
    if wait:
        raise APIError(
            429,
            "RATE_LIMITED",
            "操作过于频繁，请稍后再试",
            headers={"Retry-After": str(max(1, wait))},
        )


ROTATE_SCRIPT = """
redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
if KEYS[1] ~= KEYS[2] then redis.call('DEL', KEYS[2]) end
return 1
"""


def establish_session(store, user, request, response):
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    expires = now + timedelta(seconds=SESSION_SECONDS)
    value = json.dumps(
        {
            "user_id": str(user.id),
            "auth_version": user.auth_version,
            "created_at": now.isoformat(),
            "expires_at": expires.isoformat(),
        }
    )
    old = request.cookies.get("session", "")
    store.eval(
        ROTATE_SCRIPT, 2, session_key(token), session_key(old), value, SESSION_SECONDS
    )
    response.set_cookie(
        "session",
        token,
        max_age=SESSION_SECONDS,
        expires=expires,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


DB = Annotated[Session, Depends(get_session)]
Store = Annotated[Redis, Depends(get_redis)]


def current_user(request: Request, session: DB, store: Store):
    token = request.cookies.get("session")
    if not token or len(token) > 128:
        raise APIError(401, "SESSION_EXPIRED", "登录已失效，请重新登录")
    value = store.get(session_key(token))
    try:
        data = json.loads(value) if value else {}
        valid = datetime.fromisoformat(data["expires_at"]) > datetime.now(UTC)
        user_id = UUID(data["user_id"])
    except ValueError, KeyError, TypeError:
        valid = False
    if not valid:
        raise APIError(401, "SESSION_EXPIRED", "登录已失效，请重新登录")
    user = session.get(User, user_id)
    if (
        user is None
        or not user.active
        or data.get("auth_version", 0) != user.auth_version
    ):
        raise APIError(401, "SESSION_EXPIRED", "登录已失效，请重新登录")
    return user


Principal = Annotated[User, Depends(current_user)]
