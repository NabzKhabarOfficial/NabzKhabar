import os
import re
import io
import json
import time
import hashlib
import subprocess
from datetime import datetime, timezone, timedelta
from urllib.parse import (
    urlparse,
    quote_plus,
    urljoin,
    parse_qsl,
    urlencode,
    urlunparse,
)

import requests

import feedparser
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont


# ============================================================
# NABZ KHABAR BOT v11
# STRONG SEMANTIC DEDUPLICATION
# GOOGLE NEWS DISCOVERY
# GEMINI + VIDEO + PHOTO + TEXT + WATERMARK
# ============================================================

print("=" * 64)
print("NABZ KHABAR BOT v11")
print("STRONG DUPLICATE PROTECTION + FRESH NEWS")
print("GEMINI + GOOGLE NEWS + VIDEO + PHOTO")
print("WATERMARK + SOURCE QUALITY")
print("=" * 64)


# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
AI_API_KEY = os.getenv("AI_API_KEY", "").strip()

CHANNEL_ID = "@NabzKhabarOfficial"

# Free-tier, high-volume model. Override with GEMINI_MODEL if needed.
# Google currently lists Gemini 3.1 Flash-Lite as free-of-charge on the
# standard Gemini API tier. Free tier is quota-limited, not literally unlimited.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

REQUEST_TIMEOUT = 20
ARTICLE_TIMEOUT = 25

MAX_VIDEO_MB = 49
MAX_IMAGE_MB = 12

# The normal publication freshness contract is 30 minutes. Critical-news
# rescue temporarily expands feed collection to 6 hours in the dedicated
# freshness-rescue layer; routine stories never use that wider window.
FEED_COLLECTION_WINDOW_MINUTES = 30

# Important stories may be older than the normal feed window when RSS delivery is delayed.
# Rescue only high-impact events; routine foreign-local stories remain blocked.
IMPORTANT_NEWS_RESCUE_MAX_AGE_MINUTES = 360

# Normal publication freshness is 30 minutes. Do not silently widen this
# value: delayed high-impact stories are handled only by v13_freshness_rescue.
MAX_NEWS_AGE_HOURS = 0.5

# Semantic duplicate protection window.
SEMANTIC_HISTORY_DAYS = 7

HISTORY_FILE = "sent_news.txt"

WATERMARK_TEXT = "نبض خبر | NABZ"

MAX_OUTPUT_IMAGE_WIDTH = 1600
MAX_OUTPUT_IMAGE_HEIGHT = 1600


# ============================================================
# VALIDATION
# ============================================================

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")

print(f"Gemini enabled: {bool(AI_API_KEY)}")
print(f"Gemini model: {GEMINI_MODEL}")
print(f"Freshness window: {MAX_NEWS_AGE_HOURS}h")
print(f"Important-news rescue window: {IMPORTANT_NEWS_RESCUE_MAX_AGE_MINUTES}m")
print(f"Feed discovery window: {FEED_COLLECTION_WINDOW_MINUTES}m")
print(f"Semantic history: {SEMANTIC_HISTORY_DAYS} days")


# ============================================================
# TEXT HELPERS
# ============================================================

def normalize_space(text):
    if not text:
        return ""

    text = str(text)

    text = text.replace("\u200c", " ")
    text = text.replace("\u200f", " ")
    text = text.replace("\u200e", " ")
    text = text.replace("\xa0", " ")

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_digits(text):
    if not text:
        return ""

    table = str.maketrans(
        "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
        "01234567890123456789"
    )

    return text.translate(table)


def clean_url(url):
    if not url:
        return ""

    return str(url).strip()


def get_hostname(url):
    try:
        return urlparse(url).netloc.lower().split(":")[0]
    except Exception:
        return ""


def base_domain(host):
    host = (host or "").lower()

    if host.startswith("www."):
        host = host[4:]

    return host


# ============================================================
# LANGUAGE HELPERS
# ============================================================

def _persian_ratio(text):
    """Return the share of alphabetic characters that are Persian/Arabic."""
    letters = re.findall(r"[A-Za-z\u0600-\u06ff]", str(text or ""))
    if not letters:
        return 1.0
    return sum("\u0600" <= ch <= "\u06ff" for ch in letters) / len(letters)


class SkipForeignStory(Exception):
    """Signal that a candidate must be skipped without failing the whole run."""
    pass


# ============================================================
# URL CANONICALIZATION
# ============================================================

TRACKING_PARAMETERS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_name",
    "gclid",
    "fbclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "referrer",
    "source",
    "output",
}


def canonicalize_url(url):
    """
    Removes tracking parameters so the same article with
    different tracking links produces the same history key.
    """

    if not url:
        return ""

    try:
        parsed = urlparse(
            clean_url(url)
        )

        scheme = (
            parsed.scheme
            or "https"
        ).lower()

        host = (
            parsed.netloc
            or ""
        ).lower()

        if host.startswith("www."):
            host = host[4:]

        path = parsed.path or "/"

        # Remove trailing slash except root.
        if path != "/":
            path = path.rstrip("/")

        query_items = parse_qsl(
            parsed.query,
            keep_blank_values=True
        )

        filtered = []

        for key, value in query_items:

            key_lower = key.lower()

            if key_lower in TRACKING_PARAMETERS:
                continue

            if key_lower.startswith("utm_"):
                continue

            filtered.append(
                (key, value)
            )

        filtered.sort()

        query = urlencode(
            filtered,
            doseq=True
        )

        return urlunparse(
            (
                scheme,
                host,
                path,
                "",
                query,
                ""
            )
        )

    except Exception:
        return clean_url(url)


# ============================================================
# HOST FILTERS
# ============================================================

def is_google_host(url):
    host = get_hostname(url)

    return (
        host == "news.google.com"
        or host == "google.com"
        or host.endswith(".google.com")
        or "googleusercontent.com" in host
        or "gstatic.com" in host
    )


def is_social_host(url):
    host = get_hostname(url)

    social_hosts = (
        "facebook.com",
        "fb.com",
        "fbcdn.net",
        "x.com",
        "twitter.com",
        "twimg.com",
        "youtube.com",
        "youtu.be",
        "tiktok.com",
        "instagram.com",
        "telegram.me",
        "t.me"
    )

    return any(
        host == x or host.endswith("." + x)
        for x in social_hosts
    )


def is_bad_media_url(url):
    if not url:
        return True

    host = get_hostname(url)

    bad_hosts = (
        "googleusercontent.com",
        "gstatic.com",
        "google.com",
        "facebook.com",
        "fbcdn.net",
        "twitter.com",
        "twimg.com",
        "x.com"
    )

    return any(
        host == x or host.endswith("." + x)
        for x in bad_hosts
    )


def looks_like_video_url(url):
    if not url:
        return False

    value = url.lower().split("?")[0]

    return value.endswith(
        (
            ".mp4",
            ".webm",
            ".mov",
            ".m4v"
        )
    )


def is_hls_url(url):
    if not url:
        return False

    return ".m3u8" in url.lower()


# ============================================================
# GOOGLE NEWS
# ============================================================

GOOGLE_NEWS_BASE = "https://news.google.com/rss"
GOOGLE_HL = "fa"
GOOGLE_GL = "IR"
GOOGLE_CEID = "IR:fa"


def google_news_search_url(query):
    query = normalize_space(query)

    return (
        f"{GOOGLE_NEWS_BASE}/search?"
        f"q={quote_plus(query)}"
        f"&hl={GOOGLE_HL}"
        f"&gl={GOOGLE_GL}"
        f"&ceid={GOOGLE_CEID}"
        f"&when={FEED_COLLECTION_WINDOW_MINUTES}m"
    )


# ============================================================
# DIRECT RSS
# ============================================================

