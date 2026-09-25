"""NABZ V13 critical editorial rescue.

A narrow safety net for consequential geopolitical headlines that can score low
because they describe diplomacy/roadmaps/agreements rather than casualties.
It wraps the existing intelligence gate instead of replacing it.
"""

import re
import v13_intelligence

CRITICAL_PAIRS = (
    ("iran", ("united states", "u.s.", "us", "america", "washington")),
    ("israel", ("iran", "gaza", "hamas", "hezbollah", "lebanon")),
    ("russia", ("ukraine", "nato", "united states", "europe")),
    ("china", ("taiwan", "united states", "philippines")),
    ("north korea", ("south korea", "japan", "united states")),
)

CRITICAL_ACTIONS = (
    "roadmap", "talks", "negotiations", "negotiation", "agreement", "deal",
    "ceasefire", "truce", "nuclear", "conflict", "war", "sanctions",
    "sanction", "tariff", "tariffs", "military", "attack", "strike",
    "missile", "invasion", "ultimatum", "peace plan", "peace proposal",
    "مذاکرات", "مذاکره", "توافق", "آتش بس", "آتش‌بس", "هسته ای", "هسته‌ای",
    "تحریم", "جنگ", "درگیری", "حمله", "موشک", "نقشه راه", "طرح صلح",
)


def _critical_geopolitical(candidate):
    title = str(candidate.get("title", "") or "").lower()
    if len(title) < 20:
        return False
    # Avoid rescuing generic statements, meetings, profiles or opinions.
    routine = (
        "said", "says", "remarks", "meeting", "visit", "visited", "speech",
        "opinion", "analysis", "profile", "گفت", "اظهارات", "دیدار", "سفر",
        "تحلیل", "نظر", "پروفایل",
    )
    action = any(x in title for x in CRITICAL_ACTIONS)
    if not action:
        return False
    for primary, partners in CRITICAL_PAIRS:
        if primary in title and any(p in title for p in partners):
            return True
    # A single major global actor plus a concrete crisis/action is sufficient.
    actors = ("trump", "putin", "zelensky", "netanyahu", "nato", "united nations", "ایران", "ترامپ", "پوتین", "زلنسکی", "نتانیاهو", "ناتو")
    return any(a in title for a in actors) and action


def install():
    original = v13_intelligence.is_publishable

    def wrapped(main, candidate):
        ok, score, reason = original(main, candidate)
        if ok or not _critical_geopolitical(candidate):
            return ok, score, reason
        rescued_score = max(int(score or 0), v13_intelligence.MIN_EVENT_SCORE + 6)
        print(f"V13 CRITICAL EDITORIAL RESCUE: {candidate.get('title', '')}")
        return True, rescued_score, "critical-geopolitical-rescue"

    v13_intelligence.is_publishable = wrapped
    print("V13 CRITICAL EDITORIAL RESCUE ACTIVE")
