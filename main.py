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
# NABZ KHABAR BOT v13
# STRONG SEMANTIC DEDUPLICATION
# GOOGLE NEWS DISCOVERY
# GEMINI + VIDEO + PHOTO + TEXT + WATERMARK
# ============================================================

print("=" * 64)
print("NABZ KHABAR BOT v12")
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

# Only reasonably fresh news.
MAX_NEWS_AGE_HOURS = 36

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
    # Additional free publisher feeds for broader coverage.
    ("ایران", "https://www.tabnak.ir/fa/rss/allnews"),
    ("ایران", "https://www.khabaronline.ir/rss"),
    ("ایران", "https://www.tasnimnews.com/fa/rss/feed/0/8/0/%D9%85%D9%87%D9%85%D8%AA%D8%B1%DB%8C%D9%86-%D8%AE%D8%A8%D8%B1%D8%A7%DB%8C-%D8%AA%D8%B3%D9%86%DB%8C%D9%85"),
    ("ایران", "https://www.asriran.com/fa/rss/allnews"),
    ("ایران", "https://www.entekhab.ir/fa/rss/allnews"),
    ("اقتصاد", "https://donya-e-eqtesad.com/fa/feeds/?p=all"),
    ("بین الملل", "https://www.iranpress.com/rss"),
    ("جهان", "https://www.iranintl.com/en/feed"),
    ("جهان", "https://irannewsdaily.com/feed/"),
    ("جهان", "https://www.theguardian.com/world/iran/rss"),
    ("جهان", "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml"),
]



# ============================================================
# GOOGLE NEWS DISCOVERY
# ============================================================