DIRECT_RSS_FEEDS = [
    # Iranian direct RSS: keep exactly two sources to reduce polling and
    # duplicate candidates while preserving broad domestic coverage.
    ("ایران", "https://www.yjc.ir/fa/rss/allnews"),
    ("ایران", "https://www.irna.ir/rss"),

    # International / specialist RSS sources remain available below.
    ("هوش مصنوعی", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("هوش مصنوعی", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ("فناوری", "https://feeds.arstechnica.com/arstechnica/technology-lab"),
    ("هوش مصنوعی", "https://www.technologyreview.com/topic/artificial-intelligence/feed/"),
    ("هوش مصنوعی", "https://venturebeat.com/category/ai/feed/"),
    ("هوش مصنوعی", "https://blogs.nvidia.com/feed/"),
    ("ورزش", "https://feeds.bbci.co.uk/sport/rss.xml"),
    ("ورزش", "https://www.espn.com/espn/rss/news"),
    ("جهان", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("فناوری", "https://www.engadget.com/rss.xml"),
]


# ============================================================
# GOOGLE NEWS DISCOVERY
# ============================================================

GOOGLE_NEWS_FEEDS = [
    # Core Iranian / breaking coverage
    ("ایران", google_news_search_url("ایران")),
    ("خبر فوری", google_news_search_url('"خبر فوری" ایران')),
    ("خبر مهم", google_news_search_url('"خبر مهم" ایران')),
    ("حوادث", google_news_search_url("حادثه انفجار تصادف سقوط آتش سوزی ایران")),
    ("اقتصاد", google_news_search_url("اقتصاد ایران")),
    ("بازار", google_news_search_url("دلار طلا سکه بورس ایران")),
    ("جنگ و بحران", google_news_search_url("جنگ بحران درگیری حمله آتش بس")),
    ("جهان", google_news_search_url("مهمترین اخبار جهان بین الملل")),
    ("ایران و جهان", google_news_search_url("ایران آمریکا اروپا روسیه چین اسرائیل")),
    ("جامعه", google_news_search_url("جامعه اجتماعی ایران")),
    ("سلامت", google_news_search_url("سلامت پزشکی بیمارستان دارو")),
    ("علم", google_news_search_url("علم دانش پژوهش فضا پزشکی")),
    ("فرهنگ", google_news_search_url("فرهنگ هنر ادبیات")),
    ("سینما", google_news_search_url("سینما فیلم سریال تلویزیون")),
    ("فیلم و سریال", google_news_search_url("site:variety.com film OR series OR television OR streaming")),

    # AI / technology: intentionally split so one broad query does not
    # become the bottleneck for the entire technology category.
    ("هوش مصنوعی", google_news_search_url("هوش مصنوعی AI")),
    ("هوش مصنوعی", google_news_search_url("OpenAI ChatGPT")),
    ("هوش مصنوعی", google_news_search_url("Google Gemini DeepMind")),
    ("هوش مصنوعی", google_news_search_url("Anthropic Claude")),
    ("هوش مصنوعی", google_news_search_url("NVIDIA AI GPU")),
    ("هوش مصنوعی", google_news_search_url("مدل زبانی LLM هوش مصنوعی مولد")),
    ("رباتیک", google_news_search_url("رباتیک ربات انسان نما robotics")),
    ("فناوری", google_news_search_url("فناوری تکنولوژی")),
    ("فناوری", google_news_search_url("Microsoft Apple Google Meta Amazon")),
    ("فناوری", google_news_search_url("تراشه پردازنده نیمه رسانا semiconductor chip")),
    ("فناوری", google_news_search_url("امنیت سایبری هک حمله سایبری")),
    ("موبایل", google_news_search_url("موبایل گوشی iPhone Samsung Pixel")),
    ("اینترنت", google_news_search_url("اینترنت شبکه ارتباطات 5G")),

    # World / geopolitics: separate regional queries increase coverage
    # while the semantic deduplicator collapses reports about one event.
    ("جهان", google_news_search_url("آمریکا کاخ سفید کنگره ترامپ")),
    ("جهان", google_news_search_url("اروپا اتحادیه اروپا بریتانیا فرانسه آلمان")),
    ("جهان", google_news_search_url("روسیه اوکراین جنگ")),
    ("جهان", google_news_search_url("خاورمیانه اسرائیل فلسطین لبنان غزه")),
    ("جهان", google_news_search_url("ایران آمریکا مذاکرات تحریم")),
    ("جهان", google_news_search_url("چین تایوان آسیا ژاپن کره جنوبی")),
    ("جهان", google_news_search_url("هند پاکستان افغانستان")),
    ("جهان", google_news_search_url("آفریقا آمریکای لاتین جهان")),

    # Economy / energy / markets
    ("اقتصاد", google_news_search_url("تورم نرخ بهره اقتصاد جهانی")),
    ("اقتصاد", google_news_search_url("بانک مرکزی فدرال رزرو ECB")),
    ("نفت و انرژی", google_news_search_url("نفت گاز انرژی اوپک")),
    ("بورس", google_news_search_url("بورس سهام بازارهای مالی")),
    ("کریپتو", google_news_search_url("بیت کوین ارز دیجیتال کریپتو")),
    ("اقتصاد", google_news_search_url("خودرو بازار خودرو قیمت خودرو ایران")),

    # Sports: split by major sports rather than one overloaded query.
    ("ورزش", google_news_search_url("ورزش فوتبال ایران")),
    ("ورزش", google_news_search_url("لیگ قهرمانان فوتبال اروپا")),
    ("ورزش", google_news_search_url("Premier League football")),
    ("ورزش", google_news_search_url("NBA basketball")),
    ("ورزش", google_news_search_url("تنیس Wimbledon ATP WTA")),
    ("ورزش", google_news_search_url("فرمول یک Formula 1 F1")),
    ("ورزش", google_news_search_url("UFC MMA")),
]


# ============================================================
# IMPORTANCE
# ============================================================

VERY_IMPORTANT_KEYWORDS = [
    "خبر فوری",
    "فوری",
    "انفجار",
    "حمله",
    "جنگ",
    "موشک",
    "حمله موشکی",
    "زلزله",
    "سیل",
    "آتش سوزی",
    "آتش‌سوزی",
    "هواپیما",
    "سقوط",
    "کشته",
    "مفقود",
    "ترور",
    "تحریم",
    "هسته ای",
    "هسته‌ای",
    "مذاکرات",
    "آتش بس",
    "آتش‌بس",
    "قطعی اینترنت",
    "قطع اینترنت",
]


IMPORTANT_KEYWORDS = [
    "ایران",
    "تهران",
    "دلار",
    "طلا",
    "سکه",
    "بورس",
    "اقتصاد",
    "قیمت",
    "بنزین",
    "نفت",
    "برق",
    "گاز",
    "هوش مصنوعی",
    "فناوری",
    "موبایل",
    "خودرو",
    "فوتبال",
    "ورزش",
    "پزشکی",
    "سلامت",
    "دانشگاه",
    "مدرسه",
    "جهان",
    "آمریکا",
    "اروپا",
    "اسرائیل",
    "روسیه",
    "اوکراین",
    "چین",
]

# Important-news rescue: the normal feed window stays 30 minutes, but
# high-impact stories are allowed a short grace period so delayed RSS
# timestamps cannot silently discard major events before intelligence scoring.
IMPORTANT_NEWS_RESCUE_MAX_AGE_MINUTES = 360

IMPORTANT_RESCUE_PATTERNS = [
    "جنگ", "حمله", "حمله موشکی", "بمباران", "انفجار", "زلزله", "سیل",
    "سونامی", "طوفان", "رانش زمین", "سقوط هواپیما", "سقوط بالگرد",
    "کشته", "کشته شد", "زخمی", "مفقود", "ترور", "تیراندازی", "بازداشت",
    "موشک", "پرتابه", "درگیری نظامی", "عملیات نظامی", "آتش بس", "آتش‌بس",
    "تحریم", "قطع اینترنت", "اختلال گسترده", "قطع برق", "قطع گاز",
    "مذاکرات", "توافق", "فراخوان", "فوری",
    "attack", "strike", "missile", "bombing", "explosion", "earthquake",
    "flood", "tsunami", "storm", "landslide", "crash", "killed", "wounded",
    "shooting", "military", "ceasefire", "sanction", "internet outage",
]


def is_important_news_rescue_candidate(title):
    """Return True when a slightly stale RSS item is still worth intelligence scoring."""
    value = normalize_space(title).lower()
    if not value:
        return False
    hits = sum(1 for pattern in IMPORTANT_RESCUE_PATTERNS if pattern.lower() in value)
    return hits >= 1



# ============================================================
# SOURCE QUALITY
# ============================================================

HIGH_QUALITY_HOSTS = {
    "irna.ir",
    "isna.ir",
    "mehrnews.com",
    "yjc.ir",
    "zoomit.ir",
    "tasnimnews.com",
    "farsnews.ir",
    "snn.ir",
    "tabnak.ir",
    "tejaratnews.com",
    "donya-e-eqtesad.com",
    "ecoiran.com",
    "varzesh3.com",
    "bbc.com",
    "reuters.com",
    "apnews.com",
    "aljazeera.com",
    "euronews.com",
    "variety.com",
}


MEDIUM_QUALITY_HOSTS = {
    "israelhayom.com",
    "theguardian.com",
    "nytimes.com",
    "washingtonpost.com",
    "cnn.com",
    "dw.com",
}


def publisher_quality(url):
    host = base_domain(
        get_hostname(url)
    )

    if not host:
        return 0

    if is_social_host(url):
        return -40

    if is_google_host(url):
        return -50

    for domain in HIGH_QUALITY_HOSTS:

        if (
            host == domain
            or host.endswith("." + domain)
        ):
            return 25

    for domain in MEDIUM_QUALITY_HOSTS:

        if (
            host == domain
            or host.endswith("." + domain)
        ):
            return 15

    return 5


# ============================================================
# HTTP
# ============================================================

SESSION = requests.Session()

SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "fa,en;q=0.8",
})


# ============================================================
# ROUNDUP FILTER
# ============================================================

ROUNDUP_PATTERNS = [
    r"چه خبر",
    r"مرور مهمترین",
    r"مهم‌ترین اخبار",
    r"مهمترین اخبار",
    r"اخبار مهم امروز",
    r"اخبار مهم",
    r"آخرین اخبار",
    r"بسته خبری",
    r"مرور اخبار",
    r"در این گزارش",
    r"اخبار روز",
    r"چند خبر",
    r"نگاهی به اخبار",
]


def is_roundup_title(title):
    if not title:
        return False

    title = normalize_space(
        title
    )

    for pattern in ROUNDUP_PATTERNS:

        if re.search(
            pattern,
            title,
            re.I
        ):
            return True

    return False


# ============================================================
# SOURCE CLEANING
# ============================================================

SOURCE_PHRASES = [
    "به گزارش خبرنگار مهر",
    "به گزارش مهر",
    "به گزارش ایسنا",
    "به گزارش ایرنا",
    "به گزارش خبرنگار ایرنا",
    "به گزارش خبرنگار ایسنا",
    "به گزارش یزدانه",
    "به گزارش باشگاه خبرنگاران جوان",
    "به گزارش خبرنگار باشگاه خبرنگاران جوان",
    "به گزارش خبرنگار",
    "به نقل از",
    "در گفت‌وگو با",
    "در گفتگو با",
    "طبق اعلام",
    "بر اساس اعلام",
    "براساس اعلام",
]


def clean_content(text):
    if not text:
        return ""

    text = BeautifulSoup(
        str(text),
        "html.parser"
    ).get_text(" ")

    text = normalize_space(
        text
    )

    # Remove a leading reporter/byline fragment such as
    # "سید محمدعلی سجادی - سرهنگ کاظمی رئیس پلیس راه ...".
    # This is deliberately limited to a short leading fragment followed by
    # an attribution/official-role phrase, so ordinary factual sentences
    # are not accidentally truncated.
    text = re.sub(
        r"^[^|،؛.!؟]{2,60}\s*[-–—]\s*(?="
        r"(?:سرهنگ|سردار|سرتیپ|رئیس|مدیر|فرمانده|استاندار|وزیر|معاون|"
        r"نماینده|سخنگو|مسئول|او\s+افزود|وی\s+افزود|وی\s+گفت|"
        r"گفت|افزود|اظهار\s+کرد|اعلام\s+کرد)"
        r")",
        "",
        text,
        count=1,
        flags=re.I
    )

    text = re.sub(
        r"^(مشهد|تهران|قم|تبریز|اصفهان|شیراز|کرج|اهواز|بغداد|واشنگتن|لندن)"
        r"\s*[-–—:]\s*",
        "",
        text,
        flags=re.I
    )

    for phrase in SOURCE_PHRASES:

        text = text.replace(
            phrase,
            ""
        )

    # Remove publisher/navigation boilerplate that can leak from broad
    # webpage containers (for example Digiato's membership and navigation
    # blocks). These are not article facts and must never reach the AI.
    BOILERPLATE_PHRASES = [
        "عضویت در دیجیاتو",
        "دیجیاتو را در گوگل بیشتر ببینید",
        "در دیجیاتو ثبت نام کنید",
        "جهت بهره مندی و دسترسی به امکانات ویژه",
        "عضو ویژه دیجیاتو شوید",
        "کپی لینک",
        "عضویت در خبرنامه",
        "اشتراک گذاری",
        "مطالب مرتبط",
        "بیشتر بخوانید",
        "آخرین اخبار",
    ]

    for phrase in BOILERPLATE_PHRASES:
        text = text.replace(phrase, " ")

    # Strip common byline/date fragments that are page chrome rather than
    # the article body. Keep dates that are actually part of a sentence.
    text = re.sub(
        r"\b(?:منتشر شده در|نوشته شده در)\s+"
        r"[^|]{0,100}?\s*\d{1,2}\s+"
        r"(?:فروردین|اردیبهشت|خرداد|تیر|مرداد|شهریور|مهر|آبان|آذر|دی|بهمن|اسفند)"
        r"\s+\d{4}\s*\|?\s*\d{1,2}:\d{2}",
        " ",
        text,
        flags=re.I
    )

    text = re.sub(
        r"\b(?:مرتضی قانع|نویسنده)\b",
        " ",
        text,
        flags=re.I
    )

    text = re.sub(
        r"\s+#?[A-Za-z0-9_]+\s*$",
        "",        text
    )

    text = re.sub(
        r"\b(ایرنا|ایسنا|مهر|باشگاه خبرنگاران جوان|خبرگزاری)"
        r"\s*[:：-]",
        "",
        text,
        flags=re.I
    )

    text = re.sub(
        r"\+\s*(فیلم|ویدئو|ویدیو|عکس|تصاویر)\s*$",
        "",
        text,
        flags=re.I
    )

    text = normalize_space(
        text
    )

    return text[:6000]


# ============================================================
# TITLE CLEANING
# ============================================================

def clean_title(title):
    if not title:
        return ""

    title = BeautifulSoup(
        str(title),
        "html.parser"
    ).get_text(" ")

    title = normalize_space(
        title
    )

    title = re.sub(
        r"\s*[-|]\s*"
        r"(facebook\.com|twitter\.com|x\.com|youtube\.com)"
        r"\s*$",
        "",
        title,
        flags=re.I
    )

    title = re.sub(
        r"\s+-\s+[A-Za-z0-9._-]+\.[A-Za-z]{2,}$",
        "",
        title
    )

    title = re.sub(
        r"^(ایرنا|ایسنا|مهر|فارس|تسنیم|یعنی چه|باشگاه خبرنگاران جوان)"
        r"\s*[-|:：]\s*",
        "",
        title,
        flags=re.I
    )

    title = re.sub(
        r"\s*\+\s*(فیلم|ویدئو|ویدیو|عکس|تصاویر)\s*$",
        "",
        title,
        flags=re.I
    )

    return normalize_space(
        title
    )[:180]


# ============================================================
# SENTENCE HELPERS
# ============================================================

def split_sentences(text):
    if not text:
        return []

    text = normalize_space(
        text
    )

    parts = re.split(
        r"(?<=[\.\!\؟\?؛])\s+",
        text
    )

    result = []

    for item in parts:

        item = normalize_space(
            item
        )

        if len(item) >= 15:
            result.append(
                item
            )

    return result


def sentence_score(sentence):
    score = 0

    for word in VERY_IMPORTANT_KEYWORDS:

        if word in sentence:
            score += 4

    for word in IMPORTANT_KEYWORDS:

        if word in sentence:
            score += 2

    if any(
        x in sentence
        for x in [
            "اعلام کرد",
            "گفت",
            "تصمیم",
            "تصویب",
            "تأیید"
        ]
    ):
        score += 1

    return score


def enforce_short_summary(text):
    text = clean_content(
        text
    )

    if not text:
        return ""

    sentences = split_sentences(
        text
    )

    if not sentences:
        return text[:600].strip()

    selected = [
        sentences[0]
    ]

    remaining = sorted(
        sentences[1:],
        key=sentence_score,
        reverse=True
    )

    for sentence in remaining:

        if len(selected) >= 3:
            break

        candidate = " ".join(
            selected + [sentence]
        )

        if len(candidate) <= 600:
            selected.append(
                sentence
            )

    return " ".join(
        selected
    )[:600].strip()


# ============================================================
# HISTORY
# ============================================================

def load_history():

    hash_history = set()
    title_history = []

    if not os.path.exists(
        HISTORY_FILE
    ):
        return (
            hash_history,
            title_history
        )

    try:

        with open(
            HISTORY_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            for raw in f.read().splitlines():

                line = raw.strip()

                if not line:
                    continue

                # New format:
                # TITLE|timestamp|title
                if line.startswith(
                    "TITLE|"
                ):

                    parts = line.split(
                        "|",
                        2
                    )

                    if len(parts) == 3:

                        try:
                            timestamp = int(
                                parts[1]
                            )
                        except Exception:
                            timestamp = 0

                        title = clean_title(
                            parts[2]
                        )

                        if title:
                            title_history.append(
                                (
                                    timestamp,
                                    title
                                )
                            )

                    continue

                hash_history.add(
                    normalize_space(
                        line
                    )
                )

    except Exception as e:

        print(
            f"History load error: {e}"
        )

    return (
        hash_history,
        title_history
    )


def save_history(
    hash_history,
    title_history
):

    try:

        cutoff = int(
            (
                datetime.now(
                    timezone.utc
                )
                - timedelta(
                    days=SEMANTIC_HISTORY_DAYS
                )
            ).timestamp()
        )

        recent_titles = []

        for timestamp, title in title_history:

            if timestamp >= cutoff:

                cleaned = clean_title(
                    title
                )

                if cleaned:
                    recent_titles.append(
                        (
                            timestamp,
                            cleaned
                        )
                    )

        # Deduplicate semantic records.
        seen_titles = set()
        cleaned_titles = []

        for timestamp, title in sorted(
            recent_titles,
            key=lambda x: x[0]
        ):

            key = normalize_space(
                title
            ).lower()

            if not key:
                continue

            if key in seen_titles:
                continue

            seen_titles.add(
                key
            )

            cleaned_titles.append(
                (
                    timestamp,
                    title
                )
            )

        with open(
            HISTORY_FILE,
            "w",
            encoding="utf-8"
        ) as f:

            for item in sorted(
                hash_history
            ):
                f.write(
                    item + "\n"
                )

            for timestamp, title in cleaned_titles:

                f.write(
                    f"TITLE|{timestamp}|{title}\n"
                )

    except Exception as e:

        print(
            f"History save error: {e}"
        )


def make_history_key(
    title,
    link
):

    canonical_link = canonicalize_url(
        link
    )

    value = (
        normalize_space(title)
        + "|"
        + canonical_link
    )

    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


# ============================================================
# TITLE / STORY NORMALIZATION
# ============================================================

STOPWORDS = {
    "از",
    "به",
    "در",
    "با",
    "برای",
    "و",
    "که",
    "را",
    "این",
    "آن",
    "یک",
    "شد",
    "شدند",
    "کرد",
    "کرده",
    "است",
    "هست",
    "می",
    "شود",
    "خواهد",
    "خبر",
    "گزارش",
    "اعلام",
    "جدید",
    "مهم",
    "آخرین",
    "درباره",
    "مورد",
    "پس",
    "نیز",
    "اما",
    "هم",
    "تا",
    "بر",
    "های",
    "ها",
}


GENERIC_NEWS_WORDS = {
    "خبر",
    "گزارش",
    "اعلام",
    "آخرین",
    "جدید",
    "مهم",
    "ادعا",
    "مدعی",
    "تصمیم",
    "تازه",
    "جزئیات",
    "واکنش",
    "اظهارات",
    "مواضع",
    "توضیح",
    "انتقاد",
    "تأکید",
    "تاکید",
    "خبرگزاری",
    "تحلیل",
    "تحلیلگر",
    "گفت",
    "گفتند",
    "عنوان",
    "رونمایی",
    "انتشار",
}


def title_tokens(title):

    title = normalize_digits(
        title
    )

    title = clean_title(
        title
    ).lower()

    title = re.sub(
        r"[^\w\u0600-\u06ff]+",
        " ",
        title
    )

    tokens = set()

    for token in title.split():

        token = token.strip()

        if len(token) < 2:
            continue

        if token in STOPWORDS:
            continue

        tokens.add(
            token
        )

    return tokens


def story_tokens(title):

    tokens = title_tokens(
        title
    )

    return {
        x
        for x in tokens
        if x not in GENERIC_NEWS_WORDS
    }


def title_similarity(a, b):

    A = title_tokens(a)
    B = title_tokens(b)

    if not A or not B:
        return 0

    intersection = len(
        A & B
    )

    union = len(
        A | B
    )

    if union == 0:
        return 0

    return (
        intersection
        / union
    )


def story_similarity(a, b):

    A = story_tokens(a)
    B = story_tokens(b)

    if not A or not B:

        return title_similarity(
            a,
            b
        )

    intersection = len(
        A & B
    )

    if intersection == 0:
        return 0

    union = len(
        A | B
    )

    jaccard = (
        intersection
        / union
    )

    containment = (
        intersection
        / min(
            len(A),
            len(B)
        )
    )

    return (
        jaccard * 0.45
        + containment * 0.55
    )


def numeric_anchors(text):
    """
    Numbers often identify the same event:
    15 نفر, 2-0, F-15, 1405, 49%, etc.
    """

    text = normalize_digits(
        text
    )

    found = re.findall(
        r"\b\d+(?:[.,]\d+)?\b",
        text
    )

    return set(
        found
    )


def same_story(a, b):

    title_a = clean_title(
        a.get(
            "title",
            ""
        )
    )

    title_b = clean_title(
        b.get(
            "title",
            ""
        )
    )

    if not title_a or not title_b:
        return False

    # Exact normalized title.
    if (
        normalize_space(
            title_a
        ).lower()
        ==
        normalize_space(
            title_b
        ).lower()
    ):
        return True

    similarity = story_similarity(
        title_a,
        title_b
    )

    title_sim = title_similarity(
        title_a,
        title_b
    )

    A = story_tokens(
        title_a
    )

    B = story_tokens(
        title_b
    )

    common = A & B

    # Very high similarity.
    if similarity >= 0.72:
        return True

    # High token overlap.
    if (
        len(common) >= 4
        and similarity >= 0.50
    ):
        return True

    # Short titles.
    if (
        len(A) <= 3
        or len(B) <= 3
    ):

        if title_sim >= 0.80:
            return True

    # Numeric anchors strengthen a moderate match.
    nums_a = numeric_anchors(
        title_a
    )

    nums_b = numeric_anchors(
        title_b
    )

    common_numbers = (
        nums_a & nums_b
    )

    if (
        common_numbers
        and similarity >= 0.45
        and len(common) >= 3
    ):
        return True

    # Strong event-anchor duplicate guard. Different publishers often phrase
    # the same breaking event very differently (e.g. "students injured" vs
    # "11 killed and wounded"). If a concrete event/location pair and the same
    # numeric casualty count are present, treat it as the same story even when
    # generic token similarity is below the normal threshold.
    event_anchors = (
        "تیراندازی", "انفجار", "زلزله", "سیل", "سونامی", "طوفان",
        "حمله", "حملات", "درگیری", "سقوط", "آتش سوزی", "آتش‌سوزی",
        "shooting", "explosion", "earthquake", "flood", "tsunami",
        "typhoon", "attack", "strike", "crash", "fire",
    )
    location_anchors = (
        "ترکیه", "اوکراین", "روسیه", "ژاپن", "ایران", "عربستان",
        "آمریکا", "آمریکا", "اسرائیل", "یمن", "لبنان",
        "turkey", "ukraine", "russia", "japan", "iran", "saudi",
        "america", "israel", "yemen", "lebanon",
    )
    event_a = {x for x in event_anchors if x in title_a.lower()}
    event_b = {x for x in event_anchors if x in title_b.lower()}
    loc_a = {x for x in location_anchors if x in title_a.lower()}
    loc_b = {x for x in location_anchors if x in title_b.lower()}
    if (
        common_numbers
        and (event_a & event_b)
        and (loc_a & loc_b)
    ):
        return True

    return False


def history_contains_story(
    title,
    title_history
):

    if not title:
        return False

    now = int(
        datetime.now(
            timezone.utc
        ).timestamp()
    )

    cutoff = (
        now
        - int(
            SEMANTIC_HISTORY_DAYS
            * 86400
        )
    )

    for timestamp, old_title in title_history:

        if timestamp < cutoff:
            continue

        if same_story(
            {"title": title},
            {"title": old_title}
        ):
            return True

    return False


def record_semantic_history(
    title,
    title_history
):

    title = clean_title(
        title
    )

    if not title:
        return

    # Avoid storing an immediate exact duplicate.
    for _, old_title in title_history[-20:]:

        if (
            normalize_space(
                old_title
            ).lower()
            ==
            normalize_space(
                title
            ).lower()
        ):
            return

    title_history.append(
        (
            int(
                datetime.now(
                    timezone.utc
                ).timestamp()
            ),
            title
        )
    )


# ============================================================
# DATE / FRESHNESS
# ============================================================

def parse_entry_time(entry):

    try:

        parsed = (
            entry.get(
                "published_parsed"
            )
            or entry.get(
                "updated_parsed"
            )
        )
        if parsed:

            return datetime(
                parsed.tm_year,
                parsed.tm_mon,
                parsed.tm_mday,
                parsed.tm_hour,
                parsed.tm_min,
                parsed.tm_sec,
                tzinfo=timezone.utc
            )

    except Exception:
        pass

    return None


def is_fresh(
    published_at
):

    if not published_at:
        return True

    try:

        now = datetime.now(
            timezone.utc
        )

        age_hours = (
            now - published_at
        ).total_seconds() / 3600

        if age_hours < 0:
            return True

        return (
            age_hours
            <= MAX_NEWS_AGE_HOURS
        )

    except Exception:
        return True


def calculate_recency_score(dt):

    if not dt:
        return 0

    try:

        now = datetime.now(
            timezone.utc
        )

        age_hours = (
            now - dt
        ).total_seconds() / 3600

        if age_hours < 1:
            return 12

        if age_hours < 3:
            return 10

        if age_hours < 6:
            return 8

        if age_hours < 12:
            return 5

        if age_hours < 24:
            return 3

        if age_hours <= 36:
            return 1

    except Exception:
        pass

    return 0


# ============================================================
# IMPORTANCE
# ============================================================

def calculate_keyword_importance(
    title,
    body
):

    text = f"{title} {body}"

    score = 0

    for word in VERY_IMPORTANT_KEYWORDS:

        if word in text:
            score += 8

    for word in IMPORTANT_KEYWORDS:

        if word in text:
            score += 3

    # Major international events must compete fairly with local stories
    # even when the source/headline is in English.
    if _has_global_high_impact(text):
        score += 14

    return min(
        score,
        55
    )


def source_priority(
    url,
    is_google=False
):

    score = publisher_quality(
        url
    )

    if is_google:
        score -= 10

    return score


def calculate_importance(
    candidate
):

    title = candidate.get(
        "title",
        ""
    )

    body = candidate.get(
        "summary",
        ""
    )

    score = 0

    score += calculate_keyword_importance(
        title,
        body
    )

    score += calculate_recency_score(
        candidate.get(
            "published_at"
        )
    )

    score += source_priority(
        candidate.get(
            "link",
            ""
        ),
        candidate.get(
            "is_google",
            False
        )
    )

    if candidate.get(
        "video_url"
    ):
        score += 3

    if candidate.get(
        "image_url"
    ):
        score += 2

    # Only count resolved_link if it is
    # actually a publisher article.
    resolved = candidate.get(
        "resolved_link",
        ""
    )

    if (
        resolved
        and not is_google_host(
            resolved
        )
        and not is_social_host(
            resolved
        )
    ):
        score += 8

    if is_social_host(
        candidate.get(
            "link",
            ""
        )
    ):
        score -= 30

    if is_google_host(
        candidate.get(
            "link",
            ""
        )
    ):
        score -= 20

    if is_roundup_title(
        title
    ):
        score -= 25

    if candidate.get(
        "cluster_size",
        1
    ) >= 2:

        score += min(
            candidate[
                "cluster_size"
            ],
            4
        ) * 2

    return score


# ============================================================
# GOOGLE NEWS RESOLUTION
# ============================================================

GOOGLE_RESOLVE_TIMEOUT = 6
GOOGLE_RESOLVE_WORKERS = 20
# Resolve a wider slice of Google discovery candidates so global breaking
# stories are not lost before their publisher URL is resolved.
GOOGLE_RESOLVE_MAX_CANDIDATES = 180


def _has_global_high_impact(text):
    """True for objectively high-impact global events used by Google fallback."""
    value = normalize_space(str(text or "")).lower()
    if not value:
        return False
    critical = (
        "war", "conflict", "ceasefire", "invasion", "missile", "airstrike",
        "bombing", "explosion", "earthquake", "tsunami", "hurricane",
        "wildfire", "mass shooting", "hostage", "terror attack", "nuclear",
        "sanction", "tariff", "strait of hormuz", "airspace", "nationwide outage",
        "emergency", "evacuation", "کشته", "زخمی", "انفجار", "زلزله", "سیل",
        "حمله", "جنگ", "درگیری", "موشک", "بمباران", "آتش‌بس", "تحریم",
        "تعرفه", "هسته‌ای", "تنگه هرمز", "وضعیت اضطراری", "تخلیه",
    )
    actors = (
        "iran", "united states", "u.s.", "china", "russia", "ukraine",
        "israel", "nato", "united nations", "un general assembly",
        "آمریکا", "ایران", "چین", "روسیه", "اوکراین", "اسرائیل",
        "ناتو", "سازمان ملل", "مجمع عمومی",
    )
    def hit(term):
        if any("\u0600" <= ch <= "\u06ff" for ch in term):
            return term in value
        return bool(re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", value, re.I))
    return any(hit(x) for x in critical) and any(hit(x) for x in actors)


def _is_telemetry_or_tracking_url(url):
    """Reject analytics/tracking endpoints during Google News resolution."""
    try:
        host = base_domain(get_hostname(url))
        path = urlparse(url).path.lower()
    except Exception:
        return False
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


def resolve_google_news_url(
    url
):

    if not url:
        return ""

    if not is_google_host(
        url
    ):
        return canonicalize_url(
            url
        )

    try:

        response = SESSION.get(
            url,
            timeout=GOOGLE_RESOLVE_TIMEOUT,
            allow_redirects=True,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "Referer": "https://news.google.com/",
            },
        )

        final_url = canonicalize_url(response.url)

        # Normal HTTP redirects are preferred.
        if (
            final_url
            and not is_google_host(final_url)
            and not is_social_host(final_url)
            and not _is_telemetry_or_tracking_url(final_url)
        ):
            return final_url

        # Google News sometimes leaves the request on a Google host and
        # embeds the publisher URL in the returned HTML instead of issuing a
        # normal redirect. Recover canonical/OG/external links before giving
        # up, while explicitly rejecting Google/social destinations.
        html = response.text or ""
        soup = BeautifulSoup(html, "html.parser")

        embedded = []
        for selector in (
            "link[rel='canonical']",
            "meta[property='og:url']",
            "meta[name='twitter:url']",
        ):
            for node in soup.select(selector):
                value = node.get("href") or node.get("content") or ""
                if value:
                    embedded.append(urljoin(response.url, value))

        for anchor in soup.select("a[href]"):
            embedded.append(urljoin(response.url, anchor.get("href", "")))

        for candidate in embedded:
            candidate = canonicalize_url(candidate)
            if (
                candidate
                and not is_google_host(candidate)
                and not is_social_host(candidate)
                and not _is_telemetry_or_tracking_url(candidate)
                and get_hostname(candidate)
                and not candidate.startswith("javascript:")
            ):
                return candidate

        # Last-resort extraction for pages where BeautifulSoup does not see
        # a usable anchor/canonical element.
        for match in re.findall(
            r'https?://[^\s"\'<>\\]+',
            html,
            flags=re.I,
        ):
            candidate = canonicalize_url(match.rstrip(").,;"))
            if (
                candidate
                and not is_google_host(candidate)
                and not is_social_host(candidate)
                and not _is_telemetry_or_tracking_url(candidate)
                and get_hostname(candidate)
            ):
                return candidate

    except Exception as e:

        print(
            f"Google URL resolve failed: {e}"
        )

    return ""


# ============================================================
# ARTICLE
# ============================================================

def fetch_article(
    url
):

    if not url:
        return ""

    try:

        response = SESSION.get(
            url,
            timeout=ARTICLE_TIMEOUT,
            allow_redirects=True
        )

        if response.status_code != 200:
            return ""

        content_type = response.headers.get(
            "content-type",
            ""
        ).lower()

        if "text/html" not in content_type:
            return ""

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        for tag in soup([
            "script",
            "style",
            "noscript",
            "svg",
            "nav",
            "footer",
            "header",
            "aside",
            "form"
        ]):
            tag.decompose()

        candidates = []

        selectors = [
            "article",
            "[itemprop='articleBody']",
            ".article-body",
            ".article__body",
            ".news-body",
            ".news-content",
            ".content",
            "main"
        ]

        for selector in selectors:

            for node in soup.select(
                selector
            ):

                text = normalize_space(
                    node.get_text(
                        " ",
                        strip=True
                    )
                )

                if len(text) > 150:

                    candidates.append(
                        text
                    )

        if not candidates:

            paragraphs = []

            for p in soup.find_all("p"):

                text = normalize_space(
                    p.get_text(
                        " ",
                        strip=True
                    )
                )

                if len(text) >= 40:

                    paragraphs.append(
                        text
                    )

            if paragraphs:

                candidates.append(
                    " ".join(
                        paragraphs
                    )
                )

        if not candidates:
            return ""

        cleaned_candidates = []
        for candidate in candidates:
            cleaned = clean_content(candidate)
            if len(cleaned) < 150:
                continue

            # Prefer article-like candidates and penalize obvious webpage
            # chrome. A larger but polluted container must not win merely
            # because it contains navigation and membership text.
            boilerplate_hits = sum(
                1 for phrase in (
                    "عضویت در دیجیاتو",
                    "کپی لینک",
                    "در دیجیاتو ثبت نام کنید",
                    "دیجیاتو را در گوگل بیشتر ببینید",
                    "عضویت در خبرنامه",
                    "مطالب مرتبط",
                )
                if phrase in cleaned
            )
            score = len(cleaned) - (boilerplate_hits * 500)
            cleaned_candidates.append((score, cleaned))

        if not cleaned_candidates:
            return ""

        _, text = max(
            cleaned_candidates,
            key=lambda item: item[0]
        )

        return text[:6000]

    except Exception as e:

        print(
            f"Article fetch error: {e}"
        )

        return ""


# ============================================================
# IMAGE
# ============================================================

def absolute_url(
    url,
    base
):

    if not url:
        return ""

    try:

        return urljoin(
            base,
            url
        )

    except Exception:

        return url


def image_is_acceptable(
    url
):

    if not url:
        return False

    if is_bad_media_url(
        url
    ):
        return False

    lower = url.lower()

    bad_words = [
        "logo",
        "icon",
        "avatar",
        "favicon",
        "placeholder",
        "default",
        "sprite",
        "google-news",
        "google_news",
        "blank.gif"
    ]

    for word in bad_words:

        if word in lower:
            return False

    return True


def extract_image_from_html(
    html,
    page_url
):

    if not html:
        return ""

    try:

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        meta_names = [
            ("property", "og:image"),
            ("property", "og:image:url"),
            ("property", "og:image:secure_url"),
            ("name", "twitter:image"),
            ("name", "twitter:image:src"),
        ]

        for attr, value in meta_names:

            tag = soup.find(
                "meta",
                attrs={
                    attr: value
                }
            )

            if tag:

                url = tag.get(
                    "content",
                    ""
                ).strip()

                url = absolute_url(
                    url,
                    page_url
                )

                if image_is_acceptable(
                    url
                ):
                    return url

        article_nodes = soup.select(
            "article img, "
            "main img, "
            "[itemprop='articleBody'] img"
        )

        best = ""

        for img in article_nodes:

            src = (
                img.get(
                    "data-src"
                )
                or img.get(
                    "data-original"
                )
                or img.get(
                    "data-lazy-src"
                )
                or img.get(
                    "src"
                )
                or ""
            )

            src = absolute_url(
                src,
                page_url
            )

            if not image_is_acceptable(
                src
            ):
                continue

            width = 0
            height = 0

            try:
                width = int(
                    img.get(
                        "width",
                        0
                    )
                )
            except Exception:
                pass

            try:
                height = int(
                    img.get(
                        "height",
                        0
                    )
                )
            except Exception:
                pass

            if (
                width >= 500
                or height >= 300
            ):
                return src

            if not best:
                best = src

        return best

    except Exception:
        return ""


def extract_image_from_article(
    url
):

    if not url:
        return ""

    try:

        response = SESSION.get(
            url,
            timeout=ARTICLE_TIMEOUT,
            allow_redirects=True
        )

        if response.status_code != 200:
            return ""

        content_type = response.headers.get(
            "content-type",
            ""
        ).lower()

        if "text/html" not in content_type:
            return ""

        return extract_image_from_html(
            response.text,
            response.url
        )

    except Exception as e:

        print(
            f"Image extraction error: {e}"
        )

        return ""


# ============================================================
# VIDEO
# ============================================================

def extract_video_from_html(
    html,
    page_url
):

    if not html:
        return ""

    try:

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        meta_values = [
            ("property", "og:video"),
            ("property", "og:video:url"),
            ("property", "og:video:secure_url"),
            ("name", "twitter:player:stream"),
        ]

        for attr, value in meta_values:

            tag = soup.find(
                "meta",
                attrs={
                    attr: value
                }
            )

            if tag:

                url = tag.get(
                    "content",
                    ""
                ).strip()

                url = absolute_url(
                    url,
                    page_url
                )

                if (
                    looks_like_video_url(
                        url
                    )
                    and not is_bad_media_url(
                        url
                    )
                ):
                    return url

        for source in soup.select(
            "video source, video"
        ):

            url = (
                source.get(
                    "src"
                )
                or source.get(
                    "data-src"
                )
                or ""
            )

            url = absolute_url(
                url,
                page_url
            )

            if (
                looks_like_video_url(
                    url
                )
                and not is_bad_media_url(
                    url
                )
            ):
                return url
        for script in soup.find_all(
            "script",
            attrs={
                "type": "application/ld+json"
            }
        ):

            try:

                data = json.loads(
                    script.string
                    or script.get_text()
                )

                objects = data

                if isinstance(
                    data,
                    dict
                ):
                    objects = [data]

                if not isinstance(
                    objects,
                    list
                ):
                    continue

                for obj in objects:

                    if not isinstance(
                        obj,
                        dict
                    ):
                        continue

                    for key in [
                        "contentUrl",
                        "embedUrl"
                    ]:

                        url = obj.get(
                            key
                        )

                        if not url:
                            continue

                        url = absolute_url(
                            url,
                            page_url
                        )

                        if (
                            looks_like_video_url(
                                url
                            )
                            and not is_bad_media_url(
                                url
                            )
                        ):
                            return url

            except Exception:
                continue

    except Exception:
        pass

    return ""


def extract_video_from_article(
    url
):

    if not url:
        return ""

    try:

        response = SESSION.get(
            url,
            timeout=ARTICLE_TIMEOUT,
            allow_redirects=True
        )

        if response.status_code != 200:
            return ""

        return extract_video_from_html(
            response.text,
            response.url
        )

    except Exception as e:

        print(
            f"Video extraction error: {e}"
        )

        return ""


# ============================================================
# DOWNLOAD
# ============================================================

def download_file(
    url,
    filename,
    max_mb
):

    if not url:
        return ""

    # CDN/media connections can close early (IncompleteRead). Retry the
    # complete download instead of dropping an otherwise valid story.
    max_attempts = 3

    for attempt in range(1, max_attempts + 1):

        try:

            response = SESSION.get(
                url,
                timeout=(10, ARTICLE_TIMEOUT),
                stream=True,
                allow_redirects=True,
                headers={
                    "Cache-Control": "no-cache",
                    "Accept-Encoding": "identity",
                },
            )

            if response.status_code != 200:
                print(
                    f"Media download HTTP {response.status_code} "
                    f"(attempt {attempt}/{max_attempts})"
                )
                response.close()
                if attempt < max_attempts:
                    time.sleep(attempt)
                    continue
                return ""

            content_length = response.headers.get(
                "content-length"
            )

            if content_length:

                try:

                    size_mb = int(
                        content_length
                    ) / (
                        1024 * 1024
                    )

                    if size_mb > max_mb:

                        print(
                            f"File too large: "
                            f"{size_mb:.1f} MB"
                        )

                        response.close()
                        return ""

                except Exception:
                    pass

            total = 0

            with open(
                filename,
                "wb"
            ) as f:

                for chunk in response.iter_content(
                    chunk_size=64 * 1024
                ):

                    if not chunk:
                        continue

                    total += len(
                        chunk
                    )

                    if (
                        total
                        > max_mb
                        * 1024
                        * 1024
                    ):

                        print(
                            f"Download exceeded "
                            f"{max_mb} MB"
                        )

                        return ""

                    f.write(
                        chunk
                    )

            response.close()

            if total == 0:
                raise IOError(
                    "media download returned zero bytes"
                )

            print(
                f"Media download OK: "
                f"{total / (1024 * 1024):.2f} MB "
                f"(attempt {attempt})"
            )

            return filename

        except Exception as e:

            print(
                f"Download error "
                f"(attempt {attempt}/{max_attempts}): {e}"
            )

            try:
                if os.path.exists(filename):
                    os.remove(filename)
            except Exception:
                pass

            if attempt < max_attempts:
                time.sleep(attempt)
                continue

    print("Media download failed after 3 attempts.")
    return ""


# ============================================================
# WATERMARK
# ============================================================

def find_font(
    size,
    bold=True
):

    if bold:

        candidates = [
            "Vazirmatn-Bold.ttf",
            "./Vazirmatn-Bold.ttf",
        ]

    else:

        candidates = [
            "Vazirmatn-Regular.ttf",
            "./Vazirmatn-Regular.ttf",
        ]

    for path in candidates:

        if os.path.exists(
            path
        ):

            try:

                return ImageFont.truetype(
                    path,
                    size
                )

            except Exception:
                pass

    return ImageFont.load_default()


def resize_for_telegram(
    image
):

    width, height = image.size

    ratio = min(
        MAX_OUTPUT_IMAGE_WIDTH / width,
        MAX_OUTPUT_IMAGE_HEIGHT / height,
        1.0
    )

    if ratio >= 1:
        return image

    new_width = max(
        1,
        int(width * ratio)
    )

    new_height = max(
        1,
        int(height * ratio)
    )

    return image.resize(
        (
            new_width,
            new_height
        ),
        Image.Resampling.LANCZOS
    )


def add_watermark(
    input_path,
    output_path
):
    """
    Add a small, fixed-size watermark safely inside the image.
    Uses Pillow's bottom-right anchor so font bbox offsets cannot
    push the watermark outside the image.
    """
    try:
        image = Image.open(input_path).convert("RGBA")
        image = resize_for_telegram(image)
        width, height = image.size

        # Intentionally small: branding without covering the photo.
        if width >= 1400:
            font_size = 11
        elif width >= 1000:
            font_size = 10
        elif width >= 700:
            font_size = 10
        else:
            font_size = 9

        font = find_font(font_size, bold=True)
        draw = ImageDraw.Draw(image, "RGBA")

        margin = max(8, int(min(width, height) * 0.012))
        pad_x = 4
        pad_y = 2

        bbox = draw.textbbox(
            (0, 0),
            WATERMARK_TEXT,
            font=font,
            anchor="rb",
        )
        text_width = max(1, bbox[2] - bbox[0])
        text_height = max(1, bbox[3] - bbox[1])

        text_x = width - margin
        text_y = height - margin

        rect = [
            max(0, text_x - text_width - pad_x),
            max(0, text_y - text_height - pad_y),
            min(width - 1, text_x + pad_x),
            min(height - 1, text_y + pad_y),
        ]

        draw.rounded_rectangle(
            rect,
            radius=4,
            fill=(0, 0, 0, 28),
        )

        draw.text(
            (text_x + 1, text_y + 1),
            WATERMARK_TEXT,
            font=font,
            anchor="rb",
            fill=(0, 0, 0, 45),
        )

        draw.text(
            (text_x, text_y),
            WATERMARK_TEXT,
            font=font,
            anchor="rb",
            fill=(255, 255, 255, 185),
        )

        image.convert("RGB").save(
            output_path,
            "JPEG",
            quality=90,
            optimize=True,
        )
        return output_path

    except Exception as e:
        print(f"Watermark error: {e}")
        return input_path


# ============================================================
# TELEGRAM
# ============================================================

def telegram_api(
    method
):

    return (
        f"https://api.telegram.org/bot"
        f"{BOT_TOKEN}/{method}"
    )


def send_message(
    text
):

    try:

        response = SESSION.post(
            telegram_api(
                "sendMessage"
            ),
            data={
                "chat_id": CHANNEL_ID,
                "text": text,
                "disable_web_page_preview": True,
            },
            timeout=REQUEST_TIMEOUT
        )

        if response.ok:
            return True

        print(
            f"sendMessage failed: "
            f"{response.status_code} "
            f"{response.text[:500]}"
        )

    except Exception as e:

        print(
            f"sendMessage error: {e}"
        )

    return False


def send_photo(
    path,
    caption
):

    try:

        with open(
            path,
            "rb"
        ) as photo:

            response = SESSION.post(
                telegram_api(
                    "sendPhoto"
                ),
                data={
                    "chat_id": CHANNEL_ID,
                    "caption": caption,
                },
                files={
                    "photo": photo
                },
                timeout=REQUEST_TIMEOUT
            )

        if response.ok:

            print(
                "PHOTO PUBLISHED"
            )

            return True

        print(
            f"sendPhoto failed: "
            f"{response.status_code} "
            f"{response.text[:500]}"
        )

    except Exception as e:

        print(
            f"sendPhoto error: {e}"
        )

    return False


def get_video_duration(path):
    """Return accurate duration in whole seconds using ffprobe."""
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=15,
        )
        value = float((probe.stdout or "").strip())
        if value > 0:
            return max(1, int(round(value)))
    except Exception as e:
        print(f"Video duration probe failed: {e}")
    return 0


def send_video(path, caption):
    try:
        duration = get_video_duration(path)
        width = 0
        height = 0
        try:
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", path],
                capture_output=True, text=True, timeout=15,
            )
            dims = (probe.stdout or "").strip().split("x")
            if len(dims) == 2:
                width, height = int(dims[0]), int(dims[1])
        except Exception as e:
            print(f"Video dimensions probe failed: {e}")

        with open(path, "rb") as video:
            data = {
                "chat_id": CHANNEL_ID,
                "caption": caption,
                "supports_streaming": "true",
            }
            if duration:
                data["duration"] = str(duration)
            if width and height:
                data["width"] = str(width)
                data["height"] = str(height)

            response = SESSION.post(
                telegram_api("sendVideo"),
                data=data,
                files={"video": video},
                timeout=120,
            )

        if response.ok:
            print(f"VIDEO PUBLISHED | duration={duration}s | size={os.path.getsize(path)}")
            return True

        print(f"sendVideo failed: {response.status_code} {response.text[:500]}")
    except Exception as e:
        print(f"sendVideo error: {e}")
    return False


