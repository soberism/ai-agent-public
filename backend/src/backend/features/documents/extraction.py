import re
from datetime import date
from pathlib import Path

DATE_PATTERNS = (
    re.compile(
        r"(?P<year>20\d{2})-(?P<month>1[0-2]|0?[1-9])-(?P<day>3[01]|[12]\d|0?[1-9])(?!\d)"
    ),
    re.compile(
        r"(?P<year>20\d{2})年(?P<month>1[0-2]|0?[1-9])月(?P<day>3[01]|[12]\d|0?[1-9])日"
    ),
)
EVENT_WORDS = ("活动", "会议", "家长会", "预约", "课程", "演出", "聚会")


def decode_text(content: bytes, filename: str, media_type: str | None):
    suffix = Path(filename).suffix.lower()
    if not (
        (media_type or "").startswith("text/") or suffix in (".txt", ".md", ".csv")
    ):
        return None
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return None


def extract_candidates(text: str, fallback_title: str):
    candidates = []
    seen = set()
    for line in (part.strip() for part in text.splitlines() if part.strip()):
        for pattern in DATE_PATTERNS:
            for match in pattern.finditer(line):
                try:
                    found = date(
                        int(match.group("year")),
                        int(match.group("month")),
                        int(match.group("day")),
                    )
                except ValueError:
                    continue
                key = (found, line)
                if key in seen:
                    continue
                seen.add(key)
                title = re.sub(r"\s+", " ", line).strip()[:100] or fallback_title[:100]
                candidates.append(
                    {
                        "target_type": "event"
                        if any(word in line for word in EVENT_WORDS)
                        else "todo",
                        "title": title,
                        "evidence": line[:500],
                        "confidence": 0.8,
                        "proposed_date": found.isoformat(),
                    }
                )
    return candidates
