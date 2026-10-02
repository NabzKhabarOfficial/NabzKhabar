"""NABZ V13 — post design layer.

Gives every news post the NABZ signature look without touching the news
engine:

* Caption layout: urgency/category tag, bold title, one-line lead, details
  in a tap-to-expand quote, the NABZ pulse meter, topical hashtags and the
  channel link footer. No source is ever mentioned.
* Telegram formatting is sent as message *entities* (never parse_mode), so no
  text escaping is needed and a rejected style can fall back to plain text.
* No inline button (removed at the owner's request); a one-time cleanup
  strips the join button from the few posts that already carried it.
* News card: title rendered on the photo over a dark gradient, red NABZ pulse
  bar and urgency badge. Any failure falls back to the classic watermark.

Everything here is fail-safe: if a step fails, the post goes out exactly as it
would have before this layer existed.
"""

import json
import os
import re
import shutil
import tempfile
import time

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps, features

CHANNEL_URL = "https://t.me/NabzKhabarOfficial"
SHORT_URL = "t.me/NabzKhabarOfficial"
HANDLE = "@NabzKhabarOfficial"
BRAND_FA = "نبض خبر"
FONT_PATH = "Vazirmatn-Bold.ttf"
BUTTON_TEXT = "💓 عضویت در نبض خبر"
ACCENT = (229, 28, 45)
JOIN_BUTTON = False  # owner asked to remove the button under posts
CLEANUP_FLAG = "_join_button_cleanup_done"  # persisted in ai_model_health.json
CLEANUP_LOOKBACK = 60
MAX_CAPTION = 980  # below content_enhancer's 1000-char cut, so it never trims us

_CURRENT = {"candidate": None, "blocked": ""}
_PLANS = []          # most recent caption plans (title, quote, header)
_UNBRANDED = set()   # photo paths whose branding is deferred to send time

# --------------------------------------------------------------------------
# Classification (deterministic, keyword based)
# --------------------------------------------------------------------------

IRAN_TERMS = (
    "ایران", "تهران", "سپاه", "خامنه", "پزشکیان", "عراقچی", "اصفهان",
    "مشهد", "تبریز", "شیراز", "خوزستان", "بندرعباس", "تنگه هرمز",
)
ECON_TERMS = (
    "دلار", "یورو", "طلا", "سکه", "بورس", "تورم", "نرخ بهره", "بانک مرکزی",
    "قیمت نفت", "بنزین", "اقتصاد", "تعرفه", "بازار", "ارز",
)
TECH_TERMS = (
    "هوش مصنوعی", "تراشه", "اپل", "گوگل", "مایکروسافت", "متا", "انویدیا",
    "سایبری", "اینترنت", "فناوری", "ماهواره", "ربات", "اسپیس ایکس",
)
SPORT_TERMS = ("فوتبال", "فینال", "جام جهانی", "المپیک", "لیگ", "تیم ملی")

CATEGORIES = (
    (IRAN_TERMS, "🇮🇷", "ایران"),
    (ECON_TERMS, "💰", "اقتصاد"),
    (TECH_TERMS, "💻", "فناوری"),
    (SPORT_TERMS, "⚽", "ورزش"),
)

TOPIC_TAGS = (
    ("ایران", "#ایران"), ("اسرائیل", "#اسرائیل"), ("نتانیاهو", "#اسرائیل"),
    ("آمریکا", "#آمریکا"), ("ترامپ", "#ترامپ"), ("روسیه", "#روسیه"),
    ("پوتین", "#روسیه"), ("اوکراین", "#اوکراین"), ("غزه", "#غزه"),
    ("لبنان", "#لبنان"), ("حزب الله", "#لبنان"), ("سوریه", "#سوریه"),
    ("عراق", "#عراق"), ("یمن", "#یمن"), ("عربستان", "#عربستان"),
    ("چین", "#چین"), ("ترکیه", "#ترکیه"), ("اروپا", "#اروپا"),
    ("ناتو", "#ناتو"), ("سازمان ملل", "#سازمان_ملل"), ("تنگه هرمز", "#تنگه_هرمز"),
    ("هسته ای", "#هسته_ای"), ("نفت", "#نفت"), ("دلار", "#دلار"), ("طلا", "#طلا"),
    ("هوش مصنوعی", "#هوش_مصنوعی"), ("زلزله", "#زلزله"), ("انتخابات", "#انتخابات"),
)