# ============================================================
# CAPTION
# ============================================================

def _sanitize_caption_text(text):
    """Final caption safety: remove source/link boilerplate before Telegram."""
    value = str(text or "")
    value = re.sub(r"https?://\\S+", " ", value, flags=re.I)
    value = re.sub(r"www\\.\\S+", " ", value, flags=re.I)
    value = re.sub(
        r"(?:📡\\s*)?(?:منبع|منبع خبر|منبع اصلی)\\s*[:：-]?\\s*[^\\n]+",
        " ",
        value,
        flags=re.I,
    )
    value = re.sub(r"\\b(?:باشگاه خبرنگاران جوان|yjc\\.ir)\\b", " ", value, flags=re.I)
    value = re.sub(r"\\s{2,}", " ", value).strip()
    return value


def build_caption(
    title,
    body
):
    """Single canonical V13 news caption formatter."""
    title = _sanitize_caption_text(clean_title(title))
    body = _sanitize_caption_text(enforce_short_summary(body))

    parts = [f"📰 {title}"]
    if body:
        parts.append(body)
    parts.append("#نبض_خبر")
    parts.append("🔗 کانال نبض خبر: https://t.me/NabzKhabarOfficial")
    return "\n\n".join(parts)


# ============================================================
# GEMINI
# ============================================================

