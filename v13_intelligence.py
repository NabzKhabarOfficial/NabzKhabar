"""NABZ V13 intelligence/stability layer.

This module is intentionally additive: it wraps the existing V13 runtime
without replacing the news engine or touching independent pipelines.
"""

import json
import os
import re
import time
from collections import Counter
from datetime import datetime, timezone

HEALTH_FILE = "v13_health.json"
REJECTED_NEWS_FILE = "v13_rejected_news.json"
MAX_REJECTED_NEWS_HISTORY = 500
MAX_NEWS_PER_RUN = 4
MIN_EVENT_SCORE = 7

HIGH_IMPACT = (
    "جنگ", "حمله", "موشک", "انفجار", "زلزله", "سیل", "آتش سوزی",
    "آتش‌سوزی", "سقوط هواپیما", "هواپیما سقوط", "کشته", "زخمی",
    "مفقود", "ترور", "آتش بس", "آتش‌بس", "تحریم", "هسته ای", "هسته‌ای",
    "قطعی اینترنت", "قطع اینترنت", "حمله سایبری", "بحران", "اضطراری",
    "فراخوان", "ممنوع", "ممنوعیت", "تعلیق", "توقف", "قطع برق", "قطع گاز",
    "کمبود سوخت", "افزایش قیمت", "کاهش قیمت", "تورم", "نرخ بهره",
    "بنزین", "نفت", "گاز", "هوش مصنوعی", "تراشه", "قهرمان", "فینال",
)

MEDIUM_IMPACT = (
    "قانون", "تصویب", "ابلاغ", "وزارت", "دولت", "رئیس جمهور", "رئیس‌جمهور",
    "مجلس", "بانک مرکزی", "دارو", "بیماری", "واکسین", "پژوهش", "ماهواره",
    "ربات", "شرکت", "اپل", "گوگل", "مایکروسافت", "متا", "انویدیا",
)

ACTION_TERMS = (
    "کشته", "زخمی", "مفقود", "بازداشت", "تخلیه", "متوقف", "تعلیق",
    "ممنوع", "محدود", "قطع", "بازگشت", "فراخوان", "لغو", "تصویب",
    "رد", "اجرا", "ابلاغ", "اعلام", "افزایش", "کاهش", "سقوط", "رشد",
    "جهش", "تحریم", "حمله", "انفجار", "آتش بس", "آتش‌بس",
)

ROUTINE = (
    "دیدار", "سفر", "مراسم", "نشست", "همایش", "گرامیداشت", "افتتاح",
    "واکنش", "اظهارات", "گفت", "گفت:", "تاکید کرد", "تأکید کرد",
    "تسلیت", "تبریک", "پیام", "قرار است", "برنامه دارد", "تصمیم دارد",
)

HIGH_IMPACT_SECURITY_SIGNALS = (
    "تهدید", "اولتیماتوم", "تهدید نظامی", "تهدید کرد", "حمله نظامی",
    "حمله هوایی", "حمله زمینی", "حمله دریایی", "حمله موشکی", "بمباران",
    "عملیات نظامی", "عملیات هوایی", "درگیری نظامی", "تشدید درگیری",
    "تشدید تنش", "تشدید حملات", "تنش نظامی", "پاسخ نظامی", "پاسخ تلافی",
    "تلافی", "شلیک", "آتش گشود", "هدف قرار داد", "هدف قرار دادن",
    "مورد حمله قرار گرفت", "مواضع نظامی", "پایگاه نظامی", "آماده باش",
    "آماده‌باش", "تحرک نظامی", "هشدار امنیتی", "حمله به", "درگیری",
    "تجاوز نظامی", "پرتابه", "طوفان", "تخلیه",
)

HIGH_IMPACT_ACTORS = (
    "ایران", "ترامپ", "آمریکا", "اسرائیل", "سوریه", "عراق", "لبنان",
    "فلسطین", "غزه", "یمن", "عربستان", "ترکیه", "روسیه", "اوکراین",
    "چین", "تایوان", "کره جنوبی", "کره شمالی", "ناتو", "بریتانیا",
    "فرانسه", "آلمان", "دونالد ترامپ", "پنتاگون", "کاخ سفید",
    "سپاه", "ارتش", "نیروی هوایی", "نیروی دریایی",
)

LOW_VALUE = (
    "تخفیف", "فروش ویژه", "قرعه کشی", "قرعه‌کشی", "استخدام", "فال",
    "طالع بینی", "تولد", "اینستاگرام", "چهره", "سلبریتی", "رپورتاژ",
    "تبلیغات", "تبلیغاتی", "مسابقه", "لایف استایل", "سبک زندگی",
    "اکران", "مستند", "رونمایی هنری", "کنسرت", "جشنواره فیلم",
)

IRAN_REGION_ENTITIES = (
    "ایران", "تهران", "خوزستان", "کردستان", "کرمان", "سیستان", "آذربایجان",
    "عراق", "سوریه", "لبنان", "فلسطین", "غزه", "اسرائیل", "ترکیه",
    "عربستان", "قطر", "امارات", "آمریکا", "روسیه", "اوکراین", "چین",
    "اروپا", "کره جنوبی", "کره شمالی",
)

