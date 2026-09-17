import os
import re
import io
import json
import time
import hashlib
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

GEMINI_MODEL = "gemini-3.5-flash-lite"

MAX_NEWS_PER_RUN = int(
    os.getenv("MAX_NEWS_PER_RUN", "4")
)

REQUEST_TIMEOUT = 20
ARTICLE_TIMEOUT = 25

MAX_VIDEO_MB = 49
MAX_IMAGE_MB = 12

MAX_NEWS_AGE_HOURS = 36
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
print(f"Max news/run: {MAX_NEWS_PER_RUN}")
print(f"Freshness window: {MAX_NEWS_AGE_HOURS}h")
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
# URL CANONICALIZATION
# ============================================================

TRACKING_PARAMETERS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term",
    "utm_content", "utm_name", "gclid", "fbclid", "mc_cid",
    "mc_eid", "ref", "referrer", "source", "output",
}


def canonicalize_url(url):
    if not url:
        return ""
    try:
        parsed = urlparse(clean_url(url))
        scheme = (parsed.scheme or "https").lower()
        host = (parsed.netloc or "").lower()
        if host.startswith("www."):
            host = host[4:]
        path = parsed.path or "/"
        if path != "/":
            path = path.rstrip("/")
        query_items = parse_qsl(parsed.query, keep_blank_values=True)
        filtered = []
        for key, value in query_items:
            key_lower = key.lower()
            if key_lower in TRACKING_PARAMETERS or key_lower.startswith("utm_"):
                continue
            filtered.append((key, value))
        filtered.sort()
        query = urlencode(filtered, doseq=True)
        return urlunparse((scheme, host, path, "", query, ""))
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
        "facebook.com", "fb.com", "fbcdn.net", "x.com", "twitter.com",
        "twimg.com", "youtube.com", "youtu.be", "tiktok.com", "instagram.com",
        "telegram.me", "t.me"
    )
    return any(host == x or host.endswith("." + x) for x in social_hosts)


def is_bad_media_url(url):
    if not url:
        return True
    host = get_hostname(url)
    bad_hosts = (
        "googleusercontent.com", "gstatic.com", "google.com",
        "facebook.com", "fbcdn.net", "twitter.com", "twimg.com", "x.com"
    )
    return any(host == x or host.endswith("." + x) for x in bad_hosts)


def looks_like_video_url(url):
    if not url:
        return False
    value = url.lower().split("?")[0]
    return value.endswith((".mp4", ".webm", ".mov", ".m4v"))


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
    )


# ============================================================
# DIRECT RSS
# ============================================================

DIRECT_RSS_FEEDS = [
    ("ایران", "https://www.irna.ir/rss"),
    ("فناوری", "https://www.zoomit.ir/feed/"),
    ("ایران", "https://www.mehrnews.com/rss"),
    ("ایران", "https://www.isna.ir/rss"),
    ("اقتصاد", "https://www.isna.ir/rss/service/economy"),
    ("ورزش", "https://www.isna.ir/rss?serviceid=5"),
    ("جهان", "https://www.irna.ir/rss/service/world"),
    ("فناوری", "https://digiato.com/feed"),
    ("ایران", "https://www.yjc.ir/fa/rss/allnews"),
    ("فرهنگ", "https://www.irna.ir/rss/service/culture"),
    ("اجتماعی", "https://www.irna.ir/rss/service/society"),
    ("جهان", "https://www.isna.ir/rss/service/world"),
]


# ============================================================
# GOOGLE NEWS DISCOVERY
# ============================================================

GOOGLE_NEWS_FEEDS = [
    ("ایران", google_news_search_url("ایران")),
    ("خبر فوری", google_news_search_url("خبر فوری ایران")),
    ("خبر مهم", google_news_search_url("خبر مهم ایران")),
    ("حوادث", google_news_search_url("حادثه انفجار تصادف سقوط آتش سوزی ایران")),
    ("اقتصاد", google_news_search_url("اقتصاد ایران")),
    ("دلار", google_news_search_url("قیمت دلار بازار ایران")),
    ("ارز", google_news_search_url("قیمت ارز ایران")),
    ("طلا", google_news_search_url("قیمت طلا ایران")),
    ("سکه", google_news_search_url("قیمت سکه ایران")),
    ("بورس", google_news_search_url("بورس ایران")),
    ("نفت", google_news_search_url("نفت انرژی ایران")),
    ("هوش مصنوعی", google_news_search_url("هوش مصنوعی AI")),
    ("فناوری", google_news_search_url("فناوری تکنولوژی")),
    ("موبایل", google_news_search_url("موبایل گوشی")),
    ("خودرو", google_news_search_url("خودرو ماشین")),
    ("ورزش", google_news_search_url("ورزش فوتبال")),
    ("سلامت", google_news_search_url("سلامت پزشکی")),
    ("علم", google_news_search_url("علم دانش")),
    ("فرهنگ", google_news_search_url("فرهنگ هنر سینما")),
    ("جامعه", google_news_search_url("جامعه اجتماعی")),
    ("کریپتو", google_news_search_url("ارز دیجیتال بیت کوین کریپتو")),
]


# ============================================================
# IMPORTANCE
# ============================================================

VERY_IMPORTANT_KEYWORDS = [
    "خبر فوری", "فوری", "انفجار", "حمله", "جنگ", "موشک", "حمله موشکی",
    "زلزله", "سیل", "آتش سوزی", "آتش‌سوزی", "هواپیما", "سقوط", "کشته",
    "مفقود", "ترور", "تحریم", "هسته ای", "هسته‌ای", "مذاکرات", "آتش بس",
    "آتش‌بس", "قطعی اینترنت", "قطع اینترنت",
]