def gemini_request(
    title,
    article_text
):

    if not AI_API_KEY:
        return None

    if not article_text:
        article_text = title

    endpoint = (
        "https://generativelanguage.googleapis.com/"
        "v1beta/models/"
        f"{GEMINI_MODEL}:generateContent"
    )

    prompt = f"""
تو ویراستار ارشد یک کانال خبری فارسی هستی.

عنوان خبر:
{title}

متن خبر:
{article_text[:6000]}

وظیفه:
1. یک تیتر خبری کوتاه، دقیق و طبیعی فارسی بنویس.
2. متن را بدون اضافه کردن هیچ واقعیت جدیدی در حداکثر 3 جمله خلاصه کن.
3. نام رسانه، نام خبرگزاری، لینک، عبارت «به گزارش»، عبارت‌های تبلیغاتی و منبع را حذف کن.
4. اگر متن ناقص است، چیزی را حدس نزن.
5. لحن کاملاً خبری، خنثی و حرفه‌ای باشد.
6. از اغراق، کلیک‌بیت و نظر شخصی خودداری کن.
7. اگر عنوان اصلی مناسب است، آن را بی‌دلیل تغییر نده.
8. فقط اطلاعات موجود در متن را استفاده کن.

فقط JSON معتبر برگردان:

{{
  "title": "تیتر نهایی",
  "summary": "خلاصه نهایی"
}}
"""

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "maxOutputTokens": 500,
        }
    }

    try:

        response = SESSION.post(
            endpoint,
            params={
                "key": AI_API_KEY
            },
            json=payload,
            timeout=30
        )

        if not response.ok:

            print(
                f"Gemini error: "
                f"{response.status_code} "
                f"{response.text[:600]}"
            )

            return None

        data = response.json()

        text = (
            data.get(
                "candidates",
                [{}]
            )[0]
            .get(
                "content",
                {}
            )
            .get(
                "parts",
                [{}]
            )[0]
            .get(
                "text",
                ""
            )
        )

        if not text:
            return None

        text = text.strip()

        if text.startswith(
            "```"
        ):

            text = re.sub(
                r"^```(?:json)?",
                "",
                text,
                flags=re.I
            )

            text = re.sub(
                r"```$",
                "",
                text
            )

            text = text.strip()

        result = json.loads(
            text
        )

        final_title = clean_title(
            result.get(
                "title",
                ""
            )
        )

        final_summary = enforce_short_summary(
            result.get(
                "summary",
                ""
            )
        )

        if not final_title:

            final_title = clean_title(
                title
            )

        return {
            "title": final_title,
            "summary": final_summary
        }

    except Exception as e:

        print(
            f"Gemini exception: {e}"
        )

    return None