GENERIC = {
    "خبر", "گزارش", "اعلام", "آخرین", "مهم", "جدید", "درباره", "مورد",
    "واکنش", "اظهارات", "تصمیم", "جزئیات",
}


def _norm(value):
    value = str(value or "").replace("ي", "ی").replace("ك", "ک")
    value = value.replace("\u200c", " ")
    return re.sub(r"\s+", " ", value).strip()


def _text(candidate):
    return _norm(" ".join(
        str(candidate.get(k, "") or "")
        for k in ("title", "summary", "description", "article_text")
    ))


def _source_host(main, candidate):
    url = candidate.get("resolved_link") or candidate.get("link") or ""
    try:
        return main.base_domain(main.get_hostname(url))
    except Exception:
        return ""


def source_reliability(main, candidate):
    quality = main.publisher_quality(
        candidate.get("resolved_link") or candidate.get("link") or ""
    )
    if quality >= 25:
        return 10
    if quality >= 15:
        return 8
    if quality >= 5:
        return 6
    if quality > 0:
        return 4
    return 2


def event_score(main, candidate):
    title = _norm(candidate.get("title", "")).lower()
    body = _text(candidate).lower()
    title_high = sum(x.lower() in title for x in HIGH_IMPACT)
    title_medium = sum(x.lower() in title for x in MEDIUM_IMPACT)
    actions = sum(x.lower() in title or x.lower() in body[:3000] for x in ACTION_TERMS)
    entities = sum(x.lower() in title for x in IRAN_REGION_ENTITIES)
    concrete = bool(re.search(
        r"(\d+[٫,.]?\d*\s*(?:نفر|درصد|درجه|میلیون|میلیارد|کیلومتر|دلار|یورو|تومان|سال|روز))"
        r"|(?:افزایش|کاهش|رشد|سقوط|جهش|قطع|تعلیق|ممنوع|کشته|زخمی|بازداشت|انفجار|حمله)",
        title + " " + body[:2500],
        re.I,
    ))
    routine = sum(x.lower() in title for x in ROUTINE)
    low = sum(x.lower() in title for x in LOW_VALUE)

    score = 0
    score += min(title_high * 5, 20)
    score += min(title_medium * 2, 4)
    score += min(actions * 2, 6)
    score += 1 if entities and actions else 0
    score += 2 if concrete else 0
    score += source_reliability(main, candidate) // 3
    score += 1 if candidate.get("cluster_size", 1) >= 2 else 0
    score -= min(routine * 2, 6)
    score -= min(low * 8, 16)
    return score


def _major_business_legal_override(candidate):
    title = _norm(candidate.get("title", "")).lower()
    event = any(x in title for x in (
        "ادغام", "ادغام شد", "تملک", "تصاحب", "خرید", "دعوی قضایی",
        "شکایت", "حل و فصل", "رقابت", "انحصار",
        "merger", "acquisition", "acquired", "lawsuit", "settlement", "antitrust",
    ))
    concrete = bool(re.search(
        r"(?:\$?\d[\d,.]*\s*(?:میلیارد|million|billion)|"
        r"میلیارد|میلیون|%|درصد|states|state|دادگاه|دادستان|regulator|regulators|"
        r"lawsuit|settlement|antitrust)",
        title,
        re.I,
    ))
    return event and concrete


