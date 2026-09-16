import os
import re
import io
import json
import time
import hashlib
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, quote_plus, urljoin

import requests
import feedparser
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont


# ============================================================
# NABZ KHABAR BOT v10
# SMART NEWS DEDUPLICATION + GOOGLE NEWS DISCOVERY
# GEMINI + VIDEO + PHOTO + TEXT + WATERMARK
# ============================================================

print("=" * 64)
print("NABZ KHABAR BOT v10")
print("SMART DEDUPLICATION + FRESH NEWS FILTER")
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

# News older than this is normally ignored.
# This prevents old RSS items from suddenly appearing.
MAX_NEWS_AGE_HOURS = 36

# Same story is considered recently published for this period.
# This is separate from the old hash history.
SEMANTIC_HISTORY_DAYS = 7

HISTORY_FILE = "sent_news.txt"

WATERMARK_TEXT = "نبض خبر | NABZ"

# Standardize images before applying watermark.
# This prevents huge 4K watermarks.
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
]


# ============================================================
# GOOGLE NEWS SEARCH FEEDS
#
# IMPORTANT:
# Google News /topics/... endpoints were returning 400.
# They are deliberately removed in v10.
# Google News is used for DISCOVERY only.
# ============================================================

GOOGLE_NEWS_FEEDS = [
    ("ایران", google_news_search_url("ایران")),
    ("خبر فوری", google_news_search_url("خبر فوری ایران")),
    ("خبر مهم", google_news_search_url("خبر مهم ایران")),
    ("حوادث", google_news_search_url(
        "حادثه انفجار تصادف سقوط آتش سوزی ایران"
    )),
    ("اقتصاد", google_news_search_url(
        "اقتصاد ایران"
    )),
    ("دلار", google_news_search_url(
        "قیمت دلار بازار ایران"
    )),
    ("ارز", google_news_search_url(
        "قیمت ارز ایران"
    )),
    ("طلا", google_news_search_url(
        "قیمت طلا ایران"
    )),
    ("سکه", google_news_search_url(
        "قیمت سکه ایران"
    )),
    ("بورس", google_news_search_url(
        "بورس ایران"
    )),
    ("نفت", google_news_search_url(
        "نفت انرژی ایران"
    )),
    ("هوش مصنوعی", google_news_search_url(
        "هوش مصنوعی AI"
    )),
    ("فناوری", google_news_search_url(
        "فناوری تکنولوژی"
    )),
    ("موبایل", google_news_search_url(
        "موبایل گوشی"
    )),
    ("خودرو", google_news_search_url(
        "خودرو ماشین"
    )),
    ("ورزش", google_news_search_url(
        "ورزش فوتبال"
    )),
    ("سلامت", google_news_search_url(
        "سلامت پزشکی"
    )),
    ("علم", google_news_search_url(
        "علم دانش"
    )),
    ("فرهنگ", google_news_search_url(
        "فرهنگ هنر سینما"
    )),
    ("جامعه", google_news_search_url(
        "جامعه اجتماعی"
    )),
    ("کریپتو", google_news_search_url(
        "ارز دیجیتال بیت کوین کریپتو"
    )),
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

    title = normalize_space(title)

    for pattern in ROUNDUP_PATTERNS:
        if re.search(pattern, title, re.I):
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

    text = normalize_space(text)

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

    text = normalize_space(text)

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

    title = normalize_space(title)

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

    return normalize_space(title)[:180]


# ============================================================
# SENTENCE HELPERS
# ============================================================

def split_sentences(text):
    if not text:
        return []

    text = normalize_space(text)

    parts = re.split(
        r"(?<=[\.\!\؟\?؛])\s+",
        text
    )

    result = []

    for item in parts:
        item = normalize_space(item)

        if len(item) >= 15:
            result.append(item)

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
    text = clean_content(text)

    if not text:
        return ""

    sentences = split_sentences(text)

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
            selected.append(sentence)

    return " ".join(selected)[:600].strip()


# ============================================================
# HISTORY
#
# Old file compatibility:
# - old lines are hashes
# - new lines:
#   TITLE|timestamp|title
# ============================================================

def load_history():
    hash_history = set()
    title_history = []

    if not os.path.exists(HISTORY_FILE):
        return hash_history, title_history

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

                # New semantic history format
                if line.startswith("TITLE|"):

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

                # Old hash format
                hash_history.add(
                    normalize_space(line)
                )

    except Exception as e:
        print(
            f"History load error: {e}"
        )

    return hash_history, title_history


def save_history(hash_history, title_history):
    try:

        # Keep old hashes.
        # Keep only recent semantic titles.
        cutoff = int(
            (
                datetime.now(timezone.utc)
                - timedelta(
                    days=SEMANTIC_HISTORY_DAYS
                )
            ).timestamp()
        )

        recent_titles = []

        for timestamp, title in title_history:

            if timestamp >= cutoff:
                recent_titles.append(
                    (
                        timestamp,
                        clean_title(title)
                    )
                )

        # Remove exact duplicate title records.
        seen_titles = set()
        cleaned_titles = []

        for timestamp, title in sorted(
            recent_titles,
            key=lambda x: x[0]
        ):

            key = normalize_space(
                title
            ).lower()

            if not key or key in seen_titles:
                continue

            seen_titles.add(key)

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


def make_history_key(title, link):
    value = (
        normalize_space(title)
        + "|"
        + normalize_space(link)
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

        tokens.add(token)

    return tokens


def story_tokens(title):
    tokens = title_tokens(title)

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

    return intersection / union


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
        intersection / union
    )

    containment = intersection / min(
        len(A),
        len(B)
    )

    # Weighted toward containment.
    return (
        jaccard * 0.45
        + containment * 0.55
    )


def same_story(a, b):
    title_a = a.get(
        "title",
        ""
    )

    title_b = b.get(
        "title",
        ""
    )

    similarity = story_similarity(
        title_a,
        title_b
    )

    if similarity >= 0.70:
        return True

    A = story_tokens(
        title_a
    )

    B = story_tokens(
        title_b
    )

    common = A & B

    # Strong entity/event overlap.
    if len(common) >= 4:
        if similarity >= 0.52:
            return True

    # Short titles need a stricter rule.
    if len(A) <= 3 or len(B) <= 3:
        return (
            title_similarity(
                title_a,
                title_b
            ) >= 0.80
        )

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

    cutoff = now - int(
        SEMANTIC_HISTORY_DAYS
        * 86400
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
            entry.get("published_parsed")
            or entry.get("updated_parsed")
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


def is_fresh(published_at):
    if not published_at:
        return True

    try:

        now = datetime.now(
            timezone.utc
        )

        age_hours = (
            now - published_at
        ).total_seconds() / 3600

        # Future timestamps are accepted.
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
        candidate.get("published_at")
    )

    score += source_priority(
        candidate.get("link", ""),
        candidate.get("is_google", False)
    )

    if candidate.get(
        "video_url"
    ):
        score += 3

    if candidate.get(
        "image_url"
    ):
        score += 2

    if candidate.get(
        "resolved_link"
    ):
        score += 5

    if is_social_host(
        candidate.get("link", "")
    ):
        score -= 30

    if is_google_host(
        candidate.get("link", "")
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
            candidate["cluster_size"],
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
        return url

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

        if (
            final_url
            and not is_google_host(final_url)
            and not is_social_host(final_url)
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

def fetch_article(url):
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
                img.get("data-src")
                or img.get("data-original")
                or img.get("data-lazy-src")
                or img.get("src")
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
                    looks_like_video_url(url)
                    and not is_bad_media_url(url)
                ):
                    return url

        for source in soup.select(
            "video source, video"
        ):

            url = (
                source.get("src")
                or source.get("data-src")
                or ""
            )

            url = absolute_url(
                url,
                page_url
            )

            if (
                looks_like_video_url(url)
                and not is_bad_media_url(url)
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
                            looks_like_video_url(url)
                            and not is_bad_media_url(url)
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
        ).convert("RGBA")

        # Resize FIRST.
        # Watermark is therefore always consistent.
        image = resize_for_telegram(
            image
        )

        width, height = image.size

        # Small fixed watermark sizes
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

        # Very small translucent backing.
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

        # Soft shadow
        draw.text(
            (x + 1, y + 1),
            WATERMARK_TEXT,
            font=font,
            fill=(0, 0, 0, 120)
        )

        # Small subtle watermark
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

def build_caption(
    title,
    body
):
    title = clean_title(
        title
    )

    body = enforce_short_summary(
        body
    )

    if body:

        return (
            f"📰 {title}\n\n"
            f"{body}\n\n"
            f"#نبض_خبر"
        )

    return (
        f"📰 {title}\n\n"
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

        if text.startswith("```"):

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

            # Don't let old RSS items suddenly enter.
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

            # ------------------------------------------------
            # RSS media
            # ------------------------------------------------

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

            # ------------------------------------------------
            # RSS enclosure
            # ------------------------------------------------

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

            # ------------------------------------------------
            # Google News source metadata
            # ------------------------------------------------

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
                "link": raw_link,
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

def detect_cross_source_bonus(
    candidate,
    candidates
):
    bonus = 0

    checked = 0

    for other in candidates:

        if other is candidate:
            continue

        checked += 1

        if checked > 120:
            break

        similarity = story_similarity(
            candidate.get(
                "title",
                ""
            ),
            other.get(
                "title",
                ""
            )
        )

        if similarity >= 0.75:
            bonus += 5

        elif similarity >= 0.62:
            bonus += 2

    return min(
        bonus,
        10
    )


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

    # Sort better sources first.
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
            ) or datetime.min.replace(
                tzinfo=timezone.utc
            )
        ),
        reverse=True
    )

    for candidate in ordered:

        placed = False

        for cluster in clusters:

            # Compare against every item in the cluster,
            # not just cluster[0].
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

        # Transfer useful metadata from other versions.
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