# ============================================================
# LOCAL FALLBACK
# ============================================================

def local_news_engine(
    title,
    body
):

    title = clean_title(
        title
    )

    body = clean_content(
        body
    )

    return {
        "title": title,
        "summary": enforce_short_summary(
            body
        )
    }


# ============================================================
# RSS COLLECTION# ============================================================

def collect_feed(
    category,
    url,
    is_google=False
):

    candidates = []

    try:

        response = None
        for attempt in range(3):
            try:
                response = SESSION.get(
                    url,
                    timeout=REQUEST_TIMEOUT
                )
                if response.status_code not in (429, 500, 502, 503, 504):
                    break
                wait_seconds = 1.5 * (2 ** attempt)
                print(
                    f"V13 RSS RETRY: {category} | HTTP {response.status_code} | "
                    f"attempt={attempt + 1}/3 | wait={wait_seconds:.1f}s"
                )
                if attempt < 2:
                    time.sleep(wait_seconds)
            except requests.RequestException as exc:
                print(
                    f"V13 RSS RETRY: {category} | {type(exc).__name__} | "
                    f"attempt={attempt + 1}/3"
                )
                if attempt < 2:
                    time.sleep(1.5 * (2 ** attempt))
        if response is None:
            raise RuntimeError("RSS request returned no response")
        response.raise_for_status()

        feed = feedparser.parse(
            response.content
        )

        print(
            f"RSS OK: {category} | "
            f"{len(feed.entries)} | "
            f"{url}"
        )

        for entry in feed.entries[:20]:

            # Strict freshness gate: only entries with a reliable publication
            # timestamp from the source are allowed into processing. This keeps
            # stale RSS items from consuming network/AI/media resources.
            published_at = parse_entry_time(
                entry
            )

            if not published_at:
                print(
                    f"SKIPPED NO TIMESTAMP: "
                    f"{entry.get('title', '')}"
                )
                continue

            age_seconds = (
                datetime.now(timezone.utc) - published_at
            ).total_seconds()

            if age_seconds < 0:
                # Small clock skew is tolerated, but clearly future-dated
                # entries are not allowed to bypass the freshness gate.
                if age_seconds < -300:
                    print(
                        f"SKIPPED INVALID FUTURE TIMESTAMP: "
                        f"{entry.get('title', '')}"
                    )
                    continue
                age_seconds = 0

            if age_seconds > (FEED_COLLECTION_WINDOW_MINUTES * 60):
                raw_entry_title = normalize_space(entry.get("title", ""))
                rescue_limit = IMPORTANT_NEWS_RESCUE_MAX_AGE_MINUTES * 60

                if (
                    age_seconds <= rescue_limit
                    and is_important_news_rescue_candidate(raw_entry_title)
                ):
                    print(
                        "V13 IMPORTANT NEWS RESCUE: "
                        f"{raw_entry_title} | age={int(age_seconds // 60)}m"
                    )
                else:
                    print(
                        f"SKIPPED OUTSIDE {FEED_COLLECTION_WINDOW_MINUTES}M WINDOW: "
                        f"{raw_entry_title}"
                    )
                    continue

            raw_title = normalize_space(
                entry.get(
                    "title",
                    ""
                )
            )

            raw_link = clean_url(
                entry.get(
                    "link",
                    ""
                )
            )

            if not raw_title or not raw_link:
                continue

            title = clean_title(
                raw_title
            )

            if not title:
                continue

            if is_roundup_title(
                title
            ):

                print(
                    f"SKIPPED ROUNDUP: "
                    f"{title}"
                )

                continue


            summary = clean_content(
                entry.get(
                    "summary",
                    ""
                )
                or entry.get(
                    "description",
                    ""
                )
            )

            image_url = ""

            # RSS media.
            media_content = entry.get(
                "media_content",
                []
            )

            for media in media_content:

                if not isinstance(
                    media,
                    dict
                ):
                    continue

                media_url = clean_url(
                    media.get(
                        "url",
                        ""
                    )
                )

                if (
                    image_is_acceptable(
                        media_url
                    )
                    and not looks_like_video_url(
                        media_url
                    )
                ):

                    image_url = media_url
                    break

            # RSS enclosure.
            if not image_url:

                enclosures = entry.get(
                    "enclosures",
                    []
                )

                for enclosure in enclosures:

                    media_url = clean_url(
                        enclosure.get(
                            "href",
                            ""
                        )
                        or enclosure.get(
                            "url",
                            ""
                        )
                    )

                    media_type = enclosure.get(
                        "type",
                        ""
                    ).lower()

                    if (
                        "image" in media_type
                        and image_is_acceptable(
                            media_url
                        )
                    ):

                        image_url = media_url
                        break

            source_name = ""
            source_url = ""

            source = entry.get(
                "source"
            )

            if isinstance(
                source,
                dict
            ):

                source_name = normalize_space(
                    source.get(
                        "title",
                        ""
                    )
                )

                source_url = clean_url(
                    source.get(
                        "href",
                        ""
                    )
                )

            candidate = {
                "category": category,
                "title": title,
                "summary": summary,
                "link": canonicalize_url(
                    raw_link
                ),
                "published_at": published_at,
                "image_url": image_url,
                "video_url": "",
                "is_google": is_google,
                "resolved_link": "",
                "source_name": source_name,
                "source_url": source_url,
                "article_text": "",
                "importance": 0,
                "cluster_size": 1,
            }

            candidates.append(
                candidate
            )

    except Exception as e:

        print(
            f"RSS ERROR: {category} | "
            f"{url} | {e}"
        )

    return candidates