def _global_consequential_override(candidate):
    """Allow consequential world news beyond disasters/casualties.

    This is deliberately conservative: a global political, legal, economic,
    diplomatic, technology, or infrastructure story needs an explicit action
    plus a strong actor/topic signal. Routine statements and meetings do not
    qualify.
    """
    title = _norm(candidate.get("title", "")).lower()
    body = _text(candidate).lower()
    text = title + " " + body[:3500]

    routine_exclusion = (
        "home purchase", "house purchase", "buys home", "buy home",
        "property purchase", "real estate", "lifestyle", "celebrity",
        "analysis", "opinion", "commentary", "could be a bubble",
        "product review", "how to", "tutorial", "explainer",
        "research paper", "researchers say", "study finds",
        "book-pirating", "pirating books", "personal life",
        "خرید خانه", "خرید منزل", "خانه خرید", "ملک", "سبک زندگی",
        "تحلیل", "دیدگاه", "نظر", "گزارش تحلیلی", "آموزشی",
        "راهنما", "پژوهش", "مطالعه نشان می‌دهد", "زندگی شخصی",
    )
    if any(x in title for x in routine_exclusion):
        return False

    # Routine sports/personality stories are not global consequential news.
    # Keep finals/titles/results elsewhere in the normal editorial pipeline,
    # but do not let a generic appointment/challenge/profile story bypass it.
    sports_routine = (
        "challenge as", "appointed as", "named as", "takes charge",
        "floundering", "struggles", "struggling", "could become",
        "set to become", "coach", "manager", "boss",
        "سرمربی", "مربی", "انتخاب شد", "منصوب شد", "چالش",
        "دچار مشکل", "در آستانه", "احتمالا", "احتمالاً",
    )
    if any(x in title for x in sports_routine):
        return False

    # Only concrete verbs/actions belong here. Broad topics (AI, government,
    # parliament, court, inflation, etc.) are deliberately NOT actions.
    actions = (
        "approved", "approves", "passed", "passes", "banned", "ban", "sanction",
        "sanctions", "blocked", "blocks", "suspended", "suspends", "resigned",
        "halted", "halts", "disrupted", "disruption", "ground stop", "stopped",
        "outage", "failed", "failure", "severed", "repaired", "restored",
        "arrested", "charged", "indicted", "ruled", "sued", "convicted",
        "signed", "signs", "declared", "orders", "ordered", "requires", "required",
        "restricts", "restricted", "introduces", "introduced", "implements",
        "implemented", "joined", "settlement", "acquired", "acquisition",
        "merged", "merger", "recalled", "recall", "guilty", "verdict", "raises",
        "cuts", "increased", "decreased", "withdraw", "withdrew", "deployed",
        "deploy", "launched", "launches", "released", "release", "closed",
        "opens", "opened", "calls on", "call for", "urges", "urge", "pledges",
        "pledged", "criticizes", "criticised", "warns", "warned", "demands",
        "demanded", "announces", "announced", "says", "said", "review", "reviews", "reviewed", "reconsider", "reconsiders", "reconsidered", "delays", "delayed", "resumes", "resumed",
        "تایید", "تأیید", "تصویب", "ممنوع", "تحریم", "بازداشت", "محکوم",
        "امضا", "امضا کرد", "اعلام کرد", "اعلام", "دستور داد", "محدود کرد",
        "محدودیت", "تعلیق", "تعلیق کرد", "توقف", "متوقف کرد", "لغو", "لغو کرد",
        "افزایش", "افزایش داد", "کاهش", "کاهش داد", "ادغام", "تملک",
        "عرضه کرد", "رونمایی کرد", "قطع شد", "مختل شد", "بازداشت شد",
        "خواستار", "هشدار داد", "هشدار", "محکوم کرد", "درخواست کرد",
        "درخواست", "انتقاد کرد", "انتقاد", "گفت", "بررسی", "بازبینی", "بازنگری", "تجدیدنظر", "به تعویق انداخت", "تعویق", "ازسرگیری", "از سر گرفت",
    )
    actors = (
        "us", "u.s.", "united states", "white house", "trump", "china", "russia",
        "ukraine", "israel", "iran", "european union", "eu", "nato", "uk",
        "britain", "france", "germany", "japan", "south korea", "north korea",
        "india", "australia", "saudi", "albanese", "un", "imf", "fed", "ecb", "congress",
        "supreme court", "government", "president", "prime minister", "parliament",
        "faa", "federal aviation administration", "airports", "flights", "air traffic",
        "telecom", "telecommunications", "fiber", "infrastructure", "verizon",
        "un general assembly", "united nations", "world leaders", "leaders",
        "ایران", "آمریکا", "چین", "روسیه", "اوکراین", "اسرائیل", "اتحادیه اروپا",
        "ناتو", "بریتانیا", "فرانسه", "آلمان", "ژاپن", "هند", "عربستان",
        "دولت", "رئیس جمهور", "رئیس‌جمهور", "مجلس", "دادگاه", "بانک مرکزی",
    )
    action_hit = any(x in title for x in actions)
    actor_hit = any(x in title for x in actors)
    topic_hit = any(x in title for x in (
        "sanction", "tariff", "interest rate", "inflation", "lawsuit", "antitrust",
        "merger", "acquisition", "ceasefire", "military", "nuclear", "outage",
        "artificial intelligence", "smartglasses", "chip", "ai governance", "ai safety",
        "ai safeguards", "human control", "human oversight", "هوش مصنوعی", "تحریم", "نرخ بهره",
        "پرواز", "فرودگاه", "هوانوردی", "اختلال مخابراتی", "قطعی مخابرات",
        "تورم", "دادگاه", "انحصار", "ادغام", "تملک", "آتش‌بس", "هسته‌ای",
        "اختلال گسترده", "قطع گسترده",
    ))
    concrete_topic = any(x in title for x in (
        "sanction", "sanctions", "tariff", "tariffs", "interest rate", "inflation",
        "lawsuit", "antitrust", "merger", "acquisition", "ceasefire", "nuclear",
        "convicted", "guilty", "verdict", "bombing", "terrorist attack",
        "outage", "shutdown", "disruption", "اختلال گسترده", "قطع گسترده",
        "تحریم", "نرخ بهره", "تورم", "دادگاه", "انحصار", "ادغام", "تملک",
        "محکوم", "مجرم شناخته شد", "حکم دادگاه", "بمب‌گذاری", "بمب گذاری",
        "حمله تروریستی", "آتش‌بس", "جنگ", "حمله", "درگیری", "تهدید",
    ))
    ai_concrete_action = any(x in title for x in (
        "regulation", "regulations", "regulated", "regulate", "banned", "ban",
        "approved", "approves", "launch", "launched", "released", "release",
        "acquired", "acquisition", "deal", "agreement", "safety", "safeguard",
        "governance", "outage", "shutdown", "rolls out", "rolled out",
        "مقررات", "قانون", "ممنوع", "تصویب", "عرضه", "رونمایی", "توافق",
        "تملک", "ادغام", "ایمنی", "امنیت", "حکمرانی", "قطعی", "اختلال",
    ))
    if topic_hit and not concrete_topic and not ai_concrete_action and not actor_hit:
        return False
    return action_hit and (actor_hit or concrete_topic or ai_concrete_action)


