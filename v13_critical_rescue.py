"""NABZ V13 critical editorial rescue.

A narrow safety net for consequential geopolitical headlines that can score low
because they describe diplomacy/roadmaps/agreements rather than casualties.
It runs before final policy publication, so it must never promote foreign-local
stories into the translation queue.
"""

import v13_intelligence
import v13_policy_guard

CRITICAL_PAIRS = (
    ("iran", ("united states", "u.s.", "us", "america", "washington")),
    ("israel", ("iran", "gaza", "hamas", "hezbollah", "lebanon")),
    ("russia", ("ukraine", "nato", "united states", "europe")),
    ("china", ("taiwan", "united states", "philippines")),
    ("north korea", ("south korea", "japan", "united states")),
    ("canada", ("united states", "u.s.", "us", "america", "washington")),
)

CRITICAL_ACTIONS = (
    "roadmap", "talks", "negotiations", "negotiation", "agreement", "deal",
    "ceasefire", "truce", "nuclear", "conflict", "war", "sanctions",
    "sanction", "tariff", "tariffs", "military", "attack", "strike",
    "missile", "invasion", "ultimatum", "peace plan", "peace proposal", "summit",
    "مذاکرات", "مذاکره", "توافق", "آتش بس", "آتش‌بس", "هسته ای", "هسته‌ای",
    "تحریم", "جنگ", "درگیری", "حمله", "موشک", "نقشه راه", "طرح صلح", "نشست",
)


def _critical_geopolitical(candidate):
    title = str(candidate.get("title", "") or "").lower()
    if len(title) < 20:
        return False
    routine = (
        "said", "says", "remarks", "meeting", "visit", "visited", "speech",
        "opinion", "analysis", "profile", "گفت", "اظهارات", "دیدار", "سفر",
        "تحلیل", "نظر", "پروفایل",
    )
    action = any(x in title for x in CRITICAL_ACTIONS)
    if not action:
        return False
    # A concrete geopolitical pair is strongest.
    for primary, partners in CRITICAL_PAIRS:
        if primary in title and any(p in title for p in partners):
            return True
    # Other major global actors can qualify only with a concrete crisis/action.
    actors = (
        "trump", "putin", "zelensky", "netanyahu", "nato", "united nations",
        "united states", "washington", "canada", "ایران", "ترامپ", "پوتین",
        "زلنسکی", "نتانیاهو", "ناتو",
    )
    return any(a in title for a in actors) and action and not any(x in title for x in routine)


def install():
    original = v13_intelligence.is_publishable

    def wrapped(main, candidate):
        # Scope must be decided BEFORE scoring/selection. This prevents a local
        # foreign story such as a UK crime/weather item from consuming a slot,
        # triggering Argos, and failing only at the final policy gate.
        if v13_policy_guard._foreign_local_only(candidate):
            return False, 0, "foreign-local-preselection"

        ok, score, reason = original(main, candidate)
        if ok or not _critical_geopolitical(candidate):
            return ok, score, reason
        rescued_score = max(int(score or 0), v13_intelligence.MIN_EVENT_SCORE + 6)
        print(f"V13 CRITICAL EDITORIAL RESCUE: {candidate.get('title', '')}")
        return True, rescued_score, "critical-geopolitical-rescue"

    v13_intelligence.is_publishable = wrapped
    print("V13 CRITICAL EDITORIAL RESCUE ACTIVE")
