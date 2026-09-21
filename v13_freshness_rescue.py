"""V13 critical-news freshness rescue.

Keeps the normal 30-minute freshness policy, but prevents a genuinely
high-impact event from being discarded before scoring when an RSS publisher
timestamps/delivers it late. This is intentionally narrow and applies only
to the news collection layer.
"""

import re
from datetime import datetime, timezone


NORMAL_WINDOW_MINUTES = 30
CRITICAL_RESCUE_MAX_HOURS = 6


CRITICAL_TERMS = (
    "انفجار", "حمله", "حملات", "جنگ", "موشک", "حمله موشکی",
    "بمباران", "درگیری نظامی", "عملیات نظامی", "زلزله", "سیل",
    "سونامی", "طوفان", "رانش زمین", "آتش سوزی", "آتش‌سوزی",
    "سقوط هواپیما", "کشته", "زخمی", "مفقود", "ترور", "گروگان",
    "آتش بس", "آتش‌بس", "حمله سایبری", "قطعی اینترنت", "قطع اینترنت",
    "وضعیت اضطراری", "تخلیه", "تحریم", "ممنوعیت", "تعلیق",
    "توقف", "کمبود سوخت", "قطعی برق", "قطعی گاز", "فاجعه",
    "حمله", "missile", "strike", "bombing", "explosion", "earthquake",
    "flood", "typhoon", "tsunami", "landslide", "wildfire", "shooting",
    "hostage", "military", "ceasefire", "sanction", "cyberattack",
    "emergency", "evacuation", "outage", "crash",
)

EVENT_TERMS = (
    "کشته", "زخمی", "مفقود", "انفجار", "حمله", "حملات", "موشک",
    "بمباران", "سقوط", "زلزله", "سیل", "طوفان", "سونامی", "رانش",
    "آتش سوزی", "آتش‌سوزی", "ترور", "درگیری", "تخلیه", "قطعی",
    "اختلال", "تعلیق", "توقف", "ممنوع", "آتش بس", "آتش‌بس",
    "شلیک", "گروگان", "missile", "strike", "bombing", "explosion",
    "earthquake", "flood", "storm", "typhoon", "tsunami", "landslide",
    "killed", "wounded", "missing", "crash", "shooting", "hostage",
    "evacuat", "outage", "suspended", "banned",
)


def _text(candidate):
    return " ".join(
        str(candidate.get(k, "") or "")
        for k in ("title", "summary", "description")
    ).strip()


def _is_critical(candidate):
    title = str(candidate.get("title", "") or "").lower()
    body = _text(candidate).lower()

    has_critical = any(term.lower() in title for term in CRITICAL_TERMS)
    if not has_critical:
        return False

    # Require an actual event/consequence signal as well. This prevents
    # generic mentions such as "talks about war" from bypassing freshness.
    return any(term.lower() in body for term in EVENT_TERMS)


def _age_seconds(published_at):
    if not published_at:
        return None
    try:
        return max(
            0.0,
            (datetime.now(timezone.utc) - published_at).total_seconds(),
        )
    except Exception:
        return None


def install(main):
    """Install the narrow freshness-rescue wrapper on the V13 engine."""
    original_collect_feed = main.collect_feed

    # Expand the core RSS intake temporarily so late-arriving critical stories
    # can be inspected. The wrapper below immediately restores the normal
    # 30-minute rule for non-critical stories.
    def rescued_collect_feed(category, url, is_google=False):
        old_window = main.FEED_COLLECTION_WINDOW_MINUTES
        try:
            main.FEED_COLLECTION_WINDOW_MINUTES = (
                CRITICAL_RESCUE_MAX_HOURS * 60
            )
            candidates = original_collect_feed(
                category, url, is_google=is_google
            )
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
                print(
                    "V13 FRESHNESS RESCUE: "
                    f"{category} | {age_hours:.2f}h old | "
                    f"{candidate.get('title', '')}"
                )
            else:
                print(
                    "V13 FRESHNESS DROP: "
                    f"{category} | {age_hours:.2f}h old | "
                    f"{candidate.get('title', '')}"
                )

        if rescued:
            print(
                f"V13 FRESHNESS RESCUE TOTAL: {rescued} "
                f"(normal={NORMAL_WINDOW_MINUTES}m, "
                f"critical_max={CRITICAL_RESCUE_MAX_HOURS}h)"
            )

        return kept

    main.collect_feed = rescued_collect_feed
    print(
        "V13 FRESHNESS RESCUE ACTIVE: "
        f"normal={NORMAL_WINDOW_MINUTES}m, "
        f"critical_max={CRITICAL_RESCUE_MAX_HOURS}h"
    )
