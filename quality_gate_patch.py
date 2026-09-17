"""Conservative pre-publication quality gate for NabzKhabar.

This layer only rejects clearly malformed candidates before the v11 core runs.
It does not change deduplication, ranking, scheduling, captions, media choice,
or history. No network calls or paid services are used.
"""

import re
import main

_ORIGINAL_PROCESS_NEWS = main.process_news

_URL_RE = re.compile(r"^https?://[^\s]+$", re.I)
_SITE_CHROME_RE = re.compile(
    r"(?:فیلم\s*>>|ویدئو\s*>>|ویدیو\s*>>|تعداد\s*بازدید\s*:|"
    r"کد\s*ویدیو|دانلود\s*ویدیو|کد\s*خبر\s*:|تاریخ\s*انتشار\s*:)",
    re.I,
)


def _text(value):
    return str(value or "").strip()


def _title_is_valid(candidate):
    title = _text(candidate.get("title"))
    if not title:
        return False, "missing_title"
    if len(title) < 8:
        return False, "title_too_short"
    if len(title) > 240:
        return False, "title_too_long"
    if _SITE_CHROME_RE.search(title):
        return False, "title_contains_site_chrome"
    return True, ""


def _link_is_valid(candidate):
    link = _text(
        candidate.get("canonical_article_url")
        or candidate.get("resolved_link")
        or candidate.get("link")
    )
    if not link:
        return False, "missing_link"
    if not _URL_RE.match(link):
        return False, "invalid_link"
    return True, ""


def validate_candidate(candidate):
    if not isinstance(candidate, dict):
        return False, "candidate_not_dict"

    ok, reason = _title_is_valid(candidate)
    if not ok:
        return False, reason

    ok, reason = _link_is_valid(candidate)
    if not ok:
        return False, reason

    return True, ""


def guarded_process_news(candidate, hash_history, title_history):
    ok, reason = validate_candidate(candidate)
    if not ok:
        title = _text(candidate.get("title")) if isinstance(candidate, dict) else ""
        print(f"QUALITY GATE BLOCKED: {reason} | {title}")
        return False

    return _ORIGINAL_PROCESS_NEWS(candidate, hash_history, title_history)


main.process_news = guarded_process_news
print("Pre-publication quality gate: enabled")