URGENT_WORDS = (
    "فوری", "حمله", "انفجار", "کشته", "زلزله", "جنگ", "موشک", "ترور",
    "سقوط", "آتش بس", "استعفا", "تحریم", "بمباران",
)


def _norm(value):
    value = str(value or "").replace("\u200c", " ").replace("ي", "ی").replace("ك", "ک")
    return re.sub(r"\s+", " ", value).strip()


BREAKING_WORDS = (
    "حمله", "انفجار", "کشته", "زلزله", "ترور", "سقوط هواپیما", "بمباران",
    "موشک", "استعفا", "آتش بس", "اعلام جنگ", "کودتا", "تیراندازی",
)
BREAKING_MAX_AGE_SECONDS = 90 * 60
NOT_BREAKING_WORDS = (
    "تشییع", "مراسم", "سالگرد", "یادبود", "بزرگداشت", "گرامیداشت", "هشدار", "تهدید",
    "احتمال", "سالروز", "خاطره", "روایت", "تحلیل", "یادداشت", "مصاحبه", "واکنش",
)
FOREIGN_TERMS = (
    "آمریکا", "ترامپ", "اسرائیل", "نتانیاهو", "روسیه", "پوتین", "اوکراین", "غزه",
    "کرانه باختری", "لبنان", "سوریه", "عراق", "یمن", "عربستان", "چین", "ترکیه", "اروپا",
    "آلمان", "فرانسه", "انگلیس", "بریتانیا", "ژاپن", "هند", "پاکستان", "افغانستان",
    "برزیل", "ونزوئلا", "مکزیک", "کانادا", "استرالیا", "مصر", "قطر", "امارات", "کره",
    "ناتو", "سازمان ملل", "اتحادیه اروپا", "آفریقا", "کامرون", "تایوان",
    "صهیونیست", "فلسطین", "حماس", "حزب الله", "تل آویو", "کرانه", "بغداد", "دمشق", "بیروت",
    "ریاض", "مسکو", "واشنگتن", "پکن", "لندن", "پاریس", "برلین", "کی یف", "سئول",
)
_FOREIGN_RE = re.compile(
    r"(?<![\u0600-\u06FF\w])(?:" + "|".join(re.escape(t) for t in FOREIGN_TERMS)
    + r")(?:ی|ها|ای)?(?![\u0600-\u06FF\w])")


def _age_seconds(candidate):
    try:
        value = candidate.get("age_seconds")
        return None if value is None else float(value)
    except Exception:
        return None


def classify(title, candidate=None):
    """Return (level 1..5, urgent flag, category emoji, category label).

    "فوری" is reserved for real breaking news: a hard-breaking event word in
    the title, a high editorial tier, and (when known) a fresh story.
    """
    text = _norm(title)
    candidate = candidate or {}
    try:
        tier = int(candidate.get("publication_tier") or 0)
        score = int(candidate.get("intelligence_score") or 0)
    except Exception:
        tier, score = 0, 0
    breaking_word = any(w in text for w in BREAKING_WORDS)
    age = _age_seconds(candidate)
    fresh = age is None or age <= BREAKING_MAX_AGE_SECONDS
    calm = any(w in text for w in NOT_BREAKING_WORDS)
    urgent = breaking_word and fresh and tier >= 3 and not calm

    if urgent:
        level = 5
    elif (tier >= 4 and score >= 12) or score >= 16:
        level = 4
    elif tier == 3:
        level = 3 + (1 if score >= 12 else 0)
    else:
        level = 3

    emoji, label = "🌍", "جهان"
    cat = _norm(candidate.get("category", ""))
    if candidate.get("_major_sports") or "ورزش" in cat:
        emoji, label = "⚽", "ورزش"
    elif any(t in text for t in IRAN_TERMS) or (
            "ایران" in cat and not _FOREIGN_RE.search(text)):
        emoji, label = "🇮🇷", "ایران"
    else:
        for terms, e, l in CATEGORIES:
            if any(t in text for t in terms):
                emoji, label = e, l
                break
    return level, urgent, emoji, label