def _unga_breaking_override(candidate):
    """Protect substantive UN General Assembly breaking coverage from generic gates."""
    title = _norm(candidate.get("title", "")).lower()
    body = _text(candidate).lower()
    text = title + " " + body[:3500]
    anchors = (
        "un general assembly", "united nations general assembly", "unga",
        "general debate", "مجمع عمومی سازمان ملل", "مجمع عمومی", "مناظره عمومی",
    )
    if not any(x in text for x in anchors):
        return False
    substantive = (
        "war", "conflict", "attack", "strike", "iran", "israel", "gaza",
        "ukraine", "russia", "yemen", "sanctions", "nuclear", "ceasefire",
        "peace", "ai", "artificial intelligence", "climate", "pandemic",
        "reform", "security", "humanitarian", "threat", "warn", "warning",
        "calls for", "calls on", "urges", "demands", "announces", "pledges",
        "speech", "address", "remarks", "vows", "condemns",
        "جنگ", "درگیری", "حمله", "ایران", "اسرائیل", "غزه", "اوکراین",
        "روسیه", "یمن", "تحریم", "هسته‌ای", "آتش‌بس", "صلح", "هوش مصنوعی",
        "اقلیم", "همه‌گیری", "اصلاح", "امنیت", "بشردوستانه", "تهدید",
        "هشدار", "خواستار", "محکوم", "اعلام کرد", "سخنرانی", "اظهارات",
    )
    return any(x in text for x in substantive)

def _high_impact_security_override(candidate):
    title = _norm(candidate.get("title", "")).lower()

    # Ceremonies, memorials, federation/athlete remarks and routine visa
    # disputes are not security incidents merely because they mention a
    # martyr, a country, a military actor, or a security-related word.
    ceremonial_or_routine = (
        "تشییع", "تشییع پیکر", "مراسم", "یادبود", "گرامیداشت",
        "شهید گمنام", "دهکده فرشتگان", "فدراسیون کشتی", "کشتی گیر",
        "کشتی‌گیر", "کشتی گیران", "کشتی‌گیران",
        "روادید", "ویزا", "ویزای", "گردش مالی",
        "ceremony", "funeral", "memorial", "wrestler", "wrestling federation",
        "visa", "financial turnover",
    )
    if any(x in title for x in ceremonial_or_routine):
        return False

    # Sports headlines must not enter the security/crisis override merely
    # because they contain words such as "victory", "attack", or "stormy".
    # Keep the override for genuine public-safety incidents involving sports.
    sports_routine = (
        "کبدی", "فوتبال", "فوتسال", "والیبال", "بسکتبال", "تنیس",
        "کریکت", "هندبال", "دوومیدانی", "شنا", "بوکس", "کشتی",
        "جودو", "کاراته", "قهرمانی", "قهرمان", "مسابقه", "پیروزی",
        "شکست", "لیگ", "جام", "مدال", "تیم", "بازیکن",
        "kabaddi", "football", "futsal", "volleyball", "basketball",
        "tennis", "cricket", "handball", "athletics", "boxing",
        "wrestling", "judo", "karate", "championship", "champion",
        "match", "victory", "defeat", "league", "cup", "medal",
        "team", "player",
    )
    sports_public_safety = (
        "کشته", "جان باخت", "زخمی", "مجروح", "فوت", "مفقود",
        "انفجار", "تیراندازی", "حمله تروریستی", "حادثه مرگبار",
        "killed", "dead", "fatal", "wounded", "injured", "missing",
        "explosion", "shooting", "terrorist attack", "fatal crash",
    )
    if any(x in title for x in sports_routine) and not any(
        x in title for x in sports_public_safety
    ):
        return False

    # Weekly/recap/roundup pieces are not breaking-news events.
    recap_routine = (
        "weekly", "week in review", "weekly review", "roundup", "recap",
        "this week", "what happened this week", "مروری هفتگی", "مرور هفتگی",
        "جمع‌بندی هفتگی", "جمع بندی هفتگی", "گزارش هفتگی", "اخبار هفته",
        "مرور اخبار", "جمع‌بندی اخبار", "جمع بندی اخبار",
    )
    if any(x in title for x in recap_routine):
        return False

    # Historical retrospectives and commemorative pieces must not enter the
    # breaking-news security path merely because the old event was serious.
    historical_or_commemorative = (
        "مروری به", "مرور حمله", "مرور حادثه", "روایت حمله", "روایت حادثه",
        "به مناسبت", "به‌یاد", "به یاد", "سالگرد", "هشتمین سال", "هفتمین سال",
        "ششمین سال", "پنجمین سال", "چهارمین سال", "سومین سال", "دومین سال",
        "سال ۱۳۹۷", "سال ۱۳۹۶", "سال ۱۳۹۵", "سال ۱۳۹۴", "سال ۱۳۹۳",
        "سال ۱۳۹۲", "سال ۱۳۹۱", "سال ۱۳۹۰", "۱۳۹۷", "۱۳۹۶", "۱۳۹۵",
        "۱۳۹۴", "۱۳۹۳", "۱۳۹۲", "۱۳۹۱", "۱۳۹۰",
        "years ago", "anniversary", "in 2018", "in 2019", "in 2020",
        "retrospective", "remembering", "on this day",
    )
    if any(x in title for x in historical_or_commemorative):
        return False

    # A sports/personality accident is not a security incident unless the
    # headline itself contains a concrete mass-casualty or public-safety
    # signal. This keeps athlete crashes from bypassing editorial filtering.
    sports_personal_routine = (
        "ufc", "champion", "fighter", "strickland", "pereira",
        "footballer", "football player", "wrestler", "athlete",
        "ورزشکار", "قهرمان", "کشتی‌گیر", "کشتی گیر", "فوتبالیست",
    )
    sports_accident = (
        "crash", "accident", "حادثه", "تصادف", "سقوط",
    )
    if any(x in title for x in sports_personal_routine) and any(x in title for x in sports_accident):
        public_safety = any(x in title for x in (
            "killed", "dead", "deaths", "fatal", "fatalities", "wounded",
            "injured", "mass casualty", "کشته", "جان باخت", "فوت", "زخمی",
            "مجروح", "قربانی",
        ))
        if not public_safety:
            return False
    title_signals = sum(x.lower() in title for x in HIGH_IMPACT_SECURITY_SIGNALS)
    actor_hits = sum(x.lower() in title for x in HIGH_IMPACT_ACTORS)
    strong_topic = any(x.lower() in title for x in HIGH_IMPACT)
    disaster_topic = any(x.lower() in title for x in (
        "زلزله", "سیل", "طوفان", "سونامی", "رانش زمین", "آتش سوزی",
        "آتش‌سوزی", "تخلیه", "هواپیما", "کشتی", "نفتکش",
    ))
    english_event = any(x in title for x in (
        "attack", "strike", "missile", "bombing", "explosion", "earthquake",
        "flood", "storm", "typhoon", "tsunami", "evacuat", "escalat",
        "military", "threat", "wildfire", "landslide", "shooting",
        "crash", "wounded", "killed",
    ))
    if title_signals == 0 and not disaster_topic and not english_event:
        return False
    if disaster_topic or english_event:
        return True
    return strong_topic and (actor_hits > 0 or title_signals > 0)