# ============================================================
# CLUSTERING
# ============================================================

def choose_cluster_representative(
    cluster
):

    if not cluster:
        return None

    def score(item):

        value = 0

        value += publisher_quality(
            item.get(
                "link",
                ""
            )
        )

        # Direct publishers beat Google discovery.
        if item.get(
            "is_google"
        ):
            value -= 25

        if item.get(
            "resolved_link"
        ):
            value += 8

        if item.get(
            "article_text"
        ):
            value += 5

        if item.get(
            "image_url"
        ):
            value += 3

        if item.get(
            "video_url"
        ):
            value += 4

        value += item.get(
            "importance",
            0
        )

        return value

    return max(
        cluster,
        key=score
    )


def cluster_candidates(
    candidates
):

    clusters = []

    ordered = sorted(
        candidates,
        key=lambda x: (
            publisher_quality(
                x.get(
                    "link",
                    ""
                )
            ),
            x.get(
                "published_at"
            )
            or datetime.min.replace(
                tzinfo=timezone.utc
            )
        ),
        reverse=True
    )

    for candidate in ordered:

        placed = False

        for cluster in clusters:

            for existing in cluster:

                if same_story(
                    candidate,
                    existing
                ):

                    cluster.append(
                        candidate
                    )

                    placed = True
                    break

            if placed:
                break

        if not placed:

            clusters.append(
                [candidate]
            )

    result = []

    for cluster in clusters:

        representative = choose_cluster_representative(
            cluster
        )

        if not representative:
            continue

        representative["cluster_size"] = len(
            cluster
        )

        # Transfer useful metadata.
        for item in cluster:

            if (
                not representative.get(
                    "summary"
                )
                and item.get(
                    "summary"
                )
            ):

                representative["summary"] = item[
                    "summary"
                ]

            if (
                not representative.get(
                    "image_url"
                )
                and item.get(
                    "image_url"
                )
                and not is_google_host(
                    item.get(
                        "image_url",
                        ""
                    )
                )
            ):

                representative["image_url"] = item[
                    "image_url"
                ]

        result.append(
            representative
        )

    return result