def collect_candidates():
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
    # Google News discovery
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
            + normalize_space(
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
    # Initial importance
    # --------------------------------------------------------

    for item in all_candidates:

        item["importance"] = calculate_importance(
            item
        )

    # --------------------------------------------------------
    # Cluster stories
    # --------------------------------------------------------

    clustered = cluster_candidates(
        all_candidates
    )

    print(
        f"After story clustering: "
        f"{len(clustered)}"
    )

    # --------------------------------------------------------
    # Resolve only promising Google items.
    # --------------------------------------------------------

    clustered.sort(
        key=lambda x: (
            x.get(
                "importance",
                0
            ),
            x.get(
                "published_at"
            ) or datetime.min.replace(
                tzinfo=timezone.utc
            )
        ),
        reverse=True
    )

    for item in clustered[:70]:

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

            # Replace only with real publisher URLs.
            if (
                not is_social_host(
                    resolved
                )
                and not is_google_host(
                    resolved
                )
            ):

                item["link"] = resolved

        # If Google could not resolve to a real
        # publisher, try the source href.
        if (
            not item.get(
                "resolved_link"
            )
            and item.get(
                "source_url"
            )
        ):

            source_url = item.get(
                "source_url"
            )

            if (
                not is_google_host(
                    source_url
                )
                and not is_social_host(
                    source_url
                )
            ):

                item["resolved_link"] = source_url

    # --------------------------------------------------------
    # Recalculate quality.
    # --------------------------------------------------------

    for item in clustered:

        if item.get(
            "resolved_link"
        ):

            item["importance"] += 8

            if (
                not is_social_host(
                    item["resolved_link"]
                )
                and not is_google_host(
                    item["resolved_link"]
                )
            ):
                item["importance"] += 10

        item["importance"] += detect_cross_source_bonus(
            item,
            clustered
        )

        item["importance"] = calculate_importance(
            item
        )

    # --------------------------------------------------------
    # Final story clustering after URL resolution.
    # --------------------------------------------------------

    clustered = cluster_candidates(
        clustered
    )

    # --------------------------------------------------------
    # Final importance
    # --------------------------------------------------------

    for item in clustered:
        item["importance"] = calculate_importance(
            item
        )

    # --------------------------------------------------------
    # Final sort
    # --------------------------------------------------------

    clustered.sort(
        key=lambda x: (
            x.get(
                "importance",
                0
            ),
            x.get(
                "published_at"
            ) or datetime.min.replace(
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
# CATEGORY DIVERSITY
# ============================================================

def category_family(category):
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


def violates_run_diversity(
    candidate,
    selected
):
    family = category_family(
        candidate.get(
            "category",
            ""
        )
    )

    same_family_count = 0

    for item in selected:

        if category_family(
            item.get(
                "category",
                ""
            )
        ) == family:

            same_family_count += 1

    # Do not let the 4 posts become four copies
    # of the same subject area.
    #
    # One family may have up to 2 posts normally.
    if same_family_count >= 2:
        return True

    return False


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

    link = candidate.get(
        "link",
        ""
    )

    print(
        f"\nProcessing: "
        f"{original_title}"
    )

    # --------------------------------------------------------
    # Old exact hash check
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
    # NEW semantic history check
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
    # Best article URL
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
    # Article text
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
    # Image
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

    # Google News NEVER supplies the final image.
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

        # Direct RSS can be upgraded with article image.
        if article_url:

            article_image = extract_image_from_article(
                article_url
            )

            if article_image:
                image_url = article_image

    # Final safety.
    if not image_is_acceptable(
        image_url
    ):
        image_url = ""

    # --------------------------------------------------------
    # Video
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
    # Gemini
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
    # Final cleaning
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
    # SECOND semantic check
    #
    # Important:
    # Gemini may rewrite the title.
    # Check the final title too.
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

                hash_history.add(
                    history_key
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

    candidates = collect_candidates()

    if not candidates:

        print(
            "No candidates found."
        )

        return

    published = 0

    selected = []

    # --------------------------------------------------------
    # IMPORTANT:
    # We do not simply take candidates[:4].
    # We scan further to find fresh + non-repeated
    # + reasonably diverse news.
    # --------------------------------------------------------

    for candidate in candidates:

        if published >= MAX_NEWS_PER_RUN:
            break

        title = candidate.get(
            "title",
            ""
        )

        # ----------------------------------------------------
        # Semantic duplicate inside current run
        # ----------------------------------------------------

        duplicate_current_run = False

        for used in selected:

            if same_story(
                candidate,
                used
            ):

                duplicate_current_run = True

                print(
                    f"SKIPPED SAME STORY: "
                    f"{title}"
                )

                break

        if duplicate_current_run:
            continue

        # ----------------------------------------------------
        # Recent history
        # ----------------------------------------------------

        if history_contains_story(
            title,
            title_history
        ):

            print(
                f"SKIPPED RECENT HISTORY: "
                f"{title}"
            )

            continue

        # ----------------------------------------------------
        # Diversity
        # ----------------------------------------------------

        if violates_run_diversity(
            candidate,
            selected
        ):

            print(
                f"SKIPPED CATEGORY DENSITY: "
                f"{title}"
            )

            continue

        # ----------------------------------------------------
        # Publish
        # ----------------------------------------------------

        success = process_news(
            candidate,
            hash_history,
            title_history
        )

        if success:

            published += 1

            selected.append(
                candidate
            )

            time.sleep(
                1
            )

    # --------------------------------------------------------
    # If diversity prevented 4 posts,
    # make a second pass without the category restriction.
    # This prevents the channel from becoming artificially empty.
    # --------------------------------------------------------

    if published < MAX_NEWS_PER_RUN:

        for candidate in candidates:

            if published >= MAX_NEWS_PER_RUN:
                break

            if candidate in selected:
                continue

            title = candidate.get(
                "title",
                ""
            )

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

            if history_contains_story(
                title,
                title_history
            ):
                continue

            success = process_news(
                candidate,
                hash_history,
                title_history
            )

            if success:

                published += 1

                selected.append(
                    candidate
                )

                time.sleep(
                    1
                )

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