def _publication_tier(candidate):
    """Classify editorial importance so routine warnings cannot displace major news."""
    title = _norm(candidate.get("title", "")).lower()
    body = _text(candidate).lower()
    security = _high_impact_security_override(candidate)
    major_business = _major_business_legal_override(candidate)
    global_consequential = _global_consequential_override(candidate)
    unga_breaking = _unga_breaking_override(candidate)
    critical = any(x.lower() in title for x in (
        "جنگ", "حمله", "حمله موشکی", "بمباران", "انفجار بزرگ", "زلزله",
        "سیل", "سونامی", "سقوط هواپیما", "کشته", "مفقود", "ترور",
        "آتش بس", "آتش‌بس", "تحریم", "قطع اینترنت", "حمله سایبری",
        "پرتابه", "نفتکش", "درگیری نظامی", "عملیات نظامی",
        "attack", "strike", "missile", "bombing", "explosion", "earthquake",
        "flood", "tsunami", "crash", "killed", "wounded", "tanker",
    ))
    major = any(x.lower() in title or x.lower() in body[:4000] for x in (
        "ادغام", "تملک", "تصاحب", "دعوی قضایی", "شکایت", "انحصار",
        "نرخ بهره", "تورم", "بانک مرکزی", "قیمت نفت", "کمبود سوخت",
        "اختلال گسترده", "قطع برق", "قطع گاز", "قانون", "تصویب", "ممنوعیت",
        "فراخوان", "major", "merger", "acquisition", "lawsuit", "antitrust",
        "interest rate", "inflation", "oil price",
    ))
    ai_major_action = any(x in title for x in (
        "regulation", "regulated", "banned", "ban", "approved", "launch", "launched",
        "released", "acquired", "acquisition", "agreement", "safety", "governance",
        "outage", "shutdown", "chips", "chip", "مقررات", "قانون", "ممنوع", "تصویب",
        "عرضه", "توافق", "تملک", "ادغام", "ایمنی", "حکمرانی", "قطعی", "اختلال",
    ))
    major = major or ai_major_action
    # Consequential world news gets the same protected queue position as
    # other breaking stories. It must never be displaced simply because its
    # impact is diplomatic, legal, economic, technological or infrastructural.
    if security or critical or global_consequential or unga_breaking:
        return 3
    if major_business or major:
        return 2
    return 1


def _invalid_publisher_endpoint(main, candidate):
    """Reject telemetry/asset endpoints that masquerade as news articles."""
    url = candidate.get("resolved_link") or candidate.get("link") or ""
    try:
        host = main.base_domain(main.get_hostname(url))
    except Exception:
        from urllib.parse import urlparse
        host = urlparse(url).netloc.lower().split(":")[0].removeprefix("www.")
    path = url.split(host, 1)[-1].lower() if host else url.lower()
    blocked_hosts = (
        "google-analytics.com", "analytics.google.com", "googletagmanager.com",
        "doubleclick.net", "googlesyndication.com", "googleadservices.com",
        "facebook.net", "connect.facebook.net", "pixel.facebook.com",
        "segment.io", "segment.com", "hotjar.com", "clarity.ms",
    )
    blocked_paths = (
        "/analytics.js", "/gtag/js", "/gtm.js", "/pixel", "/collect",
        "/beacon", "/tracking", "/track", "/events", "/analytics",
    )
    return (
        host in blocked_hosts
        or any(host.endswith("." + x) for x in blocked_hosts)
        or any(token in path for token in blocked_paths)
    )


