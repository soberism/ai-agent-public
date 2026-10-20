"""注册邮箱凭证：Redis 原子预留、激活与单次消费。"""

import hashlib
import hmac
import secrets
import smtplib

from redis.exceptions import RedisError

from backend.core.security import APIError, client_ip, settings
from backend.features.auth.mail import send_code

RESERVE = """
local cooldown = redis.call('PTTL', KEYS[2])
local wait = cooldown >= 0 and math.max(1, math.ceil(cooldown / 1000)) or 0
for i=3,4 do
  if tonumber(redis.call('GET', KEYS[i]) or '0') >= tonumber(ARGV[i]) then
    wait = math.max(wait, math.max(1, math.ceil(redis.call('PTTL', KEYS[i]) / 1000)))
  end
end
if wait > 0 then return wait end
for i=3,4 do
  if redis.call('INCR', KEYS[i]) == 1 then redis.call('EXPIRE', KEYS[i], 3600) end
end
redis.call('SET', KEYS[2], '1', 'EX', 60)
redis.call('DEL', KEYS[1])
redis.call('HSET', KEYS[1], 'nonce', ARGV[1], 'digest', ARGV[2], 'state', 'pending', 'attempts', 0)
redis.call('EXPIRE', KEYS[1], 600)
return 0
"""
FINISH = """
if redis.call('HGET', KEYS[1], 'nonce') ~= ARGV[1] then return 0 end
if ARGV[2] == 'active' then
  redis.call('HSET', KEYS[1], 'state', 'active')
else redis.call('DEL', KEYS[1]) end
return 1
"""
CONSUME = """
if redis.call('HGET', KEYS[1], 'state') ~= 'active' then return 0 end
if redis.call('HGET', KEYS[1], 'nonce') ~= ARGV[1] then return 0 end
if redis.call('HGET', KEYS[1], 'digest') == ARGV[2] then
  redis.call('DEL', KEYS[1])
  return 1
end
if redis.call('HINCRBY', KEYS[1], 'attempts', 1) >= 5 then redis.call('DEL', KEYS[1]) end
return 0
"""


def keys(email, ip):
    prefix = settings.redis_namespace + "email-verification:"
    mailbox = hashlib.sha256(email.encode()).hexdigest()
    address = hashlib.sha256(ip.encode()).hexdigest()
    return [
        prefix + mailbox,
        prefix + "cooldown:" + mailbox,
        prefix + "email:" + mailbox,
        prefix + "ip:" + address,
    ]


def digest(email, nonce, code):
    secret = settings.email_verification_secret.get_secret_value()
    return hmac.new(
        secret.encode(), f"register:{email}:{nonce}:{code}".encode(), hashlib.sha256
    ).hexdigest()


def send_failure():
    return APIError(
        503,
        "SERVICE_UNAVAILABLE",
        "验证码暂时无法发送，请稍后重试",
        headers={"Retry-After": "60"},
    )


def request_code(store, request, email):
    if not all(
        (
            settings.smtp_host,
            settings.smtp_username,
            settings.smtp_password.get_secret_value(),
            settings.smtp_from,
            len(settings.email_verification_secret.get_secret_value()) >= 32,
        )
    ):
        raise send_failure()
    record, *buckets = keys(email, client_ip(request))
    nonce = secrets.token_urlsafe(32)
    code = f"{secrets.randbelow(1000000):06d}"
    try:
        wait = store.eval(
            RESERVE, 4, record, *buckets, nonce, digest(email, nonce, code), 5, 20
        )
        if wait:
            raise APIError(
                429,
                "RATE_LIMITED",
                "发送过于频繁，请稍后再试",
                headers={"Retry-After": str(max(1, wait))},
            )
        send_code(email, code)
        if not store.eval(FINISH, 1, record, nonce, "active"):
            raise send_failure()
    except RedisError, smtplib.SMTPException, OSError, ValueError:
        try:
            store.eval(FINISH, 1, record, nonce, "delete")
        except RedisError:
            pass
        raise send_failure() from None


def consume_code(store, email, code):
    record = keys(email, "")[0]
    nonce = store.hget(record, "nonce")
    if (
        len(settings.email_verification_secret.get_secret_value()) < 32
        or not nonce
        or not store.eval(CONSUME, 1, record, nonce, digest(email, nonce, code))
    ):
        raise APIError(
            422,
            "INVALID_VERIFICATION_CODE",
            "验证码无效或已过期，请重新获取",
            fields={"verification_code": "验证码无效或已过期，请重新获取"},
        )