GOOGLE_NEWS_FEEDS = [
    ("ایران", google_news_search_url("ایران")),
    ("خبر فوری", google_news_search_url("خبر فوری ایران")),
    ("خبر مهم", google_news_search_url("خبر مهم ایران")),
    ("رویترز", google_news_search_url("Reuters Iran world news")),
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
    ("مسکن", google_news_search_url("مسکن اجاره خانه ایران")),
    ("کار", google_news_search_url("حقوق دستمزد اشتغال ایران")),
    ("آموزش", google_news_search_url("آموزش دانشگاه مدرسه کنکور ایران")),
    ("هواشناسی", google_news_search_url("هواشناسی ایران بارندگی")),
    ("انرژی", google_news_search_url("برق گاز انرژی ایران")),
    ("بانک", google_news_search_url("بانک مرکزی نرخ بهره ایران")),
    ("گمرک", google_news_search_url("تجارت واردات صادرات ایران")),
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


# ============================================================
# SOURCE QUALITY
# ============================================================

HIGH_QUALITY_HOSTS = {
    "irna.ir",
    "isna.ir",
    "mehrnews.com",
    "yjc.ir",
    "zoomit.ir",
    "digiato.com",
    "tasnimnews.com",
    "farsnews.ir",
    "khabaronline.ir",
    "irinn.ir",
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
}


MEDIUM_QUALITY_HOSTS = {
    "israelhayom.com",
    "theguardian.com",
    "nytimes.com",
    "washingtonpost.com",
    "cnn.com",
    "dw.com",
    "france24.com",
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
    "روابط عمومی",
    "روابط‌عمومی",
    "در اطلاعیه ای",
    "در اطلاعیه‌ای",
    "در بیانیه ای",
    "در بیانیه‌ای",
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

    # Remove common PR / promotional boilerplate.
    promotional_patterns = [
        r"برای کسب اطلاعات بیشتر",
        r"جهت کسب اطلاعات بیشتر",
        r"برای خرید",
        r"جهت خرید",
        r"ثبت ?نام کنید",
        r"همین حالا",
        r"کلیک کنید",
        r"لینک زیر",
        r"با ما همراه باشید",
        r"ما را دنبال کنید",
        r"اسپانسر",
        r"تبلیغات",
    ]

    for pattern in promotional_patterns:
        text = re.sub(pattern, "", text, flags=re.I)

    # Remove dateline / attribution fragments left after source cleanup.
    text = re.sub(
        r"^(?:[آ-یA-Za-z]+\s*){1,4}[,:-]\s*",
        "",
        text,
        count=1
    )

    # Repair repeated punctuation and spacing.
    text = re.sub(r"[ ]{2,}", " ", text)
    text = re.sub(r"([،,:؛])\1+", r"\1", text)
    text = re.sub(r"([.!؟])\1+", r"\1", text)
    text = re.sub(r"\s+([،,:؛.!؟])", r"\1", text)
    text = re.sub(r"([،,:؛])(?=[آ-یA-Za-z])", r"\1 ", text)

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

    # Remove repeated urgency / source punctuation artifacts.
    title = re.sub(r"(?:^|\s)(فوری)(?:\s+فوری)+", r" \1", title)
    title = re.sub(r"\s*[|｜]+\s*", " - ", title)
    title = re.sub(r"\s*[-–—:]\s*$", "", title)
    title = re.sub(r"[.!؟]+$", "", title)
    title = re.sub(r"\s{2,}", " ", title)

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
    """Primary identity: canonical article URL.
    Title is deliberately excluded so Gemini title changes cannot
    make the same article look new.
    """
    canonical_link = canonicalize_url(link)

    if not canonical_link:
        canonical_link = normalize_space(title)

    return hashlib.sha256(
        canonical_link.encode("utf-8")
    ).hexdigest()


def make_legacy_history_key(title, link):
    """Old v11/v12 title+URL hash kept for backward compatibility."""
    canonical_link = canonicalize_url(link)
    value = normalize_space(title) + "|" + canonical_link
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


def history_key_exists(title, link, hash_history):
    """Check both the new URL-only identity and old stored identity."""
    primary = make_history_key(title, link)
    if primary in hash_history:
        return True

    legacy = make_legacy_history_key(title, link)
    return legacy in hash_history


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

    return min(
        score,
        40
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


def calculate_hot_news_signal(candidate):
    """Return True for fresh, high-urgency stories; avoid labeling ordinary news as hot."""
    title = candidate.get("title", "")
    body = candidate.get("summary", "")
    keyword_score = calculate_keyword_importance(title, body)
    recency_score = calculate_recency_score(candidate.get("published_at"))
    cluster_size = candidate.get("cluster_size", 1)

    if keyword_score >= 8 and recency_score >= 8:
        return True

    if keyword_score >= 16 and recency_score >= 5:
        return True

    if cluster_size >= 2 and keyword_score >= 8 and recency_score >= 5:
        return True

    return False


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

    candidate["is_hot"] = calculate_hot_news_signal(candidate)

    if candidate.get("is_hot"):
        score += 18

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
            timeout=12,
            allow_redirects=True,
            stream=True
        )

        final_url = response.url

        try:
            response.close()
        except Exception:
            pass

        final_url = canonicalize_url(
            final_url
        )

        if (
            final_url
            and not is_google_host(
                final_url
            )
            and not is_social_host(
                final_url
            )
        ):
            return final_url

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

        text = max(
            candidates,
            key=len
        )

        return clean_content(
            text
        )[:6000]

    except Exception as e:

        print(
            f"Article fetch error: {e}"
        )

        return ""


# ============================================================
# CANONICAL ARTICLE URL
# ============================================================

def extract_canonical_article_url(url):
    """Return the publisher canonical URL or og:url for an article page."""

    if not url or is_google_host(url) or is_social_host(url):
        return ""

    try:
        response = SESSION.get(
            url,
            timeout=15,
            allow_redirects=True,
        )

        if response.status_code != 200:
            return ""

        content_type = response.headers.get(
            "content-type",
            "",
        ).lower()

        if "text/html" not in content_type:
            return ""

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        canonical = soup.find(
            "link",
            attrs={"rel": lambda value: value and "canonical" in value},
        )

        if canonical:
            value = canonical.get("href", "").strip()
            value = absolute_url(value, response.url)
            value = canonicalize_url(value)
            if value and not is_google_host(value) and not is_social_host(value):
                return value

        og_url = soup.find(
            "meta",
            attrs={"property": "og:url"},
        )

        if og_url:
            value = og_url.get("content", "").strip()
            value = absolute_url(value, response.url)
            value = canonicalize_url(value)
            if value and not is_google_host(value) and not is_social_host(value):
                return value

        final_url = canonicalize_url(response.url)
        if final_url and not is_google_host(final_url) and not is_social_host(final_url):
            return final_url

    except Exception as e:
        print(f"Canonical URL extraction failed: {e}")

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

    try:

        response = SESSION.get(
            url,
            timeout=ARTICLE_TIMEOUT,
            stream=True,
            allow_redirects=True
        )

        if response.status_code != 200:
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

                    try:
                        f.close()
                        os.remove(
                            filename
                        )
                    except Exception:
                        pass

                    return ""

                f.write(
                    chunk
                )

        if total == 0:

            try:
                os.remove(
                    filename
                )
            except Exception:
                pass

            return ""

        return filename

    except Exception as e:

        print(
            f"Download error: {e}"
        )

        try:

            if os.path.exists(
                filename
            ):
                os.remove(
                    filename
                )

        except Exception:
            pass

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

    try:

        image = Image.open(
            input_path
        ).convert(
            "RGBA"
        )

        image = resize_for_telegram(
            image
        )

        width, height = image.size

        if width >= 1400:
            font_size = 20
        elif width >= 1000:
            font_size = 18
        elif width >= 700:
            font_size = 16
        else:
            font_size = 14

        font = find_font(
            font_size,
            bold=True
        )

        draw = ImageDraw.Draw(
            image,
            "RGBA"
        )

        bbox = draw.textbbox(
            (0, 0),
            WATERMARK_TEXT,
            font=font
        )

        text_width = (
            bbox[2] - bbox[0]
        )

        text_height = (
            bbox[3] - bbox[1]
        )

        margin = max(
            10,
            int(width * 0.012)
        )

        x = (
            width
            - text_width
            - margin
        )

        y = (
            height
            - text_height
            - margin
        )

        pad_x = 6
        pad_y = 3

        draw.rounded_rectangle(
            [
                x - pad_x,
                y - pad_y,
                x + text_width + pad_x,
                y + text_height + pad_y
            ],
            radius=5,
            fill=(0, 0, 0, 75)
        )

        draw.text(
            (x + 1, y + 1),
            WATERMARK_TEXT,
            font=font,
            fill=(0, 0, 0, 120)
        )

        draw.text(
            (x, y),
            WATERMARK_TEXT,
            font=font,
            fill=(255, 255, 255, 190)
        )

        image = image.convert(
            "RGB"
        )

        image.save(
            output_path,
            "JPEG",
            quality=90,
            optimize=True
        )

        return output_path

    except Exception as e:

        print(
            f"Watermark error: {e}"
        )

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


def send_video(
    path,
    caption
):

    try:

        with open(
            path,
            "rb"
        ) as video:

            response = SESSION.post(
                telegram_api(
                    "sendVideo"
                ),
                data={
                    "chat_id": CHANNEL_ID,
                    "caption": caption,
                    "supports_streaming": "true",
                },
                files={
                    "video": video
                },
                timeout=120
            )

        if response.ok:

            print(
                "VIDEO PUBLISHED"
            )

            return True

        print(
            f"sendVideo failed: "
            f"{response.status_code} "
            f"{response.text[:500]}"
        )

    except Exception as e:

        print(
            f"sendVideo error: {e}"
        )

    return False


# ============================================================
# CAPTION
# ============================================================

def choose_news_emoji(title, body):
    """Choose one clean emoji based on the main topic of the news."""

    text = normalize_space(
        f"{title} {body}"
    ).lower()

    # Urgent incidents take priority over ordinary categories.
    urgent_keywords = [
        "خبر فوری", "فوری", "انفجار", "حمله", "موشک", "جنگ",
        "زلزله", "سیل", "آتش سوزی", "آتش‌سوزی", "سقوط",
        "تصادف", "کشته", "مفقود", "ترور", "حادثه مهم"
    ]
    if any(k in text for k in urgent_keywords):
        return "🚨"

    categories = [
        ("⚽", ["فوتبال", "ورزش", "لیگ", "جام جهانی", "المپیک", "تیم ملی", "بازیکن", "مربی", "آرسنال", "استقلال", "پرسپولیس"]),
        ("💵", ["دلار", "ارز", "یورو", "پوند", "نرخ ارز"]),
        ("🪙", ["طلا", "سکه", "اونس طلا", "طلای ۱۸", "طلای 24", "طلای ۲۴"]),
        ("📈", ["بورس", "شاخص کل", "فرابورس", "سهام", "معاملات بورس"]),
        ("🤖", ["هوش مصنوعی", "هوش مصنوعی", "ai", "gemini", "chatgpt", "مدل زبانی"]),
        ("📱", ["موبایل", "گوشی", "اینترنت", "اپلیکیشن", "اندروید", "آیفون", "ios", "شبکه اجتماعی"]),
        ("🚗", ["خودرو", "ماشین", "خودروساز", "خودروهای وارداتی", "خودرو برقی"]),
        ("🏥", ["سلامت", "پزشکی", "بیمارستان", "دارو", "درمان", "پزشک"]),
        ("🌦️", ["هواشناسی", "آب و هوا", "بارندگی", "بارش", "دما", "هوا"]),
        ("₿", ["بیت کوین", "اتریوم", "ارز دیجیتال", "کریپتو", "رمزارز", "crypto"]),
        ("🛢️", ["نفت", "گاز", "انرژی", "بنزین", "برق", "سوخت", "پالایشگاه"]),
        ("🔬", ["علم", "دانش", "پژوهش", "فضا", "ناسا", "نجوم", "آزمایش"]),
        ("🎬", ["سینما", "فیلم", "سریال", "بازیگر", "هنر", "موسیقی", "فرهنگ"]),
        ("🎓", ["دانشگاه", "مدرسه", "آموزش", "دانشجو", "کنکور", "معلم"]),
        ("🌍", ["جهان", "آمریکا", "اروپا", "روسیه", "اوکراین", "چین", "خاورمیانه", "بین‌الملل", "بین الملل"]),
        ("🇮🇷", ["ایران", "تهران", "مجلس", "دولت", "وزارتخانه", "استاندار", "استان"]),
    ]

    for emoji, keywords in categories:
        if any(k in text for k in keywords):
            return emoji

    return "⚡"




def build_caption(title, body, is_hot=False):
    title = clean_title(title)
    body = enforce_short_summary(body)
    emoji = choose_news_emoji(title, body)
    hot_prefix = "🔥 " if is_hot and emoji != "🚨" else ""

    if body:
        return (
            f"{hot_prefix}{emoji} {title}\n\n"
            f"{body}\n\n"
            f"#نبض_خبر"
        )

    return (
        f"{hot_prefix}{emoji} {title}\n\n"
        f"#نبض_خبر"
    )

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
3. نام رسانه، نام خبرگزاری، لینک، عبارت «به گزارش»، تاریخ‌گذاری ابتدای خبر، عبارت‌های روابط عمومی، بیانیه و اطلاعیه، متن تبلیغاتی و فراخوان‌های تبلیغاتی را حذف کن.
4. اگر متن ناقص است، چیزی را حدس نزن.
5. لحن کاملاً خبری، خنثی و حرفه‌ای باشد.
6. از اغراق، کلیک‌بیت و نظر شخصی خودداری کن.
7. اگر عنوان اصلی مناسب است، آن را بی‌دلیل تغییر نده.
8. فقط اطلاعات موجود در متن را استفاده کن.
9. هیچ نام، عدد، علت، نقل‌قول یا جزئیات جدیدی اختراع نکن.
10. متن را از عبارت‌های تبلیغاتی، روابط عمومی و معرفی خدمات پاک نگه دار.

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
# RSS COLLECTION
# ============================================================

def collect_feed(
    category,
    url,
    is_google=False
):

    candidates = []

    try:

        response = SESSION.get(
            url,
            timeout=REQUEST_TIMEOUT
        )

        response.raise_for_status()

        feed = feedparser.parse(
            response.content
        )

        print(
            f"RSS OK: {category} | "
            f"{len(feed.entries)} | "
            f"{url}"
        )

        for entry in feed.entries[:15]:

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

            published_at = parse_entry_time(
                entry
            )

            if not is_fresh(
                published_at
            ):

                print(
                    f"SKIPPED OLD: "
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

    for category, url in DIRECT_RSS_FEEDS:

        items = collect_feed(
            category,
            url,
            is_google=False
        )

        all_candidates.extend(
            items
        )

    # --------------------------------------------------------
    # Google discovery
    # --------------------------------------------------------

    for category, url in GOOGLE_NEWS_FEEDS:

        items = collect_feed(
            category,
            url,
            is_google=True
        )

        all_candidates.extend(
            items
        )

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

        if history_key_exists(title, link, hash_history):

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

    for item in clustered[:90]:

        if not item.get(
            "is_google"
        ):
            continue

        link = item.get(
            "link",
            ""
        )

        resolved = resolve_google_news_url(
            link
        )

        if resolved:

            item["resolved_link"] = resolved

            if (
                not is_social_host(
                    resolved
                )
                and not is_google_host(
                    resolved
                )
            ):

                item["link"] = resolved

                resolved_count += 1

        # DO NOT use source_url as an article URL.
        # Google source_url is often just publisher homepage.
        if not item.get(
            "resolved_link"
        ):

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

        if (
            item.get(
                "is_google"
            )
            and not item.get(
                "resolved_link"
            )
        ):

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

        if history_key_exists(title, link, hash_history):
            continue

        final_candidates.append(
            item
        )

    clustered = final_candidates

    if os.getenv("HOT_ONLY", "0").strip() == "1":
        clustered = [
            item for item in clustered
            if item.get("is_hot", False)
        ]
        print(f"HOT-ONLY MODE: {len(clustered)} hot candidates remain")

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
# V13 QUALITY GATE
# ============================================================

QUALITY_PR_PATTERNS = [
    r"\bروابط\s*عمومی\b",
    r"\bروابط‌عمومی\b",
    r"\bمراسم\b",
    r"\bگرامیداشت\b",
    r"\bتجلیل\b",
    r"\bتبریک\b",
    r"\bتسلیت\b",
    r"\bهمایش\b",
    r"\bنشست\b",
    r"\bدیدار\b",
    r"\bبالندگی\b",
    r"\bپویایی\b",
    r"\bافتخار\b",
    r"\bدستاوردهای\b",
    r"\bدرخشان\b",
    r"\bمردم‌سالاری\b",
    r"\bمردم سالاری\b",
]

QUALITY_CONCRETE_PATTERNS = [
    r"\bتصویب\b",
    r"\bتصمیم\b",
    r"\bاعلام کرد\b",
    r"\bگفت\b",
    r"\bآغاز\b",
    r"\bافتتاح\b",
    r"\bلغو\b",
    r"\bبازداشت\b",
    r"\bکشته\b",
    r"\bمصدوم\b",
    r"\bانفجار\b",
    r"\bآتش‌سوزی\b",
    r"\bتصادف\b",
    r"\bسقوط\b",
    r"\bقیمت\b",
    r"\bافزایش\b",
    r"\bکاهش\b",
    r"\bتغییر\b",
    r"\bاستخدام\b",
    r"\bتولید\b",
    r"\bعرضه\b",
    r"\bممنوع\b",
    r"\bتحریم\b",
    r"\bآتش‌بس\b",
    r"\bحمله\b",
    r"\bزلزله\b",
    r"\bسیل\b",
]

QUALITY_BAD_PATTERNS = [
    r"برای کسب اطلاعات بیشتر",
    r"جهت کسب اطلاعات بیشتر",
    r"کلیک کنید",
    r"همین حالا",
    r"ثبت\s*نام کنید",
    r"خرید کنید",
    r"فروش ویژه",
    r"تخفیف ویژه",
    r"اسپانسر",
    r"تبلیغات",
    r"https?://",
    r"www\.",
    r"t\.me/",
]

UNEXPECTED_SCRIPT_RE = re.compile(r"[\u0370-\u03ff\u0400-\u04ff\u0530-\u058f]")


def sanitize_public_text(text):
    if not text:
        return ""

    text = str(text)
    text = text.replace("\u200b", " ")
    text = text.replace("\u200c", " ")
    text = text.replace("\u200d", " ")
    text = text.replace("\u200e", " ")
    text = text.replace("\u200f", " ")
    text = text.replace("\ufeff", " ")
    text = text.replace("ي", "ی").replace("ى", "ی").replace("ك", "ک")
    text = UNEXPECTED_SCRIPT_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\s+([،,:؛.!؟])", r"\1", text)
    text = re.sub(r"([،,:؛])(?=[آ-یA-Za-z])", r"\1 ", text)
    text = re.sub(r"([.!؟])\1+", r"\1", text)
    return normalize_space(text)


def is_low_value_story(title, body):
    text = normalize_space(f"{title} {body}")
    low_hits = sum(bool(re.search(p, text, flags=re.I)) for p in QUALITY_PR_PATTERNS)
    if low_hits < 2:
        return False

    concrete = any(re.search(p, text, flags=re.I) for p in QUALITY_CONCRETE_PATTERNS)
    return not concrete


def quality_gate(candidate, final_title, final_summary):
    """Return (accepted, reason) for the final publishable text."""
    title = sanitize_public_text(final_title)
    summary = sanitize_public_text(final_summary)
    original = sanitize_public_text(candidate.get("title", ""))
    article_text = sanitize_public_text(candidate.get("article_text", ""))

    if not title or len(title) < 12:
        return False, "title_too_short"

    if len(title) > 180:
        return False, "title_too_long"

    if UNEXPECTED_SCRIPT_RE.search(title) or UNEXPECTED_SCRIPT_RE.search(summary):
        return False, "unexpected_script"

    for pattern in QUALITY_BAD_PATTERNS:
        if re.search(pattern, f"{title} {summary}", flags=re.I):
            return False, "advertising_or_link"

    if re.search(r"^(خبر|گزارش|آخرین اخبار|اخبار مهم|خبر مهم)$", title, flags=re.I):
        return False, "vague_title"

    title_words = [w for w in re.split(r"\s+", title) if len(w) > 1]
    if len(title_words) < 3 and len(original) >= 12:
        return False, "vague_title"

    if is_low_value_story(title, summary):
        return False, "low_value_pr"

    if article_text and not summary:
        return False, "empty_summary"

    if summary:
        if len(summary) < 25 and article_text:
            return False, "summary_too_short"
        if len(summary) > 650:
            return False, "summary_too_long"
        sentences = split_sentences(summary)
        if len(sentences) > 3:
            return False, "too_many_sentences"

    return True, "ok"


def quality_adjustment(candidate):
    """Deprioritize major single-source claims; do not hard-block them."""
    keyword_score = calculate_keyword_importance(
        candidate.get("title", ""),
        candidate.get("summary", "")
    )
    if candidate.get("cluster_size", 1) == 1 and keyword_score >= 16:
        return -3
    return 0


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

    if history_key_exists(
        original_title,
        link,
        hash_history
    ):

        print(
            "SKIPPED: URL history (duplicate article)"
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

    # --------------------------------------------------------
    # Canonical article URL duplicate guard.
    # --------------------------------------------------------

    canonical_article_url = ""

    if article_url:
        canonical_article_url = extract_canonical_article_url(
            article_url
        )

        if canonical_article_url:
            candidate["canonical_article_url"] = canonical_article_url

            if history_key_exists(
                original_title,
                canonical_article_url,
                hash_history,
            ):
                print(
                    "SKIPPED: canonical article URL history (duplicate article)"
                )
                return False

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

    if AI_API_KEY:

        ai_result = gemini_request(
            original_title,
            source_text
        )

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

        print(
            "Using local news engine."
        )

        local = local_news_engine(
            original_title,
            source_text
        )

        final_title = local[
            "title"
        ]

        final_summary = local[
            "summary"
        ]

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
    # V13 quality gate: never bypassed by hot-news mode.
    # --------------------------------------------------------

    quality_ok, quality_reason = quality_gate(
        candidate,
        final_title,
        final_summary,
    )

    if not quality_ok:
        print(
            f"QUALITY GATE BLOCKED: {quality_reason} | {final_title}"
        )
        return False

    # --------------------------------------------------------
    # Final semantic protection.
    # --------------------------------------------------------

    if history_contains_story(
        final_title,
        title_history
    ):

        print(
            "SKIPPED: final Gemini title "
            "matches recent history"
        )

        return False

    # --------------------------------------------------------
    # Also check original vs final.
    # If Gemini accidentally creates a title extremely
    # close to another selected story, block it later too.
    # --------------------------------------------------------

    caption = build_caption(
        final_title,
        final_summary,
        candidate.get("is_hot", False),
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

                if canonical_article_url:
                    hash_history.add(
                        make_history_key(
                            original_title,
                            canonical_article_url,
                        )
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

                add_watermark(
                    downloaded,
                    watermarked
                )

                success = send_photo(
                    watermarked,
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

    while (
        remaining
        and published < MAX_NEWS_PER_RUN
    ):

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

            effective_score = (
                base_score
                - penalty
            )

            if (
                best is None
                or effective_score
                > best_effective_score
            ):

                best = candidate
                best_effective_score = effective_score

        if best is None:
            break

        remaining.remove(
            best
        )

        print(
            f"\nSELECTED: "
            f"[{best.get('importance', 0)}] "
            f"{best.get('category', '')} - "
            f"{best.get('title', '')}"
        )

        success = process_news(
            best,
            hash_history,
            title_history
        )

        if success:

            published += 1

            selected.append(
                best
            )

            time.sleep(
                1
            )

    # ========================================================
    # FINAL STATS
    # ========================================================

    elapsed = (
        time.time()
        - start_time
    )

    print(
        "\n"
        + "=" * 64
    )

    print(
        f"FINISHED - Published: "
        f"{published}"
    )

    print(
        f"Runtime: "
        f"{elapsed:.1f}s"
    )

    print(
        f"Semantic history now: "
        f"{len(title_history)}"
    )

    print(
        "=" * 64
    )


if __name__ == "__main__":
    main()