# ============================================================
# COLLECT ALL
# ============================================================

def collect_candidates(
    hash_history,
    title_history
):

    all_candidates = []

    # --------------------------------------------------------
    # Direct publishers
    # --------------------------------------------------------

    def collect_one_direct(feed):

        category, url = feed

        return collect_feed(
            category,
            url,
            is_google=False
        )

    # Fetch independent feeds concurrently so adding sources does not
    # make total network wait time grow linearly with source count.
    with ThreadPoolExecutor(max_workers=8) as executor:

        for items in executor.map(
            collect_one_direct,
            DIRECT_RSS_FEEDS
        ):
            all_candidates.extend(items)

    # --------------------------------------------------------
    # Google discovery
    # --------------------------------------------------------

    def collect_one_google(feed):

        category, url = feed

        return collect_feed(
            category,
            url,
            is_google=True
        )

    # More Google queries are now used for breadth, so keep discovery
    # parallelized to avoid making network wait grow with query count.
    with ThreadPoolExecutor(max_workers=6) as executor:

        for items in executor.map(
            collect_one_google,
            GOOGLE_NEWS_FEEDS
        ):
            all_candidates.extend(items)

    print(
        f"Raw candidates found: "
        f"{len(all_candidates)}"
    )

    # --------------------------------------------------------
    # Exact duplicate removal
    # --------------------------------------------------------

    unique = {}

    for item in all_candidates:

        key = (
            normalize_space(
                item.get(
                    "title",
                    ""
                )
            ).lower()
            + "|"
            + canonicalize_url(
                item.get(
                    "link",
                    ""
                )
            ).lower()
        )

        if key not in unique:
            unique[key] = item

    all_candidates = list(
        unique.values()
    )

    # --------------------------------------------------------
    # HARD HISTORY FILTER BEFORE SCORING
    #
    # This is one of the most important v11 changes.
    # Old/recent stories are removed BEFORE top priority.
    # --------------------------------------------------------

    filtered = []

    history_skipped = 0

    for item in all_candidates:

        title = item.get(
            "title",
            ""
        )

        link = item.get(
            "link",
            ""
        )

        old_hash = make_history_key(
            title,
            link
        )

        if old_hash in hash_history:

            history_skipped += 1

            print(
                f"PRE-SKIPPED OLD HASH: "
                f"{title}"
            )

            continue

        if history_contains_story(
            title,
            title_history
        ):

            history_skipped += 1

            print(
                f"PRE-SKIPPED SEMANTIC: "
                f"{title}"
            )

            continue

        filtered.append(
            item
        )

    print(
        f"Removed by history before scoring: "
        f"{history_skipped}"
    )

    all_candidates = filtered

    if not all_candidates:
        return []

    # --------------------------------------------------------
    # Initial importance.
    # --------------------------------------------------------

    for item in all_candidates:

        item["importance"] = calculate_importance(
            item
        )

    # --------------------------------------------------------
    # Initial clustering.
    # --------------------------------------------------------

    clustered = cluster_candidates(
        all_candidates
    )

    print(
        f"After story clustering: "
        f"{len(clustered)}"
    )

    # --------------------------------------------------------
    # Google resolution.
    #
    # IMPORTANT:
    # source_url is NOT treated as article URL anymore.
    # --------------------------------------------------------

    clustered.sort(
        key=lambda x: (
            x.get(
                "importance",
                0
            ),
            x.get(
                "published_at"
            )
            or datetime.min.replace(
                tzinfo=timezone.utc
            )
        ),
        reverse=True
    )

    resolved_count = 0
    removed_google = 0

    # Google News redirect resolution used to run serially. With many
    # discovery queries, a handful of slow Google redirects could consume
    # most of the 10-minute workflow interval. Resolve them concurrently
    # with a short hard timeout so one bad redirect cannot stall the run.
    google_items = [
        item for item in clustered[:GOOGLE_RESOLVE_MAX_CANDIDATES]
        if item.get("is_google")
    ]

    def resolve_one_google(item):
        link = item.get("link", "")
        return item, resolve_google_news_url(link)

    with ThreadPoolExecutor(max_workers=GOOGLE_RESOLVE_WORKERS) as executor:
        for item, resolved in executor.map(
            resolve_one_google,
            google_items
        ):
            if resolved:
                item["resolved_link"] = resolved

                if (
                    not is_social_host(resolved)
                    and not is_google_host(resolved)
                ):
                    item["link"] = resolved
                    resolved_count += 1

            # DO NOT use source_url as an article URL.
            # Google source_url is often just publisher homepage.
            if not item.get("resolved_link"):
                item["_unresolved_google"] = True

    print(
        f"Google articles resolved: "
        f"{resolved_count}"
    )

    # --------------------------------------------------------
    # Remove unresolved Google candidates.
    #
    # Direct publisher RSS remains the fallback.
    # --------------------------------------------------------

    cleaned = []

    for item in clustered:

        # Re-check the actual resolved publisher after Google News URL
        # resolution. This closes the loophole where source_url is only
        # metadata and the real article belongs to an Iranian publisher.
        if _is_iranian_blocked_source(item):
            print(
                f"SKIPPED IRANIAN PUBLISHER: "
                f"{item.get('title', '')}"
            )
            continue

        if (
            item.get(
                "is_google"
            )
            and not item.get(
                "resolved_link"
            )
        ):
            # A failed Google redirect must not erase a genuinely breaking
            # story. Keep only clearly high-impact headlines with a useful
            # RSS summary; ordinary unresolved Google items are still dropped.
            google_title = normalize_space(item.get("title", "")).lower()
            google_summary = normalize_space(item.get("summary", ""))
            high_priority_google = _has_global_high_impact(
                google_title + " " + google_summary
            )
            if high_priority_google and len(google_summary) >= 120:
                item["_unresolved_google_high_impact"] = True
                print(
                    f"KEEP UNRESOLVED HIGH-IMPACT GOOGLE: "
                    f"{item.get('title', '')}"
                )
                cleaned.append(item)
                continue

            removed_google += 1

            print(
                f"SKIPPED UNRESOLVED GOOGLE: "
                f"{item.get('title', '')}"
            )

            continue

        cleaned.append(
            item
        )

    clustered = cleaned

    print(
        f"Unresolved Google removed: "
        f"{removed_google}"
    )

    # --------------------------------------------------------
    # Recalculate final quality.
    # --------------------------------------------------------

    for item in clustered:

        item["importance"] = calculate_importance(
            item
        )

    # --------------------------------------------------------
    # Cluster again after Google resolution.
    # --------------------------------------------------------

    clustered = cluster_candidates(
        clustered
    )

    # --------------------------------------------------------
    # Final importance.
    # --------------------------------------------------------

    for item in clustered:

        item["importance"] = calculate_importance(
            item
        )

    # --------------------------------------------------------
    # FINAL HISTORY FILTER AGAIN
    #
    # Protects against clusters/reps changing titles.
    # --------------------------------------------------------

    final_candidates = []

    for item in clustered:
        title = item.get(
            "title",
            ""
        )

        link = item.get(
            "link",
            ""
        )

        if history_contains_story(
            title,
            title_history
        ):
            continue

        if make_history_key(
            title,
            link
        ) in hash_history:
            continue

        final_candidates.append(
            item
        )

    clustered = final_candidates

    # --------------------------------------------------------
    # Final sort.
    # --------------------------------------------------------

    clustered.sort(
        key=lambda x: (
            x.get(
                "importance",
                0
            ),
            x.get(
                "published_at"
            )
            or datetime.min.replace(
                tzinfo=timezone.utc
            )
        ),
        reverse=True
    )

    print(
        f"Candidates found: "
        f"{len(clustered)}"
    )

    print(
        "\nTOP PRIORITY NEWS:"
    )

    for item in clustered[:15]:

        print(
            f"[{item.get('importance', 0)}] "
            f"{item.get('category', '')} - "
            f"{item.get('title', '')}"
        )

    return clustered


# ============================================================
# CATEGORY
# ============================================================