def hashtags(title, limit=2):
    text = _norm(title)
    tags = []
    for word, tag in TOPIC_TAGS:
        if word in text and tag not in tags:
            tags.append(tag)
        if len(tags) >= limit:
            break
    return " ".join(tags)


# Topic tag: each post gets a label describing what the story is about,
# instead of generic "urgent"/"important" stamps (owner's request).
#
# Logic (in order):
#   1. Sports stories are always sports.
#   2. A *statement* (speaker prefix "X: ..." or a speech verb) only gets a
#      hard-news topic when it reports a concrete event (strong signal);
#      rhetoric and opinions get "🗣 موضع‌گیری".
#   3. Military needs a concrete military signal (attack, missile, deployment,
#      clash...). The bare word "جنگ"/"نظامی" alone is weak: it only counts
#      when nothing else describes the story.
TOPIC_SPORT = ("⚽", "ورزش")
TOPIC_STATEMENT = ("🗣", "موضع‌گیری")
TOPIC_DEFAULT = ("📰", "خبر")
MILITARY_STRONG = (
    "حمله کرد", "حمله به", "حملات", "حمله هوایی", "حمله موشکی", "حمله پهپادی", "موشک",
    "پهپاد", "بمباران", "ناو", "تفنگدار", "اعزام نیرو", "اعزام شد", "رزمایش", "پایگاه",
    "یورش", "شلیک", "عملیات نظامی", "جنگنده", "سرنگون",
    "رهگیری", "استقرار", "نیروی دریایی", "نیروی هوایی", "ترور", "کشته شد", "کشته شدند",
    "درگیری مسلحانه", "درگیری ها", "درگیری های",
)
MILITARY_WEAK = ("جنگ", "نظامی", "ارتش", "سپاه", "آتش بس")
# An explosion/crash at a military site is a military story, not an accident.
MILITARY_SITE = ("فرودگاه نظامی", "پایگاه نظامی", "پایگاه هوایی", "پادگان", "انبار مهمات",
                 "تاسیسات نظامی", "ناو", "مقر ")
ACCIDENT = ("انفجار", "آتش سوزی", "سقوط", "زلزله", "سیل", "تصادف", "مصدوم", "غرق",
            "ریزش", "طوفان", "حادثه")
# "Flood risk warning" is an alert, not an accident that happened.
WARNING = ("هشدار", "خطر احتمالی", "احتمال وقوع", "احتمال سیل", "پیش بینی", "آماده باش", "در معرض خطر")
HAPPENED = ("کشته", "جان باخت", "مصدوم", "زخمی", "خسارت", "رخ داد", "وقوع یافت", "ناپدید", "مفقود",
            "تخریب", "آواره", "محبوس", "نجات")