def is_publishable(main, candidate):
    title = _norm(candidate.get("title", ""))
    if _invalid_publisher_endpoint(main, candidate):
        return False, 0, "invalid-publisher-endpoint"
    if len(title) < 12:
        return False, 0, "short-title"

    lower = title.lower()
    if any(x.lower() in lower for x in LOW_VALUE):
        return False, 0, "low-value"

    body = _text(candidate).lower()

    # Block metaphorical/routine uses of high-impact words (for example
    # "جنگ تکالیف") before they can trigger the security override.
    metaphorical_routine = (
        "تکلیف", "تکالیف", "مدرسه", "دانش آموز", "دانش‌آموز", "فرزند",
        "والد", "خانواده", "خانه", "آموزش", "آموزشی", "درس", "امتحان",
        "مدیریت زمان", "مهارت", "روانشناسی", "روان‌شناسی", "سبک زندگی",
        "زندگی روزمره", "ورزش", "مسابقه", "بازی", "سرگرمی",
        "homework", "school", "student", "parenting", "parent", "family",
        "education", "educational", "lesson", "exam", "self-help",
        "lifestyle", "everyday life", "sports", "game", "entertainment",
    )
    concrete_security_event = (
        "کشته", "زخمی", "مجروح", "مفقود", "انفجار", "بمباران", "موشک",
        "حمله", "درگیری", "تیراندازی", "ترور", "زلزله", "سیل", "سونامی",
        "طوفان", "تخلیه", "آتش سوزی", "آتش‌سوزی", "سقوط هواپیما",
        "attack", "strike", "missile", "bombing", "explosion", "shooting",
        "earthquake", "flood", "tsunami", "typhoon", "evacuation",
        "killed", "wounded", "missing", "crash",
    )
    if any(x in lower for x in metaphorical_routine) and not any(
        x in lower for x in concrete_security_event
    ):
        return False, 0, "routine-metaphorical-topic"

    has_event = any(x.lower() in lower or x.lower() in body[:3000] for x in HIGH_IMPACT + ACTION_TERMS)
    score = event_score(main, candidate)

    if _unga_breaking_override(candidate):
        score = max(event_score(main, candidate), MIN_EVENT_SCORE + 3)
        return True, score, "unga-breaking-override"

    score = event_score(main, candidate)
    if _high_impact_security_override(candidate):
        score = max(score, MIN_EVENT_SCORE + 2)
        return True, score, "high-impact-security-override"

    if _major_business_legal_override(candidate):
        score = max(score, MIN_EVENT_SCORE + 1)
        return True, score, "major-business-legal-override"

    if _global_consequential_override(candidate):
        score = max(score, MIN_EVENT_SCORE + 1)
        return True, score, "global-consequential-event"

    if not has_event:
        return False, 0, "no-concrete-event"

    # Routine statements/meetings/visits/ceremonies and personality reactions
    # are not important-news by themselves; require a concrete consequence.
    routine_statement = bool(re.search(
        r"(?:واکنش|اظهارات|گفت|تأکید|تاکید|دیدار|سفر|مراسم|گرامیداشت|تسلیت|تبریک|پیام|"
        r"responds|says|said|remarks|meeting|visit|ceremony|memorial|appointed|named as)",
        title, re.I,
    ))
    concrete_change = bool(re.search(
        r"(?:کشته|زخمی|مفقود|بازداشت|انفجار|زلزله|سیل|آتش.?سوزی|سقوط|حمله|موشک|"
        r"تحریم|آتش.?بس|تعلیق|ممنوع|قطع|اختلال|تصویب|ابلاغ|لغو|افزایش|کاهش|جهش|"
        r"قانون|نرخ بهره|تورم|تملک|ادغام|دعوی قضایی|شکایت|قهرمانی|فینال|رکورد|"
        r"attack|strike|missile|explosion|earthquake|flood|killed|wounded|arrested|"
        r"sanction|ceasefire|outage|approved|banned|suspended|merger|acquisition|lawsuit|final|champion|record)",
        title, re.I,
    ))
    if routine_statement and not concrete_change and not (
        _high_impact_security_override(candidate)
        or _global_consequential_override(candidate)
        or _major_business_legal_override(candidate)
        or _unga_breaking_override(candidate)
    ):
        return False, score, "routine-statement"

    if score < MIN_EVENT_SCORE:
        return False, score, "below-event-threshold"

    return True, score, "ok"


def _tokens(main, title):
    try:
        return set(main.story_tokens(title))
    except Exception:
        return {
            x for x in re.findall(r"[\w\u0600-\u06ff]+", _norm(title).lower())
            if len(x) > 2 and x not in GENERIC
        }