def category_family(
    category
):

    category = normalize_space(
        category
    )

    mapping = {
        "خبر فوری": "ایران",
        "حوادث": "حوادث",
        "ایران": "ایران",
        "جهان": "جهان",
        "اقتصاد": "اقتصاد",
        "دلار": "بازار",
        "ارز": "بازار",
        "طلا": "بازار",
        "سکه": "بازار",
        "بورس": "بازار",
        "نفت": "انرژی",
        "هوش مصنوعی": "فناوری",
        "فناوری": "فناوری",
        "موبایل": "فناوری",
        "خودرو": "خودرو",
        "ورزش": "ورزش",
        "سلامت": "سلامت",
        "علم": "علم",
        "فرهنگ": "فرهنگ",
        "جامعه": "جامعه",
        "کریپتو": "بازار",
    }

    return mapping.get(
        category,
        category
    )


def family_count(
    candidate,
    selected
):

    family = category_family(
        candidate.get(
            "category",
            ""
        )
    )

    count = 0

    for item in selected:

        if category_family(
            item.get(
                "category",
                ""
            )
        ) == family:

            count += 1

    return count


def diversity_penalty(
    candidate,
    selected
):

    count = family_count(
        candidate,
        selected
    )

    if count <= 0:
        return 0

    if count == 1:
        return 4

    if count == 2:
        return 10

    return 18


# ============================================================
# PROCESS NEWS
# ============================================================

def process_news(
    candidate,
    hash_history,
    title_history
):

    original_title = candidate.get(
        "title",
        ""
    )

    link = canonicalize_url(
        candidate.get(
            "link",
            ""
        )
    )

    candidate["link"] = link

    print(
        f"\nProcessing: "
        f"{original_title}"
    )

    # --------------------------------------------------------
    # Exact hash.
    # --------------------------------------------------------

    history_key = make_history_key(
        original_title,
        link
    )

    if history_key in hash_history:

        print(
            "SKIPPED: old hash history"
        )

        return False

    # --------------------------------------------------------
    # Semantic history.
    # --------------------------------------------------------

    if history_contains_story(
        original_title,
        title_history
    ):

        print(
            "SKIPPED: semantic history"
        )

        return False

    # --------------------------------------------------------
    # Article URL.
    # --------------------------------------------------------

    article_url = (
        candidate.get(
            "resolved_link"
        )
        or candidate.get(
            "link"
        )
    )

    if (
        is_google_host(
            article_url
        )
        or is_social_host(
            article_url
        )
    ):
        article_url = ""

    # --------------------------------------------------------
    # Article text.
    # --------------------------------------------------------

    article_text = ""

    if article_url:

        article_text = fetch_article(
            article_url
        )

    candidate["article_text"] = article_text

    if article_text:

        print(
            f"Article text: "
            f"{len(article_text)} chars"
        )

    # --------------------------------------------------------
    # Image.
    # --------------------------------------------------------

    image_url = ""

    rss_image = candidate.get(
        "image_url",
        ""
    )

    if image_is_acceptable(
        rss_image
    ):
        image_url = rss_image

    if candidate.get(
        "is_google"
    ):

        image_url = ""

        if article_url:

            publisher_image = extract_image_from_article(
                article_url
            )

            if publisher_image:
                image_url = publisher_image

    else:

        if article_url:

            article_image = extract_image_from_article(
                article_url
            )

            if article_image:
                image_url = article_image

    if not image_is_acceptable(
        image_url
    ):
        image_url = ""

    # --------------------------------------------------------
    # Video.
    # --------------------------------------------------------

    video_url = ""

    if article_url:

        video_url = extract_video_from_article(
            article_url
        )

    if not video_url:

        rss_video = candidate.get(
            "video_url",
            ""
        )

        if looks_like_video_url(
            rss_video
        ):
            video_url = rss_video

    if (
        is_hls_url(
            video_url
        )
        or is_bad_media_url(
            video_url
        )
    ):

        if video_url:

            print(
                f"Video skipped: "
                f"{video_url}"
            )

        video_url = ""

    # --------------------------------------------------------
    # Gemini.
    # --------------------------------------------------------

    source_text = (
        article_text
        or candidate.get(
            "summary",
            ""
        )
        or original_title
    )

    ai_result = None

    # Always enter the V13 router. It owns the free fallback chain
    try:
        ai_result = gemini_request(
            original_title,
            source_text
        )
    except Exception as exc:
        print(f"V13 AI ROUTER ERROR: {exc}", flush=True)
        ai_result = None

    if ai_result:

        final_title = ai_result.get(
            "title",
            ""
        )

        final_summary = ai_result.get(
            "summary",
            ""
        )

        print(
            f"Gemini title: "
            f"{final_title}"
        )

    else:

        # AI is optional for already-Persian publisher content. If the free
        # AI pool is temporarily exhausted/cooling down, never lose a valid
        # Iranian/Persian news event just because rewriting failed. Use only
        # the publisher's existing Persian text; for foreign content, AI is
        # mandatory because we must not publish untranslated English.
        if _persian_ratio(original_title) >= 0.60:
            print("V13 AI FALLBACK: AI pool unavailable; using source Persian title safely.")
            final_title = clean_title(original_title)

            source_clean = clean_content(source_text)
            if _persian_ratio(source_clean) >= 0.55:
                final_summary = enforce_short_summary(source_clean)
            else:
                final_summary = ""
        else:
            print("V13 AI FALLBACK: foreign story blocked because no translation model is available.")
            candidate["publication_status"] = "ai_unavailable_foreign"
            return False

    # --------------------------------------------------------
    # Final cleaning.
    # --------------------------------------------------------

    final_title = clean_title(
        final_title
    )

    final_summary = enforce_short_summary(
        final_summary
    )

    if not final_title:

        final_title = clean_title(
            original_title
        )

    # --------------------------------------------------------
    # Final semantic protection.
    # --------------------------------------------------------

    if history_contains_story(
        final_title,
        title_history
    ):

        print(
            "SKIPPED DUPLICATE: final Gemini title "
            "matches recent history"
        )
        candidate["publication_status"] = "skipped_duplicate"
        return False

    # --------------------------------------------------------
    # Also check original vs final.
    # If Gemini accidentally creates a title extremely
    # close to another selected story, block it later too.
    # --------------------------------------------------------

    caption = build_caption(
        final_title,
        final_summary
    )

    # ========================================================
    # VIDEO FIRST
    # ========================================================

    if video_url:

        print(
            f"Downloading video: "
            f"{video_url}"
        )

        video_path = (
            "nabz_video_"
            + hashlib.md5(
                video_url.encode()
            ).hexdigest()
            + ".mp4"
        )

        downloaded = download_file(
            video_url,
            video_path,
            MAX_VIDEO_MB
        )

        if downloaded:

            success = send_video(
                downloaded,
                caption
            )

            try:
                os.remove(
                    downloaded
                )
            except Exception:
                pass

            if success:

                # Store BOTH original and final title.
                hash_history.add(
                    history_key
                )

                record_semantic_history(
                    original_title,
                    title_history
                )

                record_semantic_history(
                    final_title,
                    title_history
                )

                save_history(
                    hash_history,
                    title_history
                )

                print(
                    f"PUBLISHED: "
                    f"{final_title}"
                )

                return True

        # Video is optional media, not a publication requirement.
        # If a selected story is important but its video is too large,
        # unavailable, or rejected by Telegram, continue through the normal
        # photo -> text fallback so the news event itself is never silently lost.
        print(
            "VIDEO FALLBACK: video unavailable/failed; "
            "continuing with photo/text fallback."
        )

    # ========================================================
    # PHOTO
    # ========================================================

    if image_url:

        print(
            f"Downloading image: "
            f"{image_url}"
        )

        image_raw = (
            "nabz_image_"
            + hashlib.md5(
                image_url.encode()
            ).hexdigest()
            + ".jpg"
        )

        downloaded = download_file(
            image_url,
            image_raw,
            MAX_IMAGE_MB
        )

        if downloaded:

            try:

                img = Image.open(
                    downloaded
                )

                img.verify()

                watermarked = (
                    "nabz_watermark_"
                    + hashlib.md5(
                        image_url.encode()
                    ).hexdigest()
                    + ".jpg"
                )

                # add_watermark() may intentionally return the original
                # image when the watermark is unsafe/too large. Always use
                # the returned path so we never try to upload a file that
                # was not created.
                branded_path = add_watermark(
                    downloaded,
                    watermarked
                )

                success = send_photo(
                    branded_path,
                    caption
                )

                try:
                    os.remove(
                        downloaded
                    )
                except Exception:
                    pass

                try:

                    if (
                        watermarked
                        != downloaded
                    ):
                        os.remove(
                            watermarked
                        )

                except Exception:
                    pass

                if success:

                    hash_history.add(
                        history_key
                    )

                    record_semantic_history(
                        original_title,
                        title_history
                    )

                    record_semantic_history(
                        final_title,
                        title_history
                    )

                    save_history(
                        hash_history,
                        title_history
                    )

                    print(
                        f"PUBLISHED: "
                        f"{final_title}"
                    )

                    return True

            except Exception as e:

                print(
                    f"Image processing error: "
                    f"{e}"
                )

                try:
                    os.remove(
                        downloaded
                    )
                except Exception:
                    pass

    # ========================================================
    # TEXT FALLBACK
    # ========================================================
    # Media is preferred, but missing/broken article media must never
    # silently discard an otherwise valid news story. Video stories remain
    # protected above and are not converted to a misleading text post.

    success = send_message(
        caption
    )

    if success:

        hash_history.add(
            history_key
        )

        record_semantic_history(
            original_title,
            title_history
        )

        record_semantic_history(
            final_title,
            title_history
        )

        save_history(
            hash_history,
            title_history
        )

        print(
            f"PUBLISHED TEXT: "
            f"{final_title}"
        )

        return True

    print(
        "FAILED TO PUBLISH"
    )

    return False


# ============================================================
# MAIN
# ============================================================

def main():

    start_time = time.time()

    hash_history, title_history = load_history()

    print(
        f"Old hash history: "
        f"{len(hash_history)}"
    )

    print(
        f"Semantic history: "
        f"{len(title_history)}"
    )

    candidates = collect_candidates(
        hash_history,
        title_history
    )

    if not candidates:

        print(
            "No fresh unused candidates found."
        )

        return

    published = 0
    selected = []

    # ========================================================
    # SOFT DIVERSITY SELECTION
    #
    # Category repetition is now a penalty, not a hard block.
    # A genuinely important breaking story can still pass.
    # ========================================================

    remaining = list(
        candidates
    )

    # Publish every genuinely new, valid candidate selected by the quality,
    # freshness, semantic-dedup, and diversity pipeline. There is no arbitrary
    # per-run quota: 0 new stories means 0 posts; 10 valid stories means 10 posts.
    while remaining:

        best = None
        best_effective_score = None

        for candidate in remaining:

            title = candidate.get(
                "title",
                ""
            )

            # Current-run semantic duplicate.
            duplicate = False

            for used in selected:

                if same_story(
                    candidate,
                    used
                ):

                    duplicate = True

                    break

            if duplicate:
                continue

            # Recent history.
            if history_contains_story(
                title,
                title_history
            ):
                continue

            # Effective score.
            base_score = candidate.get(
                "importance",
                0
            )

            penalty = diversity_penalty(
                candidate,
                selected
            )