WEATHERISH = ("سیل", "طوفان", "باران", "بارش", "برف", "گرد و خاک", "زلزله")
TOPICS = (
    ("⚖️", "قضایی", ("دادگاه", "اعدام", "دیوان", "حکم", "محاکمه", "بازداشت", "زندان", "قوه قضاییه")),
    ("💰", "اقتصاد", ECON_TERMS + ("نفت", "صادرات", "واردات", "دیزل", "گازوئیل", "تجارت", "میلیارد")),
    ("💻", "فناوری", TECH_TERMS),
    ("🩺", "سلامت", ("بیماری", "واکسن", "ویروس", "بیمارستان", "سلامت", "دارو", "شیوع")),
    ("🌦", "آب و هوا", ("هواشناسی", "بارش", "باران", "برف", "گرما", "سرما", "خشکسالی")),
    ("🏛", "سیاست", ("وزیر", "سفارت", "سفیر", "دیپلماتیک", "مذاکره", "رئیس جمهور", "مجلس",
                     "انتخابات", "تحریم", "سازمان ملل", "دولت", "پارلمان", "نخست وزیر", "کنگره",
                     "قطعنامه", "توافق", "نظرسنجی", "مذاکرات", "گفتگو", "گفت و گو")),
)
_SPEAKER_PREFIX = re.compile(r"^[^:؛«»]{2,45}:\s")
SPEECH_VERBS = (
    "گفت", "اظهار کرد", "اظهار داشت", "تاکید کرد", "تأکید کرد", "خواستار", "ادعا کرد",
    "معتقد است", "واکنش", "هشدار داد", "تهدید کرد", "خطاب به", "افزود", "بیان کرد",
    "ادعا", "می گوید", "گفته است", "اعلام کرد", "مدعی شد", "سخنرانی", "خطبه",
)
RHETORIC = (
    "سردرگم", "ناکام", "توهم", "ذلت", "خواب", "رویا", "پشیمان", "زانو", "شکست خورده",
    "محکوم به شکست", "از پای نخواهد نشست", "عقب نشینی خواهد", "جرأت", "جرات", "تحقیر",
    "شکست خواهد", "مقاومت مردم", "دشمن", "استکبار",
)


def _has(text, words):
    return any(w in text for w in words)


_SPEECH_RE = re.compile(
    r"(?<![\u0600-\u06FF])(?:" + "|".join(re.escape(v) for v in SPEECH_VERBS) + r")(?![\u0600-\u06FF])")


def is_statement(title):
    text = _norm(title)
    return bool(_SPEAKER_PREFIX.search(text)) or bool(_SPEECH_RE.search(text))


def topic_of(title, label):
    text = _norm(title)
    if label == "ورزش":
        return TOPIC_SPORT
    if "نظرسنجی" in text:
        return "🏛", "سیاست"
    statement = is_statement(text)
    rhetoric = _has(text, RHETORIC)
    strong_mil = _has(text, MILITARY_STRONG)
    if statement and (rhetoric or not strong_mil):
        # A speech: name a hard topic only when it is clearly about one.
        if not rhetoric:
            for emoji, name, words in TOPICS:
                if _has(text, words):
                    return emoji, name
        return TOPIC_STATEMENT
    if _has(text, ACCIDENT) and _has(text, WARNING) and not _has(text, HAPPENED) and not strong_mil:
        return ("🌦", "آب و هوا") if _has(text, WEATHERISH) else ("⚠️", "هشدار")
    if _has(text, ACCIDENT) and not strong_mil and not _has(text, MILITARY_SITE):
        return "🚨", "حادثه"
    if strong_mil or (_has(text, ACCIDENT) and _has(text, MILITARY_SITE)):
        return "⚔️", "نظامی"
    for emoji, name, words in TOPICS:
        if _has(text, words):
            return emoji, name
    if _has(text, ACCIDENT):
        return "🚨", "حادثه"
    if _has(text, MILITARY_WEAK):
        return "⚔️", "نظامی"
    return TOPIC_DEFAULT


def header_line(level, urgent, emoji, label, title=""):
    t_emoji, t_name = topic_of(title, label)
    if label == "ورزش":
        return f"{t_emoji} {t_name}"
    return f"{emoji} {label} · {t_emoji} {t_name}"


def meter(level):
    level = max(1, min(5, int(level)))
    return "▰" * level + "▱" * (5 - level)


# --------------------------------------------------------------------------
# Caption
# --------------------------------------------------------------------------

# The remaining post rendering/transport code is unchanged from the previous
# deployed version. It is intentionally preserved in the repository.
