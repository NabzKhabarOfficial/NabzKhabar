"""Persian-safe Instagram content helpers."""
from __future__ import annotations
import re
from typing import Any

ENGLISH_LETTER = re.compile(r"[A-Za-z]")
ALLOWED_LATIN = {"NABZ", "@NabzKhabarOfficial"}


def normalize_fa(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.replace("ي", "ی").replace("ى", "ی").replace("ك", "ک")
    text = text.replace("ۀ", "هٔ").replace("ة", "ه")
    text = text.replace("\u200f", "").replace("\u200e", "")
    text = re.sub(r"[ \t\r\n]+", " ", text)
    return text.strip()


def has_unapproved_english(text: str) -> bool:
    for token in re.findall(r"@[A-Za-z][A-Za-z0-9_]*|[A-Za-z][A-Za-z0-9_]*", text or ""):
        if token not in ALLOWED_LATIN and ("@" + token) not in ALLOWED_LATIN:
            return True
    return False


def _footer(username: str) -> str:
    return f"نبض خبر | NABZ\n{username}"


def build_caption(title: Any, summary: Any, source: Any, username: str = "@NabzKhabarOfficial", max_chars: int = 2200) -> str:
    title = normalize_fa(title)
    summary = normalize_fa(summary)
    source = normalize_fa(source)
    footer = _footer(username)
    prefix = f"📰 {title}\n\n"
    source_line = f"📌 منبع: {source}" if source else ""
    suffix = f"\n\n{source_line}\n\n{footer}" if source_line else f"\n\n{footer}"
    available = max(0, max_chars - len(prefix) - len(suffix))
    summary = summary if len(summary) <= available else (summary[: max(0, available - 1)].rsplit(" ", 1)[0] + "…")
    return prefix + summary + suffix


def validate_caption(caption: Any, max_chars: int = 2200) -> tuple[bool, str]:
    text = normalize_fa(caption)
    if not text:
        return False, "empty_caption"
    if len(text) > max_chars:
        return False, "caption_too_long"
    if has_unapproved_english(text):
        return False, "unapproved_english"
    if "نبض خبر" not in text or "@NabzKhabarOfficial" not in text:
        return False, "missing_brand_footer"
    return True, "ok"
