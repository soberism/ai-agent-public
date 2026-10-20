"""追踪副本的规则脱敏；不修改模型请求或业务数据。"""

import hashlib
import hmac
import json
import re
from contextlib import contextmanager
from contextvars import ContextVar

from pydantic import SecretStr

from backend.core.security import settings

CREDENTIALS = {
    "password",
    "passwd",
    "pwd",
    "secret",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "set_cookie",
    "token",
    "access_token",
    "refresh_token",
    "session_token",
    "database_url",
    "checkpoint_url",
    "celery_broker_url",
    "connection_string",
    "密码",
    "密钥",
}
PRIVATE_FIELDS = {
    "name": "姓名",
    "full_name": "姓名",
    "display_name": "姓名",
    "username": "姓名",
    "assignee_name": "姓名",
    "contact_name": "姓名",
    "contact": "联系人",
    "姓名": "姓名",
    "address": "地址",
    "地址": "地址",
    "home_address": "地址",
    "street_address": "地址",
    "location": "地址",
    "email": "邮箱",
    "phone": "电话",
    "mobile": "电话",
    "id": "标识",
    "diagnosis": "健康信息",
    "medical_history": "健康信息",
    "health_info": "健康信息",
    "bank_account": "银行账户",
    "card_number": "银行账户",
    "身份证": "证件",
}
PATTERNS = [
    (
        "凭据",
        r"(?i)(?:Bearer\s+[a-z0-9._~+/=-]+|sk-[a-z0-9_-]+|lsv2_[a-z0-9_-]+|eyJ[a-z0-9_-]+\.[a-z0-9_-]+\.[a-z0-9_-]+)",
    ),
    (
        "凭据",
        r"(?i)(?:密码|密钥|password|api[_ -]?key|authorization|cookie)\s*[:：=是]\s*[^\s，,;；。\"'<>]+",
    ),
    ("链接", r"https?://[^\s\"'<>，。]+"),
    ("邮箱", r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}"),
    ("标识", r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"),
    ("证件", r"(?<!\w)\d{17}[\dXx](?!\w)"),
    ("电话", r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)"),
    ("电话", r"(?<!\w)\+\d(?:[\d ()-]{6,}\d)(?!\d)"),
    ("银行账户", r"(?<!\d)\d{16,19}(?!\d)"),
    ("IP", r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)"),
    ("姓名", r"(?<=(?:姓名))\s*[:：=为是]\s*[\u4e00-\u9fffA-Za-z· ]{2,30}"),
    (
        "姓名",
        r"(?<=邀请)[赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦许何吕施张孔曹严华金魏陶姜谢邹苏潘葛范彭鲁韦马苗方任袁柳唐罗梁宋][\u4e00-\u9fff]{1,2}(?=[，,。\s]|的邮箱)",
    ),
    ("地址", r"(?:住址|家庭地址|收货地址|地址)\s*[:：=为是]\s*[^\n，,;；。]+"),
    (
        "健康信息",
        r"(?:病史|诊断|我患有|我确诊|我对[^\n，。]{1,12}过敏)\s*[:：=为是]?[^\n，;；。]*",
    ),
    ("路径", r"/(?:Users|home)/[^\s\"'<>]+"),
]
PATTERNS = [(kind, re.compile(pattern)) for kind, pattern in PATTERNS]
PLACEHOLDER = re.compile(r"\[[^\[\]]+_[0-9a-f]{10}\]|\[凭据已移除\]")
ACTIVE_REDACTOR = ContextVar("trace_redactor", default=None)


class Redactor:
    def __init__(self):
        self.key = settings.cursor_secret.get_secret_value().encode()
        self.secrets = sorted(
            (
                value.get_secret_value()
                for value in (
                    getattr(settings, name) for name in type(settings).model_fields
                )
                if isinstance(value, SecretStr) and len(value.get_secret_value()) >= 4
            ),
            key=len,
            reverse=True,
        )
        self.entities = {}

    def placeholder(self, kind, value):
        digest = hmac.new(
            self.key, f"{kind}:{value}".encode(), hashlib.sha256
        ).hexdigest()[:10]
        return f"[{kind}_{digest}]"

    def field_kind(self, key, parent):
        normalized = re.sub(r"(?<=[a-z])(?=[A-Z])", "_", key).lower().replace("-", "_")
        if normalized in CREDENTIALS or normalized.endswith(
            ("_password", "_secret", "_api_key", "_token")
        ):
            return "凭据"
        if normalized == "name" and parent in {
            "function",
            "tool",
            "messages",
            "tools",
            "候选工具",
            "已展开工具",
            "discovered_tools",
            "described_tools",
        }:
            return None
        if normalized.endswith("_id"):
            return "标识"
        for suffix, kind in (
            ("_name", "姓名"),
            ("_email", "邮箱"),
            ("_address", "地址"),
            ("_phone", "电话"),
        ):
            if normalized.endswith(suffix) and normalized not in {
                "tool_name",
                "model_name",
            }:
                return kind
        return PRIVATE_FIELDS.get(normalized)

    def collect(self, value, parent="", depth=0):
        if depth > 20:
            return
        if isinstance(value, dict):
            for key, item in value.items():
                kind = self.field_kind(str(key), parent)
                if (
                    kind
                    and isinstance(item, str)
                    and item
                    and not PLACEHOLDER.fullmatch(item)
                ):
                    self.entities[item] = kind
                self.collect(item, str(key), depth + 1)
        elif isinstance(value, (list, tuple)):
            for item in value:
                self.collect(item, parent, depth + 1)
        elif isinstance(value, str) and value.lstrip().startswith(("{", "[")):
            try:
                self.collect(json.loads(value), parent, depth + 1)
            except ValueError, RecursionError:
                pass

    def text(self, value):
        parts = re.split(f"({PLACEHOLDER.pattern})", value)
        return "".join(
            part if PLACEHOLDER.fullmatch(part) else self.plain_text(part)
            for part in parts
        )

    def plain_text(self, value):
        for secret in self.secrets:
            value = value.replace(secret, "[凭据已移除]")
        for entity in sorted(self.entities, key=len, reverse=True):
            kind = self.entities[entity]
            value = value.replace(entity, self.placeholder(kind, entity))
        for kind, pattern in PATTERNS:
            value = pattern.sub(
                lambda match, kind=kind: self.placeholder(kind, match.group()), value
            )
        return value

    def redact(self, value, parent="", depth=0):
        if depth > 20:
            return "[深层内容已隐藏]"
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                kind = self.field_kind(str(key), parent)
                if isinstance(item, str) and PLACEHOLDER.fullmatch(item):
                    result[self.text(str(key))] = item
                elif kind == "凭据":
                    result[self.text(str(key))] = "[凭据已移除]"
                elif kind and isinstance(item, (str, int, float)) and item != "":
                    result[self.text(str(key))] = self.placeholder(kind, item)
                else:
                    result[self.text(str(key))] = self.redact(item, str(key), depth + 1)
            return result
        if isinstance(value, (list, tuple)):
            return [self.redact(item, parent, depth + 1) for item in value]
        if isinstance(value, str):
            if value.lstrip().startswith(("{", "[")):
                try:
                    parsed = json.loads(value)
                except ValueError, RecursionError:
                    pass
                else:
                    return json.dumps(
                        self.redact(parsed, parent, depth + 1), ensure_ascii=False
                    )
            return self.text(value)
        if value is None or isinstance(value, (bool, int, float)):
            return value
        return "[非文本内容已隐藏]"


def redact_payload(value):
    try:
        redactor = ACTIVE_REDACTOR.get() or Redactor()
        redactor.collect(value)
        return redactor.redact(value)
    except Exception:  # noqa: BLE001 -- 脱敏失败时关闭该载荷，不回退为原文。
        return {"redacted": "[内容脱敏失败，已隐藏]"}


@contextmanager
def redaction_scope():
    if ACTIVE_REDACTOR.get() is not None:
        yield
        return
    token = ACTIVE_REDACTOR.set(Redactor())
    try:
        yield
    finally:
        ACTIVE_REDACTOR.reset(token)
