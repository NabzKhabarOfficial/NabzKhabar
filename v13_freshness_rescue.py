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


CONSEQUENTIAL_ACTIONS = (
    "approved", "passed", "banned", "sanctioned", "suspended", "halted",
    "closed", "reopened", "blocked", "restricted", "introduced", "signed",
    "ordered", "required", "raised", "cut", "increased", "decreased",
    "withdrew", "deployed", "launched", "released", "acquired", "merged",
    "resigned", "arrested", "charged", "ruled", "sued", "declared",
    "announced", "warned", "warns", "warn", "demanded", "pledged", "agreed", "rejects",
    "accepted", "rejected", "resume", "resumed", "delayed", "reviewed",
    "توافق", "توافق کرد", "تصویب", "ممنوع", "تحریم", "تعلیق", "تعلیق کرد",
    "متوقف", "متوقف کرد", "تعطیل", "بازگشایی", "محدود", "محدود کرد",
    "امضا", "امضا کرد", "دستور داد", "اعلام کرد", "هشدار داد", "خواستار",
    "افزایش", "کاهش", "افزایش داد", "کاهش داد", "لغو", "لغو کرد",
    "بازداشت", "محکوم", "تملک", "ادغام", "ازسرگیری", "از سر گرفت",
)

CONSEQUENTIAL_ACTORS = (
    "iran", "u.s.", "us", "united states", "trump", "white house",
    "china", "russia", "ukraine", "israel", "gaza", "nato", "european union",
    "eu", "united nations", "un general assembly", "congress", "government",
    "president", "prime minister", "parliament", "central bank", "fed", "ecb",
    "faa", "آمریکا", "ایران", "چین", "روسیه", "اوکراین", "اسرائیل",
    "غزه", "ناتو", "اتحادیه اروپا", "سازمان ملل", "مجلس", "دولت",
    "رئیس جمهور", "رئیس‌جمهور", "نخست وزیر", "بانک مرکزی",
)

CONSEQUENTIAL_TOPICS = (
    "tariff", "tariffs", "sanction", "sanctions", "ceasefire", "nuclear",
    "interest rate", "inflation", "oil", "gas", "outage", "shutdown",
    "telecom", "internet", "airport", "flight", "airspace", "shipping",
    "strait", "artificial intelligence", "ai", "chip", "technology",
    "تعرفه", "تحریم", "آتش بس", "آتش‌بس", "هسته‌ای", "نرخ بهره", "تورم",
    "نفت", "گاز", "قطعی", "اختلال", "مخابرات", "اینترنت", "فرودگاه",
    "پرواز", "حریم هوایی", "کشتیرانی", "تنگه", "هوش مصنوعی", "تراشه",
)

RESCUE_ROUTINE_EXCLUSIONS = (
    "opinion", "analysis", "commentary", "review", "explainer", "tutorial",
    "home purchase", "real estate", "celebrity", "lifestyle",
    "تحلیل", "دیدگاه", "نظر", "راهنما", "آموزشی", "خرید خانه", "ملک",
    "سلبریتی", "سبک زندگی",
)

def _contains_any(value, terms):
    value = str(value or "").lower()
    for term in terms:
        term = str(term or "").strip().lower()
        if not term:
            continue
        # Avoid substring false positives such as "war" in "Warriors".
        if re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", value, re.I):
            return True
        # Persian terms do not have the same ASCII word-boundary behavior.
        if any("\u0600" <= ch <= "\u06ff" for ch in term) and term in value:
            return True
    return False

def _is_critical(candidate):
    """Return True only for high-impact events or consequential world actions."""
    title = str(candidate.get("title", "") or "").lower()
    body = _text(candidate).lower()
    if not title:
        return False
    text = f"{title} {body[:4000]}"

    if _contains_any(title, RESCUE_ROUTINE_EXCLUSIONS):
        return False

    # Do not treat a topic word appearing twice (e.g. "جنگ" in a
    # commemorative/ceremonial story) as a breaking event. Rescue requires a
    # distinct concrete incident signal or a consequential action.
    rescue_concrete_events = (
        "کشته", "زخمی", "مفقود", "انفجار", "حمله", "حملات", "موشک", "بمباران",
        "سقوط", "زلزله", "سیل", "سونامی", "طوفان", "رانش", "آتش سوزی", "آتش‌سوزی",
        "ترور", "تخلیه", "قطعی", "اختلال", "تعلیق", "توقف", "ممنوع", "آتش بس", "آتش‌بس",
        "تحریم", "شلیک", "گروگان", "missile", "attack", "attacks", "strike", "bombing",
        "explosion", "earthquake", "flood", "storm", "typhoon", "hurricane", "tsunami",
        "landslide", "killed", "wounded", "missing", "crash", "shooting", "hostage",
        "evacuat", "outage", "suspended", "banned", "sanction", "sanctions", "coup",
    )
    rescue_symbolic_exclusions = (
        "تندیس", "مجسمه", "یادمان", "یادبود", "باغ موزه", "گرامیداشت", "مراسم",
        "statue", "memorial", "monument", "ceremony",
    )
    if _contains_any(title, rescue_symbolic_exclusions) and not _contains_any(
        title, rescue_concrete_events
    ):
        return False
    if _contains_any(title, CRITICAL_TERMS) and _contains_any(title, rescue_concrete_events):
        return True

    action_hit = _contains_any(title, CONSEQUENTIAL_ACTIONS)
    actor_or_topic_hit = (
        _contains_any(title, CONSEQUENTIAL_ACTORS)
        or _contains_any(title, CONSEQUENTIAL_TOPICS)
    )
    if action_hit and actor_or_topic_hit:
        return True

    diplomatic_actions = (
        "awaits response", "await response", "offers", "offer", "roadmap",
        "calls for", "calls on", "urges", "urge", "proposes", "proposal",
        "talks", "negotiations", "negotiation", "response",
        "در انتظار پاسخ", "پاسخ آمریکا", "پاسخ ایالات متحده", "نقشه راه",
        "پیشنهاد", "مذاکرات", "مذاکره", "خواستار", "درخواست",
    )
    diplomatic_topics = (
        "war", "conflict", "ceasefire", "sanctions", "nuclear", "military",
        "strait", "security", "crisis", "جنگ", "درگیری", "آتش بس", "آتش‌بس",
        "تحریم", "هسته‌ای", "نظامی", "تنگه", "امنیت", "بحران",
    )
    if (
        _contains_any(title, diplomatic_actions)
        and _contains_any(title, CONSEQUENTIAL_ACTORS)
        and _contains_any(text, diplomatic_topics)
    ):
        return True

    return False


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
        old_rescue_predicate = getattr(
            main, "is_important_news_rescue_candidate", None
        )
        try:
            main.FEED_COLLECTION_WINDOW_MINUTES = CRITICAL_RESCUE_MAX_HOURS * 60
            main.is_important_news_rescue_candidate = lambda title: True
            candidates = original_collect_feed(category, url, is_google=is_google)
        finally:
            main.FEED_COLLECTION_WINDOW_MINUTES = old_window
            if old_rescue_predicate is not None:
                main.is_important_news_rescue_candidate = old_rescue_predicate

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
