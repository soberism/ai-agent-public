import re
from uuid import UUID

from sqlalchemy import select

from backend.db.models import AssistantMemory, AssistantProfile

SENSITIVE_WORDS = re.compile(
    r"密码|口令|验证码|身份证|银行卡|信用卡|api\s*key|access\s*token|secret|令牌",
    re.IGNORECASE,
)


def sensitive(content: str) -> bool:
    compact = re.sub(r"[\s-]", "", content)
    return bool(
        SENSITIVE_WORDS.search(content)
        or re.search(r"(?<!\d)\d{17}[\dXx](?!\d)", compact)
        or re.search(r"(?<!\d)\d{13,19}(?!\d)", compact)
    )


def model_context(session, owner_id: UUID) -> tuple[str, list[str]]:
    profile = session.get(AssistantProfile, owner_id)
    if profile is None or not profile.memory_enabled:
        return profile.custom_instructions if profile else "", []
    memories = list(
        session.scalars(
            select(AssistantMemory)
            .where(
                AssistantMemory.owner_id == owner_id,
                AssistantMemory.enabled.is_(True),
            )
            .order_by(AssistantMemory.updated_at.desc(), AssistantMemory.id.desc())
            .limit(20)
        )
    )
    return profile.custom_instructions, [value.content for value in reversed(memories)]
