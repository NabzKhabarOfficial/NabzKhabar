"""Concurrency-safe critical-news freshness rescue."""
import re
import threading
from datetime import datetime, timezone

NORMAL_WINDOW_MINUTES = 30
CRITICAL_RESCUE_MAX_HOURS = 6

CRITICAL_TERMS = ("انفجار", "حمله", "حملات", "جنگ", "درگیری", "موشک", "بمباران", "زلزله", "سیل", "سونامی", "طوفان", "آتش سوزی", "آتش‌سوزی", "سقوط هواپیما", "کشته", "زخمی", "مفقود", "ترور", "گروگان", "آتش بس", "آتش‌بس", "حمله سایبری", "قطعی اینترنت", "تحریم", "وضعیت اضطراری", "missile", "attack", "strike", "war", "conflict", "invasion", "bombing", "explosion", "earthquake", "flood", "hurricane", "tsunami", "wildfire", "shooting", "hostage", "military", "ceasefire", "sanction", "cyberattack", "emergency", "evacuation", "outage", "crash", "coup", "nuclear", "summit", "tariff")
ROUTINE_EXCLUSIONS = ("opinion", "analysis", "commentary", "review", "explainer", "tutorial", "تحلیل", "دیدگاه", "نظر", "راهنما", "آموزشی", "سلبریتی", "سبک زندگی")
SYMBOLIC_EXCLUSIONS = ("تندیس", "مجسمه", "یادمان", "یادبود", "باغ موزه", "گرامیداشت", "مراسم", "statue", "memorial", "monument", "ceremony")

# The legacy collector reads the window from module globals. Serialize the short
# compatibility window so concurrent feed workers cannot leak rescue settings.
_WINDOW_LOCK = threading.RLock()

def _contains(value, terms):
    value = str(value or "").lower()
    for term in terms:
        term = str(term).strip().lower()
        if not term:
            continue
        if any("\u0600" <= ch <= "\u06ff" for ch in term):
            if term in value:
                return True
        elif re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", value, re.I):
            return True
    return False

def _critical(candidate):
    title = str(candidate.get("title", "") or "").strip().lower()
    if not title or _contains(title, ROUTINE_EXCLUSIONS):
        return False
    concrete = ("کشته", "زخمی", "مفقود", "انفجار", "حمله", "حملات", "موشک", "بمباران", "سقوط", "زلزله", "سیل", "طوفان", "سونامی", "آتش سوزی", "آتش‌سوزی", "ترور", "تخلیه", "قطعی", "اختلال", "تعلیق", "توقف", "ممنوع", "آتش بس", "آتش‌بس", "تحریم", "شلیک", "گروگان", "missile", "attack", "strike", "bombing", "explosion", "earthquake", "flood", "storm", "hurricane", "tsunami", "killed", "wounded", "missing", "crash", "shooting", "hostage", "evacuat", "outage", "suspended", "banned", "sanction", "coup")
    if _contains(title, SYMBOLIC_EXCLUSIONS) and not _contains(title, concrete):
        return False
    return _contains(title, CRITICAL_TERMS) and _contains(title, concrete)

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
        with _WINDOW_LOCK:
            old_window = main.FEED_COLLECTION_WINDOW_MINUTES
            old_predicate = getattr(main, "is_important_news_rescue_candidate", None)
            try:
                main.FEED_COLLECTION_WINDOW_MINUTES = CRITICAL_RESCUE_MAX_HOURS * 60
                main.is_important_news_rescue_candidate = lambda title: True
                candidates = original_collect_feed(category, url, is_google=is_google)
            finally:
                main.FEED_COLLECTION_WINDOW_MINUTES = old_window
                if old_predicate is not None:
                    main.is_important_news_rescue_candidate = old_predicate
        kept = []
        for candidate in candidates:
            age = _age_seconds(candidate.get("published_at"))
            if age is None or age <= NORMAL_WINDOW_MINUTES * 60:
                kept.append(candidate)
            elif age <= CRITICAL_RESCUE_MAX_HOURS * 3600 and _critical(candidate):
                candidate["freshness_rescued"] = True
                candidate["freshness_rescue_age_hours"] = round(age / 3600.0, 2)
                kept.append(candidate)
                print(f"V13 FRESHNESS RESCUE: {category} | {age / 3600.0:.2f}h old | {candidate.get('title', '')}")
            else:
                print(f"V13 FRESHNESS DROP: {category} | {age / 3600.0:.2f}h old | {candidate.get('title', '')}")
        return kept
    main.collect_feed = rescued_collect_feed
    print(f"V13 FRESHNESS RESCUE ACTIVE: normal={NORMAL_WINDOW_MINUTES}m, critical_max={CRITICAL_RESCUE_MAX_HOURS}h")