def same_event(main, a, b):
    if main.same_story(a, b):
        return True
    ta = _tokens(main, a.get("title", ""))
    tb = _tokens(main, b.get("title", ""))
    if not ta or not tb:
        return False
    common = ta & tb
    if len(common) < 3:
        return False
    ratio = len(common) / max(1, min(len(ta), len(tb)))
    nums_a = set(re.findall(r"\d+", main.normalize_digits(a.get("title", ""))))
    nums_b = set(re.findall(r"\d+", main.normalize_digits(b.get("title", ""))))
    shared_number = bool(nums_a & nums_b)
    return ratio >= 0.78 or (ratio >= 0.62 and shared_number)


def _dedup_events(main, candidates):
    groups = []
    for candidate in candidates:
        placed = False
        for group in groups:
            if same_event(main, candidate, group[0]):
                group.append(candidate)
                placed = True
                break
        if not placed:
            groups.append([candidate])

    selected = []
    for group in groups:
        best = max(
            group,
            key=lambda c: (
                # Preserve the upstream editorial priority when multiple
                # feeds describe the same event.  The previous implementation
                # preferred only event_score(), which could replace a genuinely
                # high-priority story with a lower-value local variant.
                int(c.get("importance", 0) or 0),
                int(c.get("intelligence_score", 0) or event_score(main, c)),
                _publication_tier(c),
                source_reliability(main, c),
                c.get("published_at") or datetime.min.replace(tzinfo=timezone.utc),
            ),
        )
        best["intelligence_event_cluster"] = len(group)
        selected.append(best)
    return selected


