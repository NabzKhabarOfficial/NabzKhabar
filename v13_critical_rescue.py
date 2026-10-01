"""NABZ V13 critical editorial rescue.

A narrow safety net for consequential geopolitical headlines that can score low
because they describe diplomacy/roadmaps/agreements rather than casualties.
It runs before final policy publication, so it must never promote foreign-local
stories into the translation queue.
"""

import re
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

LOCAL_ROUTINE_MARKERS = (
    "شهرداری", "شهردار", "شورای شهر", "فرماندار", "فرمانداری", "بخشدار",
    "دهیاری", "امام جمعه", "تندیس", "مجسمه", "یادمان", "یادبود",
    "مراسم", "گرامیداشت", "افتتاح پروژه", "کلنگ زنی", "کلنگ‌زنی",
    "جشنواره", "نمایشگاه محلی", "همایش", "نشست خبری", "تجلیل",
    "مدیرکل", "اداره کل", "دانشگاه .* منصوب", "رئیس دانشگاه .* منصوب",
    "پارک", "بوستان", "میدان", "خیابان", "آسفالت", "روکش آسفالت",
    "آب و فاضلاب .* خبر", "قطعی آب .* شهرستان", "پروژه عمرانی",
    "local mayor", "mayor", "municipality", "city council", "governor",
    "municipal", "ceremony", "memorial", "statue", "monument", "festival",
)

LOCAL_PLACE_MARKERS = (
    "تهران", "مشهد", "اصفهان", "شیراز", "تبریز", "کرمان", "رشت", "اهواز",
    "قم", "یزد", "کرمانشاه", "همدان", "ارومیه", "سنندج", "زاهدان", "بیرجند",
    "ساری", "گرگان", "بوشهر", "بندرعباس", "اراک", "قزوین", "اردبیل",
    "خرم‌آباد", "خرم آباد", "ایلام", "زنجان", "کاشان", "دزفول", "آبادان",
)

NATIONAL_OR_GLOBAL_CONSEQUENCE = (
    "جنگ", "حمله", "موشک", "بمباران", "انفجار", "ترور", "کشته", "زخمی",
    "آتش‌بس", "آتش بس", "تحریم", "هسته‌ای", "هسته ای", "حمله سایبری",
    "قطعی اینترنت", "اختلال گسترده", "قطع گسترده", "بحران", "زلزله", "سیل",
    "سونامی", "طوفان", "هواپیما سقوط", "سقوط هواپیما", "نفت", "گاز", "بنزین",
    "تورم", "نرخ بهره", "قیمت نفت", "بانک مرکزی", "مجلس", "دولت", "رئیس جمهور",
    "قانون", "تصویب", "ممنوعیت", "تحریم", "توافق", "مذاکرات", "روابط ایران",
    "آمریکا", "اسرائیل", "روسیه", "اوکراین", "چین", "ناتو", "سازمان ملل",
    "هوش مصنوعی", "تراشه", "فناوری", "میلیارد", "میلیون",
    "attack", "strike", "missile", "bombing", "explosion", "killed", "wounded",
    "sanction", "ceasefire", "nuclear", "outage", "inflation", "interest rate",
    "oil", "gas", "government", "parliament", "president", "united nations",
    "artificial intelligence", "chip", "billion", "million",
)


def _norm(text):
    return re.sub(r"\s+", " ", str(text or "").replace("ي", "ی").replace("ك", "ک")).strip().lower()


def _local_routine_only(candidate):
    title = _norm(candidate.get("title", ""))
    body = _norm(" ".join(str(candidate.get(k, "") or "") for k in ("summary", "description")))
    text = title + " " + body[:1800]
    routine = any(
        (re.search(marker, title, re.I) if ".*" in marker else marker in title)
        for marker in LOCAL_ROUTINE_MARKERS
    )
    local_place = any(x in title for x in LOCAL_PLACE_MARKERS)
    # Routine local stories must not become "important" merely because they
    # mention broad words such as جنگ/دولت/میلیارد/فناوری. A mayoral quote
    # about the war is still local routine unless the headline contains a
    # concrete national-scale event.
    strong_local_event = (
        "کشته", "زخمی", "مفقود", "انفجار", "حمله موشکی", "حمله تروریستی",
        "موشک", "بمباران", "سقوط هواپیما", "زلزله", "سیل", "سونامی",
        "آتش‌سوزی", "آتش سوزی", "تخلیه", "قطعی گسترده", "اختلال گسترده",
        "قطع اینترنت", "حمله سایبری", "وضعیت اضطراری", "بحران ملی",
        "تحریم", "ممنوعیت سراسری", "قانون جدید", "تصویب قانون",
        "national emergency", "missile attack", "terrorist attack", "earthquake",
        "flood", "wildfire", "cyberattack", "nationwide outage",
    )
    strong_consequence = any(x in text for x in strong_local_event)
    if not routine:
        return False
    if local_place:
        return not strong_consequence
    return not strong_consequence


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
    for primary, partners in CRITICAL_PAIRS:
        if primary in title and any(p in title for p in partners):
            return True
    actors = (
        "trump", "putin", "zelensky", "netanyahu", "nato", "united nations",
        "united states", "washington", "canada", "ایران", "ترامپ", "پوتین",
        "زلنسکی", "نتانیاهو", "ناتو",
    )
    return any(a in title for a in actors) and action and not any(x in title for x in routine)


def install():
    original = v13_intelligence.is_publishable

    def wrapped(main, candidate):
        if _local_routine_only(candidate):
            print(
                f"V13 EDITORIAL QUALITY: rejected [local-routine-low-value] {candidate.get('title', '')}",
                flush=True,
            )
            return False, 0, "local-routine-low-value"

        if v13_policy_guard._foreign_local_only(candidate):
            if not v13_intelligence._high_impact_security_override(candidate):
                return False, 0, "foreign-local-preselection"

        ok, score, reason = original(main, candidate)
        if ok or not _critical_geopolitical(candidate):
            return ok, score, reason
        rescued_score = max(int(score or 0), v13_intelligence.MIN_EVENT_SCORE + 6)
        print(f"V13 CRITICAL EDITORIAL RESCUE: {candidate.get('title', '')}", flush=True)
        return True, rescued_score, "critical-geopolitical-rescue"

    v13_intelligence.is_publishable = wrapped
    print("V13 CRITICAL EDITORIAL RESCUE ACTIVE", flush=True)