IMPORTANT_KEYWORDS = [
    "ایران", "تهران", "دلار", "طلا", "سکه", "بورس", "اقتصاد", "قیمت",
    "بنزین", "نفت", "برق", "گاز", "هوش مصنوعی", "فناوری", "موبایل",
    "خودرو", "فوتبال", "ورزش", "پزشکی", "سلامت", "دانشگاه", "مدرسه",
    "جهان", "آمریکا", "اروپا", "اسرائیل", "روسیه", "اوکراین", "چین",
]


# ============================================================
# SOURCE QUALITY
# ============================================================

HIGH_QUALITY_HOSTS = {
    "irna.ir", "isna.ir", "mehrnews.com", "yjc.ir", "zoomit.ir", "digiato.com",
    "tasnimnews.com", "farsnews.ir", "khabaronline.ir", "irinn.ir", "snn.ir",
    "tabnak.ir", "tejaratnews.com", "donya-e-eqtesad.com", "ecoiran.com",
    "varzesh3.com", "bbc.com", "reuters.com", "apnews.com", "aljazeera.com",
    "euronews.com",
}

MEDIUM_QUALITY_HOSTS = {
    "israelhayom.com", "theguardian.com", "nytimes.com", "washingtonpost.com",
    "cnn.com", "dw.com", "france24.com",
}


def publisher_quality(url):
    host = base_domain(get_hostname(url))
    if not host:
        return 0
    if is_social_host(url):
        return -40
    if is_google_host(url):
        return -50
    for domain in HIGH_QUALITY_HOSTS:
        if host == domain or host.endswith("." + domain):
            return 25
    for domain in MEDIUM_QUALITY_HOSTS:
        if host == domain or host.endswith("." + domain):
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
    )
})


# ============================================================
# CAPTION
# ============================================================

def build_caption(title, body):
    title = clean_title(title)
    body = enforce_short_summary(body)
    footer = "@NabzKhabarOfficial"
    if body:
        return f"📰 {title}\n\n{body}\n\n{footer}"
    return f"📰 {title}\n\n{footer}"


# ============================================================
# WATERMARK
# ============================================================

def find_font(size, bold=True):
    if bold:
        candidates = ["Vazirmatn-Bold.ttf", "./Vazirmatn-Bold.ttf"]
    else:
        candidates = ["Vazirmatn-Regular.ttf", "./Vazirmatn-Regular.ttf"]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def resize_for_telegram(image):
    width, height = image.size
    ratio = min(MAX_OUTPUT_IMAGE_WIDTH / width, MAX_OUTPUT_IMAGE_HEIGHT / height, 1.0)
    if ratio >= 1:
        return image
    return image.resize(
        (max(1, int(width * ratio)), max(1, int(height * ratio))),
        Image.Resampling.LANCZOS,
    )


def add_watermark(input_path, output_path):
    try:
        image = Image.open(input_path).convert("RGBA")
        image = resize_for_telegram(image)
        width, height = image.size
        font_size = 20 if width >= 1400 else 18 if width >= 1000 else 16 if width >= 700 else 14
        font = find_font(font_size, bold=True)
        draw = ImageDraw.Draw(image, "RGBA")
        bbox = draw.textbbox((0, 0), WATERMARK_TEXT, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        margin = max(10, int(width * 0.012))
        x = width - text_width - margin
        y = height - text_height - margin
        draw.rounded_rectangle(
            [x - 6, y - 3, x + text_width + 6, y + text_height + 3],
            radius=5,
            fill=(0, 0, 0, 75),
        )
        draw.text((x + 1, y + 1), WATERMARK_TEXT, font=font, fill=(0, 0, 0, 120))
        draw.text((x, y), WATERMARK_TEXT, font=font, fill=(255, 255, 255, 190))
        image.convert("RGB").save(output_path, "JPEG", quality=90, optimize=True)
        return output_path
    except Exception as e:
        print(f"Watermark error: {e}")
        return input_path


# ============================================================
# TELEGRAM
# ============================================================

def telegram_api(method):
    return f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"


def send_message(text):
    try:
        response = SESSION.post(
            telegram_api("sendMessage"),
            data={"chat_id": CHANNEL_ID, "text": text, "disable_web_page_preview": True},
            timeout=REQUEST_TIMEOUT,
        )
        if response.ok:
            return True
        print(f"sendMessage failed: {response.status_code} {response.text[:500]}")
    except Exception as e:
        print(f"sendMessage error: {e}")
    return False


def send_photo(path, caption):
    try:
        with open(path, "rb") as photo:
            response = SESSION.post(
                telegram_api("sendPhoto"),
                data={"chat_id": CHANNEL_ID, "caption": caption},
                files={"photo": photo},
                timeout=REQUEST_TIMEOUT,
            )
        if response.ok:
            print("PHOTO PUBLISHED")
            return True
        print(f"sendPhoto failed: {response.status_code} {response.text[:500]}")
    except Exception as e:
        print(f"sendPhoto error: {e}")
    return False


def send_video(path, caption):
    try:
        with open(path, "rb") as video:
            response = SESSION.post(
                telegram_api("sendVideo"),
                data={"chat_id": CHANNEL_ID, "caption": caption, "supports_streaming": "true"},
                files={"video": video},
                timeout=120,
            )
        if response.ok:
            print("VIDEO PUBLISHED")
            return True
        print(f"sendVideo failed: {response.status_code} {response.text[:500]}")
    except Exception as e:
        print(f"sendVideo error: {e}")
    return False