def _write_health(state):
    try:
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        with open(HEALTH_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        print(f"V13 HEALTH WRITE ERROR: {exc}", flush=True)


def _load_rejected_history():
    try:
        with open(REJECTED_NEWS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_rejected_history(history):
    try:
        history = history[-MAX_REJECTED_NEWS_HISTORY:]
        with open(REJECTED_NEWS_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        print(f"V13 REJECTED NEWS WRITE ERROR: {exc}", flush=True)


def _rejected_record(main, candidate, score, reason, stage="intelligence_filter"):
    title = _norm(candidate.get("title", ""))
    published_at = candidate.get("published_at")
    if hasattr(published_at, "isoformat"):
        published_at = published_at.isoformat()
    url = candidate.get("resolved_link") or candidate.get("link") or ""
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "title": title,
        "source": _source_host(main, candidate) or candidate.get("source", "") or "unknown",
        "category": candidate.get("category", ""),
        "published_at": published_at or "",
        "url": url,
        "age_seconds": candidate.get("age_seconds"),
        "intelligence_score": score,
        "reason": reason,
        "stage": stage,
        "high_impact_security_candidate": _high_impact_security_override(candidate),
        "major_business_legal_candidate": _major_business_legal_override(candidate),
    }


def install(main):
    original_collect = main.collect_candidates
    original_process = main.process_news
    original_strict_gate = getattr(main, "is_strictly_useful_news", None)
    strict_rejection_records = []

    if original_strict_gate is not None:
        def _intelligence_strict_gate(candidate):
            if _unga_breaking_override(candidate):
                print(
                    "V13 INTELLIGENCE: UNGA breaking override -> "
                    f"{candidate.get('title', '')}",
                    flush=True,
                )
                return True
            if _high_impact_security_override(candidate):
                print(
                    "V13 INTELLIGENCE: high-impact security override -> "
                    f"{candidate.get('title', '')}",
                    flush=True,
                )
                return True
            if _global_consequential_override(candidate):
                print(
                    "V13 INTELLIGENCE: global consequential override -> "
                    f"{candidate.get('title', '')}",
                    flush=True,
                )
                return True
            result = original_strict_gate(candidate)
            if not result:
                strict_rejection_records.append(
                    _rejected_record(
                        main, candidate, 0, "strict-pre-intelligence",
                        stage="strict_gate",
                    )
                )
            return result
        main.is_strictly_useful_news = _intelligence_strict_gate

    state = {
        "status": "starting",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "raw_candidates": 0,
        "strict_rejected": 0,
        "event_duplicates_removed": 0,
        "selected_for_publication": 0,
        "published": 0,
        "failed_publications": 0,
        "top_sources": {},
        "last_errors": [],
        "rejected_news_this_run": [],
        "selected_news_this_run": [],
        "publication_attempts": [],
    }

    def intelligent_collect(hash_history, title_history):
        candidates = original_collect(hash_history, title_history)
        state["raw_candidates"] = len(candidates)

        if strict_rejection_records:
            history = _load_rejected_history()
            history.extend(strict_rejection_records)
            _save_rejected_history(history)
            state["rejected_news_this_run"].extend(strict_rejection_records)
            strict_rejection_records.clear()

        filtered = []
        rejected = Counter()
        rejected_records = []
        evaluated = []

        for candidate in candidates:
            ok, score, reason = is_publishable(main, candidate)
            candidate["intelligence_score"] = score
            evaluated.append((candidate, ok, score, reason))
            if not ok:
                rejected[reason] += 1
                record = _rejected_record(main, candidate, score, reason)
                rejected_records.append(record)
                print(
                    f"V13 INTELLIGENCE: rejected [{reason}] "
                    f"{candidate.get('title', '')}",
                    flush=True,
                )
                continue
            candidate["importance"] = max(
                int(candidate.get("importance", 0) or 0),
                score,
            )
            filtered.append(candidate)

        state["strict_rejected"] = sum(rejected.values()) + len(state["rejected_news_this_run"])
        state["rejected_news_this_run"] = rejected_records

        history = _load_rejected_history()
        history.extend(rejected_records)
        _save_rejected_history(history)

        publishable_before_dedup = sum(1 for _, ok, _, _ in evaluated if ok)
        filtered = _dedup_events(main, filtered)
        state["event_duplicates_removed"] = max(
            0, publishable_before_dedup - len(filtered)
        )

        # Editorial priority gate:
        # Never fill the channel with routine/low-tier stories when a major
        # or critical event is available. If no major story exists at all,
        # publish nothing rather than substituting a weak story.
        for candidate in filtered:
            candidate["publication_tier"] = _publication_tier(candidate)

        # Editorial ranking is deliberately tier-first: a critical or
        # consequential event must be considered before an ordinary incident.
        # Within the same tier, retain upstream priority and intelligence
        # score so important breaking stories are not displaced by routine
        # local accidents simply because they contain a strong event keyword.
        filtered.sort(
            key=lambda c: (
                int(c.get("publication_tier", 1) or 1),
                int(c.get("intelligence_score", 0) or 0),
                int(c.get("importance", 0) or 0),
                source_reliability(main, c),
                c.get("published_at") or datetime.min.replace(tzinfo=timezone.utc),
            ),
            reverse=True,
        )

        highest_tier = max(
            (int(c.get("publication_tier", 1) or 1) for c in filtered),
            default=0,
        )
        if highest_tier >= 3:
            # Keep tier-2 consequential stories in the fallback queue. A
            # critical story can fail later (duplicate, translation, media);
            # the next major story must still get a chance in the same run.
            eligible = [c for c in filtered if int(c.get("publication_tier", 1) or 1) >= 2]
        elif highest_tier >= 2:
            eligible = [c for c in filtered if int(c.get("publication_tier", 1) or 1) >= 2]
        else:
            eligible = []

        # Pass several strong candidates forward so downstream failures
        # (translation, duplicate validation, media, publication) have a
        # fallback instead of turning the whole run into Published: 0.
        selected = []
        families = Counter()
        for candidate in eligible:
            family = main.category_family(candidate.get("category", ""))
            if families[family] >= 2 and candidate.get("intelligence_score", 0) < 12:
                continue
            selected.append(candidate)
            families[family] += 1
            if len(selected) >= MAX_NEWS_PER_RUN:
                break

        state["selected_for_publication"] = len(selected)
        state["top_sources"] = dict(Counter(
            _source_host(main, x) or "unknown" for x in selected
        ))
        state["status"] = "collect-complete"
        _write_health(state)

        print(
            f"V13 INTELLIGENCE: {len(candidates)} candidates -> "
            f"{len(filtered)} event-valid -> {len(selected)} selected",
            flush=True,
        )
        return selected

    def tracked_process(candidate, hash_history, title_history):
        attempt = {
            "title": _norm(candidate.get("title", "")),
            "source": _source_host(main, candidate) or candidate.get("source", "") or "unknown",
            "url": candidate.get("resolved_link") or candidate.get("link") or "",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "result": "unknown",
            "error": "",
        }
        try:
            result = original_process(candidate, hash_history, title_history)
            if result:
                state["published"] += 1
                attempt["result"] = "published"
            elif candidate.get("publication_status") == "skipped_duplicate":
                attempt["result"] = "skipped_duplicate"
                attempt["reason"] = "recent-semantic-history"
            else:
                state["failed_publications"] += 1
                attempt["result"] = "failed"
            state["publication_attempts"].append(attempt)
            state["publication_attempts"] = state["publication_attempts"][-10:]
            _write_health(state)
            return result
        except Exception as exc:
            state["failed_publications"] += 1
            attempt["result"] = "exception"
            attempt["error"] = str(exc)[:500]
            state["publication_attempts"].append(attempt)
            state["publication_attempts"] = state["publication_attempts"][-10:]
            state["last_errors"].append(str(exc)[:300])
            state["last_errors"] = state["last_errors"][-5:]
            _write_health(state)
            raise

    main.collect_candidates = intelligent_collect
    main.process_news = tracked_process

    original_main = main.main

    def tracked_main():
        started = time.time()
        state["status"] = "running"
        _write_health(state)
        try:
            result = original_main()
            state["status"] = "success"
            state["runtime_seconds"] = round(time.time() - started, 1)
            _write_health(state)
            return result
        except Exception as exc:
            state["status"] = "failed"
            state["runtime_seconds"] = round(time.time() - started, 1)
            state["last_errors"].append(str(exc)[:300])
            state["last_errors"] = state["last_errors"][-5:]
            _write_health(state)
            raise

    main.main = tracked_main
    print(
        "V13 INTELLIGENCE ACTIVE: event scoring + semantic event dedup + "
        f"source reliability + max {MAX_NEWS_PER_RUN} news/run + health monitor "
        "+ rejected-news audit",
        flush=True,
    )
