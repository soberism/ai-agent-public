import base64
import hmac
import json
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from backend.core.security import APIError, settings


def encode_cursor(data):
    raw = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    signature = hmac.digest(
        settings.cursor_secret.get_secret_value().encode(), raw, "sha256"
    )
    return base64.urlsafe_b64encode(raw + signature).decode().rstrip("=")


def decode_cursor(value, scope):
    try:
        raw = base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
        )
        payload, signature = raw[:-32], raw[-32:]
        if not hmac.compare_digest(
            signature,
            hmac.digest(
                settings.cursor_secret.get_secret_value().encode(), payload, "sha256"
            ),
        ):
            raise ValueError()
        data = json.loads(payload)
        if any(data[key] != value for key, value in scope.items()):
            raise ValueError()
        now = datetime.fromisoformat(data["now"])
        if (
            now.tzinfo is None
            or data["day"] != now.astimezone(ZoneInfo(scope["tz"])).date().isoformat()
        ):
            raise ValueError()
        UUID(data["id"])
        datetime.fromisoformat(data["created"])
        if data["due"] is not None:
            datetime.fromisoformat(data["due"])
        return data, now
    except ValueError, KeyError, TypeError, json.JSONDecodeError:
        raise APIError(422, "INVALID_CURSOR", "分页标识无效，请重新加载") from None
