"""V13 critical-news freshness rescue.

Keeps the normal 30-minute freshness policy, but prevents genuinely
high-impact events from being discarded before scoring when an RSS publisher
delivers them late.
"""

import re
from datetime import datetime, timezone

NORMAL_WINDOW_MINUTES = 30
CRITICAL_RESCUE_MAX_HOURS = 6

CRITICAL_TERMS = (
    "انفجار", "حمله", "حملات", "جنگ", "درگیری", "موشک", "حمله موشکی",
    "بمباران", "درگیری نظامی", "عملیات نظامی", "زلزله", "سیل", "سونامی",
    "طوفان", "رانش زمین", "آتش سوزی", "آتش‌سوزی", "سقوط هواپیما",
    "کشته", "زخمی", "مفقود", "ترور", "گروگان", "آتش بس", "آتش‌بس",
    "حمله سایبری", "قطعی اینترنت", "قطع اینترنت", "وضعیت اضطراری", "تخلیه",
    "تحریم", "ممنوعیت", "تعلیق", "توقف", "کمبود سوخت", "قطعی برق",
    "قطعی گاز", "فاجعه", "missile", "attack", "attacks", "strike", "strikes",
    "war", "conflict", "invasion", "bombing", "explosion", "earthquake",
    "flood", "typhoon", "hurricane", "tsunami", "landslide", "wildfire",
    "shooting", "hostage", "military", "ceasefire", "sanction", "sanctions",
    "cyberattack", "emergency", "evacuation", "outage", "crash", "coup",
    "nuclear", "summit", "unga", "un general assembly", "united nations",
    "nato", "tariff", "tariffs",
)

EVENT_TERMS = (
    "کشته", "زخمی", "مفقود", "انفجار", "حمله", "حملات", "جنگ", "درگیری",
    "موشک", "بمباران", "سقوط", "زلزله", "سیل", "طوفان", "سونامی", "رانش",
    "آتش سوزی", "آتش‌سوزی", "ترور", "تخلیه", "قطعی", "اختلال", "تعلیق",
    "توقف", "ممنوع", "آتش بس", "آتش‌بس", "شلیک", "گروگان", "تحریم",
    "توافق", "تارiff", "missile", "attack", "attacks", "strike", "strikes",
    "war", "conflict", "invasion", "bombing", "explosion", "earthquake",
    "flood", "storm", "typhoon", "hurricane", "tsunami", "landslide", "killed",
    "wounded", "missing", "crash", "shooting", "hostage", "evacuat", "outage",
    "suspended", "banned", "sanction", "sanctions", "coup", "nuclear", "summit",
    "unga", "un general assembly", "united nations", "nato", "tariff", "tariffs",
)


def _text(candidate):
    return " ".join(str(candidate.get(k, "") or "") for k in ("title", "summary", "description")).strip()


def _is_critical(candidate):
    title = str(candidate.get("title", "") or "").lower()
    body = _text(candidate).lower()
    if not any(term.lower() in title for term in CRITICAL_TERMS):
        return False
    return any(term.lower() in body for term in EVENT_TERMS)


def _age_seconds(published_at):
    if not published_at:
        return None
    try:
        return max(0.0, (datetime.now(timezone.utc) - published_at).total_seconds())
    except Exception:
        return None


def install(main):
    original_collect_feed = main.collect_feed

    def rescued_collect_feed(category, url, is_google=False):
        old_window = main.FEED_COLLECTION_WINDOW_MINUTES
        try:
            main.FEED_COLLECTION_WINDOW_MINUTES = CRITICAL_RESCUE_MAX_HOURS * 60
            candidates = original_collect_feed(category, url, is_google=is_google)
        finally:
            main.FEED_COLLECTION_WINDOW_MINUTES = old_window

        kept = []
        rescued = 0
        for candidate in candidates:
            age = _age_seconds(candidate.get("published_at"))
            if age is None or age <= NORMAL_WINDOW_MINUTES * 60:
                kept.append(candidate)
                continue

            age_hours = age / 3600.0
            if age <= CRITICAL_RESCUE_MAX_HOURS * 3600 and _is_critical(candidate):
                candidate["freshness_rescued"] = True
                candidate["freshness_rescue_age_hours"] = round(age_hours, 2)
                kept.append(candidate)
                rescued += 1
                print(f"V13 FRESHNESS RESCUE: {category} | {age_hours:.2f}h old | {candidate.get('title', '')}")
            else:
                print(f"V13 FRESHNESS DROP: {category} | {age_hours:.2f}h old | {candidate.get('title', '')}")

        if rescued:
            print(f"V13 FRESHNESS RESCUE TOTAL: {rescued} (normal={NORMAL_WINDOW_MINUTES}m, critical_max={CRITICAL_RESCUE_MAX_HOURS}h)")
        return kept

    main.collect_feed = rescued_collect_feed
    print(f"V13 FRESHNESS RESCUE ACTIVE: normal={NORMAL_WINDOW_MINUTES}m, critical_max={CRITICAL_RESCUE_MAX_HOURS}h")
