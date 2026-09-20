"""Instagram-safe Persian content validation and formatting."""

from __future__ import annotations

import re

ENGLISH_LETTER = re.compile(r"[A-Za-z]")


def contains_english(text: str) -> bool:
    return bool(ENGLISH_LETTER.search(text))


def build_caption(title: str, summary: str, source: str, username: str = "@NabzKhabarOfficial") -> str:
    title = " ".join(title.split())
    summary = " ".join(summary.split())
    source = " ".join(source.split())

    caption = (
        f"📰 {title}\n\n"
        f"{summary}\n\n"
        f"📌 منبع: {source}\n\n"
        f"نبض خبر | NABZ\n{username}"
    )

    if len(caption) > 2200:
        caption = caption[:2190].rstrip() + "…"
    return caption


def validate_caption(caption: str) -> tuple[bool, str]:
    if not caption.strip():
        return False, "empty_caption"
    if len(caption) > 2200:
        return False, "caption_too_long"
    return True, "ok"
