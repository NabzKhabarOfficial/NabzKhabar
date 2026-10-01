"""Final V13 editorial calibration patch.

Loaded before the V13 stack. It keeps the normal 30-minute freshness rule,
but broadens the *strictly consequential* rescue window and hard-rejects
routine local Iranian stories that have no national/global consequence.
"""
import re

import v13_freshness_rescue
import v13_intelligence

# Do not loosen ordinary freshness. Only consequential events can use this
# extended rescue window.
v13_freshness_rescue.CRITICAL_RESCUE_MAX_HOURS = 12

# Short Latin tokens (ai, us, meta, u.s.) must be word-bounded; otherwise
# "said", "business" or "metal" are misread as AI / United States / Meta.
CRITICAL_ACTORS = re.compile(r"(?:google|gemini|openai|anthropic|nvidia|microsoft|(?<![a-z])meta(?![a-z])|alphabet|elevenlabs|(?<![a-z])ai(?![a-z])|artificial intelligence|گوگل|جمنای|اوپن.?ای.?آی|آنتروپیک|انویدیا|مایکروسافت|متا|هوش مصنوعی)", re.I)
CRITICAL_ACTIONS = re.compile(r"(?:launch(?:es|ed)?|release(?:s|d)?|unveil(?:s|ed)?|valuation|valued|funding|funded|raised|doubles|regulation|regulated|banned|approved|acquired|acquisition|outage|disrupt(?:s|ed)?|رونمایی|عرضه|ارزش.?گذاری|تأمین مالی|سرمایه.?گذاری|معرفی|مقررات|ممنوع|تصویب|تملک|اختلال)", re.I)
CRITICAL_GEOPOLITICAL = re.compile(r"(?:iran|israel|russia|ukraine|(?<![a-z])us(?![a-z])|(?<![a-z])u\.s\.|china|nato|united nations|trump|president|prime minister|اسرائیل|روسیه|اوکراین|آمریکا|چین|ناتو|سازمان ملل|ترامپ|رئیس.?جمهور|نخست.?وزیر)", re.I)
CRITICAL_STRATEGIC = re.compile(r"(?:war|attack|strike|missile|drone|conflict|ceasefire|sanction|nuclear|military|outage|shutdown|tariff|airspace|flight|جنگ|حمله|موشک|پهپاد|درگیری|آتش.?بس|تحریم|هسته.?ای|نظامی|اختلال|تعرفه|حریم هوایی|پرواز)", re.I)

_original_critical = v13_freshness_rescue._is_critical


def _title_is_major_global_event(title):
    title = str(title or "")
    return bool(
        (CRITICAL_ACTORS.search(title) and CRITICAL_ACTIONS.search(title))
        or (CRITICAL_GEOPOLITICAL.search(title) and CRITICAL_STRATEGIC.search(title))
    )


def _critical_with_major_global_events(candidate):
    if _original_critical(candidate):
        return True
    return _title_is_major_global_event(candidate.get("title", ""))

v13_freshness_rescue._is_critical = _critical_with_major_global_events

# Editorial quality: local Iranian routine must not compete with global/national
# consequential news merely because generic words such as "program", "growth",
# "project", "health", or "price" inflate the event score.
_original_publishable = v13_intelligence.is_publishable

LOCAL_MARKERS = (
    "پارسیان", "عنبرآباد", "شیروان", "توران", "سمنان", "خراسان رضوی", "خراسان",
    "آستارا", "زنجان", "لوندویل", "سنندج", "هرمزگان", "فارس", "کرمان",
    "شهرستان", "فرمانداری", "استاندار", "شهرداری", "شورای شهر", "دهیاری",
    "local", "county", "municipality", "mayor", "district",
)
LOCAL_ROUTINE = (
    "پارکینگ", "افتتاح", "جشنواره", "گرامیداشت", "مراسم", "فرهنگ", "سرمایه گذاری در",
    "کشاورزی", "مدرسه", "دانش آموز", "دانش‌آموز", "ورزش دانش آموزی", "گردشگری",
    "آسفالت", "ترافیک", "راهکار", "ترویج", "پرونده شهری", "پروژه عمرانی", "پروژه شهری",
    "پارک", "تندیس", "مجسمه", "یادمان", "مراقبت سالمندان", "تغذیه کودک",
)
NATIONAL_SIGNALS = (
    "کشوری", "سراسری", "ملی", "دولت", "مجلس", "بانک مرکزی", "وزارت", "رئیس جمهور",
    "رئیس‌جمهور", "تحریم", "قانون", "تصویب", "ابلاغ", "ممنوعیت", "نرخ بهره", "تورم",
    "نفت", "گاز", "اینترنت کشور", "شبکه ملی", "اختلال گسترده", "قطعی گسترده",
    "جنگ", "حمله", "موشک", "ترور", "زلزله", "سیل", "آتش‌سوزی", "کشته", "زخمی",
    "هوش مصنوعی", "تراشه", "امنیت سایبری", "میلیارد", "تحریم",
)

def _routine_local(title):
    low = str(title or "").lower()
    if not any(x.lower() in low for x in LOCAL_MARKERS):
        return False
    if not any(x.lower() in low for x in LOCAL_ROUTINE):
        return False
    return not any(x.lower() in low for x in NATIONAL_SIGNALS)

def _publishable_with_editorial_guard(main, candidate):
    title = str(candidate.get("title", "") or "")
    if _routine_local(title):
        return False, 0, "local-routine-final-gate"
    return _original_publishable(main, candidate)

v13_intelligence.is_publishable = _publishable_with_editorial_guard

print("V13 EDITORIAL FINAL PATCH: freshness=12h consequential rescue; local-routine final gate=active", flush=True)
