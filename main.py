import os
import re
import io
import json
import time
import hashlib
import mimetypes
from datetime import datetime, timezone
from urllib.parse import urlparse, quote_plus

import requests
import feedparser
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont


# ============================================================
# NABZ KHABAR BOT v9
# GEMINI + GOOGLE NEWS + SMART SOURCE + VIDEO + WATERMARK
# ============================================================

print("=" * 60)
print("NABZ KHABAR BOT v9")
print("GEMINI + GOOGLE NEWS + SMART SOURCE")
print("VIDEO + PHOTO + TEXT + WATERMARK")
print("=" * 60)


# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
AI_API_KEY = os.getenv("AI_API_KEY", "").strip()

CHANNEL_ID = "@NabzKhabarOfficial"

GEMINI_MODEL = "gemini-3.5-flash-lite"

MAX_NEWS_PER_RUN = int(os.getenv("MAX_NEWS_PER_RUN", "4"))

REQUEST_TIMEOUT = 20
ARTICLE_TIMEOUT = 25

MAX_VIDEO_MB = 49
MAX_IMAGE_MB = 12

MAX_BODY_CHARS = 600
MAX_BODY_SENTENCES = 4

HISTORY_FILE = "sent_news.txt"

WATERMARK_TEXT = "نبض خبر | NABZ"


# ============================================================
# BASIC VALIDATION
# ============================================================

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")

print(f"Gemini enabled: {bool(AI_API_KEY)}")
print(f"Gemini model: {GEMINI_MODEL}")


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

    return url.strip()


def get_hostname(url):
    try:
        return urlparse(url).netloc.lower().split(":")[0]
    except Exception:
        return ""


def is_google_host(url):
    host = get_hostname(url)

    return (
        host == "news.google.com"
        or host.endswith(".google.com")
        or "googleusercontent.com" in host
    )


def is_social_host(url):
    host = get_hostname(url)

    social_hosts = (
        "facebook.com",
        "fb.com",
        "x.com",
        "twitter.com",
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

    return value.endswith((
        ".mp4",
        ".webm",
        ".mov",
        ".m4v"
    ))


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
# DIRECT RSS SOURCES
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
# GOOGLE NEWS FEEDS
# ============================================================

GOOGLE_NEWS_FEEDS = [
    ("گوگل نیوز", f"{GOOGLE_NEWS_BASE}?hl={GOOGLE_HL}&gl={GOOGLE_GL}&ceid={GOOGLE_CEID}"),

    ("جهان", f"{GOOGLE_NEWS_BASE}/topics/WORLD?hl={GOOGLE_HL}&gl={GOOGLE_GL}&ceid={GOOGLE_CEID}"),
    ("اقتصاد", f"{GOOGLE_NEWS_BASE}/topics/BUSINESS?hl={GOOGLE_HL}&gl={GOOGLE_GL}&ceid={GOOGLE_CEID}"),
    ("فناوری", f"{GOOGLE_NEWS_BASE}/topics/TECHNOLOGY?hl={GOOGLE_HL}&gl={GOOGLE_GL}&ceid={GOOGLE_CEID}"),
    ("ورزش", f"{GOOGLE_NEWS_BASE}/topics/SPORTS?hl={GOOGLE_HL}&gl={GOOGLE_GL}&ceid={GOOGLE_CEID}"),
    ("سلامت", f"{GOOGLE_NEWS_BASE}/topics/HEALTH?hl={GOOGLE_HL}&gl={GOOGLE_GL}&ceid={GOOGLE_CEID}"),
    ("علم", f"{GOOGLE_NEWS_BASE}/topics/SCIENCE?hl={GOOGLE_HL}&gl={GOOGLE_GL}&ceid={GOOGLE_CEID}"),
    ("فرهنگ", f"{GOOGLE_NEWS_BASE}/topics/ENTERTAINMENT?hl={GOOGLE_HL}&gl={GOOGLE_GL}&ceid={GOOGLE_CEID}"),

    ("ایران", google_news_search_url("ایران")),
    ("خبر فوری", google_news_search_url("خبر فوری ایران")),
    ("خبر مهم", google_news_search_url("خبر مهم ایران")),
    ("حوادث", google_news_search_url("حادثه انفجار تصادف ایران")),
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
# IMPORTANCE KEYWORDS
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


def base_domain(host):
    host = (host or "").lower()

    if host.startswith("www."):
        host = host[4:]

    return host


def publisher_quality(url):
    host = base_domain(get_hostname(url))

    if not host:
        return 0

    if is_social_host(url):
        return -30

    if is_google_host(url):
        return -35

    for domain in HIGH_QUALITY_HOSTS:
        if host == domain or host.endswith("." + domain):
            return 25

    for domain in MEDIUM_QUALITY_HOSTS:
        if host == domain or host.endswith("." + domain):
            return 15

    return 5


# ============================================================
# HTTP SESSION
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
# SOURCE / DATELINE CLEANING
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

    text = BeautifulSoup(str(text), "html.parser").get_text(" ")

    text = normalize_space(text)

    # Remove obvious RSS/source prefixes
    text = re.sub(
        r"^(مشهد|تهران|قم|تبریز|اصفهان|شیراز|کرج|اهواز|بغداد|واشنگتن|لندن)"
        r"\s*[-–—:]\s*",
        "",
        text,
        flags=re.I
    )

    for phrase in SOURCE_PHRASES:
        text = text.replace(phrase, "")

    # Remove common source markers
    text = re.sub(
        r"\b(ایرنا|ایسنا|مهر|باشگاه خبرنگاران جوان|خبرگزاری)\s*[:：-]",
        "",
        text,
        flags=re.I
    )

    # Remove media markers
    text = re.sub(
        r"\+\s*(فیلم|ویدئو|ویدیو|عکس|تصاویر)\s*$",
        "",
        text,
        flags=re.I
    )

    text = normalize_space(text)

    return text[:3000]


# ============================================================
# TITLE CLEANING
# ============================================================

def clean_title(title):
    if not title:
        return ""

    title = BeautifulSoup(str(title), "html.parser").get_text(" ")

    title = normalize_space(title)

    # Remove Google News publisher suffix
    title = re.sub(
        r"\s*[-|]\s*(facebook\.com|twitter\.com|x\.com|youtube\.com)\s*$",
        "",
        title,
        flags=re.I
    )

    # Common Google News publisher suffixes
    title = re.sub(
        r"\s+-\s+[A-Za-z0-9._-]+\.[A-Za-z]{2,}$",
        "",
        title
    )

    # Remove source names at the beginning
    title = re.sub(
        r"^(ایرنا|ایسنا|مهر|فارس|تسنیم|یعنی چه|باشگاه خبرنگاران جوان)"
        r"\s*[-|:：]\s*",
        "",
        title,
        flags=re.I
    )

    # Remove + فیلم / + عکس
    title = re.sub(
        r"\s*\+\s*(فیلم|ویدئو|ویدیو|عکس|تصاویر)\s*$",
        "",
        title,
        flags=re.I
    )

    title = normalize_space(title)

    return title[:180]


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

    if any(x in sentence for x in ["اعلام کرد", "گفت", "تصمیم", "تصویب", "تأیید"]):
        score += 1

    return score


def enforce_short_summary(text):
    text = clean_content(text)

    if not text:
        return ""

    sentences = split_sentences(text)

    if not sentences:
        return text[:MAX_BODY_CHARS]

    selected = []

    first = sentences[0]

    selected.append(first)

    remaining = sentences[1:]

    remaining = sorted(
        remaining,
        key=sentence_score,
        reverse=True
    )

    for sentence in remaining:
        if len(selected) >= MAX_BODY_SENTENCES:
            break

        candidate = " ".join(selected + [sentence])

        if len(candidate) <= MAX_BODY_CHARS:
            selected.append(sentence)

    result = " ".join(selected)

    return result[:MAX_BODY_CHARS].strip()


# ============================================================
# HISTORY
# ============================================================

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return set()

    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return {
                normalize_space(x)
                for x in f.read().splitlines()
                if normalize_space(x)
            }
    except Exception:
        return set()


def save_history(history):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            for item in sorted(history):
                f.write(item + "\n")
    except Exception as e:
        print(f"History save error: {e}")


def make_history_key(title, link):
    value = normalize_space(title) + "|" + normalize_space(link)

    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


# ============================================================
# TITLE SIMILARITY
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
}


def title_tokens(title):
    title = normalize_digits(title)
    title = clean_title(title).lower()

    title = re.sub(
        r"[^\w\u0600-\u06ff]+",
        " ",
        title
    )

    tokens = {
        x for x in title.split()
        if len(x) >= 2 and x not in STOPWORDS
    }

    return tokens


def title_similarity(a, b):
    A = title_tokens(a)
    B = title_tokens(b)

    if not A or not B:
        return 0

    intersection = len(A & B)
    union = len(A | B)

    if union == 0:
        return 0

    return intersection / union


def detect_cross_source_bonus(candidate, candidates):
    title = candidate.get("title", "")

    bonus = 0

    checked = 0

    for other in candidates:
        if other is candidate:
            continue

        checked += 1

        if checked > 80:
            break

        similarity = title_similarity(
            title,
            other.get("title", "")
        )

        if similarity >= 0.72:
            bonus += 5

        elif similarity >= 0.58:
            bonus += 2

    return min(bonus, 10)


# ============================================================
# STORY CLUSTERING
# ============================================================

def same_story(a, b):
    similarity = title_similarity(
        a.get("title", ""),
        b.get("title", "")
    )

    if similarity >= 0.70:
        return True

    A = title_tokens(a.get("title", ""))
    B = title_tokens(b.get("title", ""))

    common = A & B

    if len(common) >= 4 and similarity >= 0.50:
        return True

    return False


def choose_cluster_representative(cluster):
    if not cluster:
        return None

    def score(item):
        value = 0

        value += publisher_quality(item.get("link", ""))

        if item.get("is_google"):
            value -= 20

        if item.get("resolved_link"):
            value += 8

        if item.get("article_text"):
            value += 5

        if item.get("image_url"):
            value += 3

        if item.get("video_url"):
            value += 4

        value += item.get("importance", 0)

        return value

    return max(cluster, key=score)


def cluster_candidates(candidates):
    clusters = []

    for candidate in candidates:
        placed = False

        for cluster in clusters:
            representative = cluster[0]

            if same_story(candidate, representative):
                cluster.append(candidate)
                placed = True
                break

        if not placed:
            clusters.append([candidate])

    result = []

    for cluster in clusters:
        representative = choose_cluster_representative(cluster)

        if representative:
            # If a direct publisher version exists in the cluster,
            # prefer its metadata.
            for item in cluster:
                if not item.get("is_google"):
                    if publisher_quality(item.get("link", "")) > publisher_quality(
                        representative.get("link", "")
                    ):
                        representative = item

            representative["cluster_size"] = len(cluster)

            result.append(representative)

    return result


# ============================================================
# DATE / IMPORTANCE
# ============================================================

def parse_entry_time(entry):
    try:
        parsed = entry.get("published_parsed") or entry.get("updated_parsed")

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

    return datetime.now(timezone.utc)


def calculate_keyword_importance(title, body):
    text = f"{title} {body}"

    score = 0

    for word in VERY_IMPORTANT_KEYWORDS:
        if word in text:
            score += 8

    for word in IMPORTANT_KEYWORDS:
        if word in text:
            score += 3

    return min(score, 40)


def calculate_recency_score(dt):
    try:
        now = datetime.now(timezone.utc)

        age_hours = (
            now - dt
        ).total_seconds() / 3600

        if age_hours < 1:
            return 10

        if age_hours < 3:
            return 8

        if age_hours < 6:
            return 6

        if age_hours < 12:
            return 4

        if age_hours < 24:
            return 2

    except Exception:
        pass

    return 0


def source_priority(url, is_google=False):
    score = publisher_quality(url)

    if is_google:
        score -= 10

    return score


def calculate_importance(candidate):
    title = candidate.get("title", "")
    body = candidate.get("summary", "")

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

    if candidate.get("video_url"):
        score += 3

    if candidate.get("image_url"):
        score += 2

    if candidate.get("resolved_link"):
        score += 5

    # Social/aggregator penalty
    if is_social_host(candidate.get("link", "")):
        score -= 20

    if is_google_host(candidate.get("link", "")):
        score -= 10

    if is_roundup_title(title):
        score -= 25

    # Multi-source confirmation
    if candidate.get("cluster_size", 1) >= 2:
        score += min(candidate["cluster_size"], 4) * 2

    return score


# ============================================================
# GOOGLE NEWS REDIRECT RESOLUTION
# ============================================================

def resolve_google_news_url(url):
    if not url:
        return ""

    if not is_google_host(url):
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

        if final_url and not is_google_host(final_url):
            return final_url

    except Exception as e:
        print(f"Google URL resolve failed: {e}")

    return ""


# ============================================================
# ARTICLE FETCH
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

        # Remove unwanted elements
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

        for selector in [
            "article",
            "[itemprop='articleBody']",
            ".article-body",
            ".article__body",
            ".news-body",
            ".news-content",
            ".content",
            "main"
        ]:
            for node in soup.select(selector):
                text = normalize_space(
                    node.get_text(" ", strip=True)
                )

                if len(text) > 150:
                    candidates.append(text)

        if not candidates:
            paragraphs = []

            for p in soup.find_all("p"):
                text = normalize_space(
                    p.get_text(" ", strip=True)
                )

                if len(text) >= 40:
                    paragraphs.append(text)

            candidates.append(
                " ".join(paragraphs)
            )

        if not candidates:
            return ""

        text = max(
            candidates,
            key=len
        )

        return clean_content(text)[:6000]

    except Exception as e:
        print(f"Article fetch error: {e}")
        return ""


# ============================================================
# IMAGE EXTRACTION
# ============================================================

def absolute_url(url, base):
    if not url:
        return ""

    try:
        from urllib.parse import urljoin
        return urljoin(base, url)
    except Exception:
        return url


def image_is_acceptable(url):
    if not url:
        return False

    if is_bad_media_url(url):
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
        "google-news"
    ]

    for word in bad_words:
        if word in lower:
            return False

    return True


def extract_image_from_html(html, page_url):
    if not html:
        return ""

    try:
        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        # Priority order:
        # og:image -> twitter:image -> large image in article

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
                attrs={attr: value}
            )

            if tag:
                url = tag.get("content", "").strip()

                url = absolute_url(
                    url,
                    page_url
                )

                if image_is_acceptable(url):
                    return url

        # Article images
        article_nodes = soup.select(
            "article img, main img, [itemprop='articleBody'] img"
        )

        best = ""

        for img in article_nodes:
            src = (
                img.get("data-src")
                or img.get("data-original")
                or img.get("src")
                or ""
            )

            src = absolute_url(
                src,
                page_url
            )

            if not image_is_acceptable(src):
                continue

            width = 0
            height = 0

            try:
                width = int(img.get("width", 0))
            except Exception:
                pass

            try:
                height = int(img.get("height", 0))
            except Exception:
                pass

            if width >= 500 or height >= 300:
                return src

            if not best:
                best = src

        return best

    except Exception:
        return ""


def extract_image_from_article(url):
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
        print(f"Image extraction error: {e}")
        return ""


# ============================================================
# VIDEO EXTRACTION
# ============================================================

def extract_video_from_html(html, page_url):
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
                attrs={attr: value}
            )

            if tag:
                url = tag.get("content", "").strip()

                url = absolute_url(
                    url,
                    page_url
                )

                if looks_like_video_url(url):
                    return url

        # video/source
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

            if looks_like_video_url(url):
                return url

        # JSON-LD
        for script in soup.find_all(
            "script",
            attrs={"type": "application/ld+json"}
        ):
            try:
                data = json.loads(
                    script.string or script.get_text()
                )

                objects = data

                if isinstance(data, dict):
                    objects = [data]

                if not isinstance(objects, list):
                    continue

                for obj in objects:
                    if not isinstance(obj, dict):
                        continue

                    for key in [
                        "contentUrl",
                        "embedUrl"
                    ]:
                        url = obj.get(key)

                        if not url:
                            continue

                        url = absolute_url(
                            url,
                            page_url
                        )

                        if looks_like_video_url(url):
                            return url

            except Exception:
                continue

    except Exception:
        pass

    return ""


def extract_video_from_article(url):
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
        print(f"Video extraction error: {e}")
        return ""


# ============================================================
# DOWNLOAD
# ============================================================

def download_file(url, filename, max_mb):
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

        content_type = response.headers.get(
            "content-type",
            ""
        ).lower()

        content_length = response.headers.get(
            "content-length"
        )

        if content_length:
            try:
                size_mb = int(content_length) / (
                    1024 * 1024
                )

                if size_mb > max_mb:
                    print(
                        f"File too large: {size_mb:.1f} MB"
                    )
                    return ""

            except Exception:
                pass

        total = 0

        with open(filename, "wb") as f:
            for chunk in response.iter_content(
                chunk_size=64 * 1024
            ):
                if not chunk:
                    continue

                total += len(chunk)

                if total > max_mb * 1024 * 1024:
                    print(
                        f"Download exceeded {max_mb} MB"
                    )

                    try:
                        f.close()
                        os.remove(filename)
                    except Exception:
                        pass

                    return ""

                f.write(chunk)

        if total == 0:
            try:
                os.remove(filename)
            except Exception:
                pass

            return ""

        return filename

    except Exception as e:
        print(f"Download error: {e}")

        try:
            if os.path.exists(filename):
                os.remove(filename)
        except Exception:
            pass

        return ""


# ============================================================
# WATERMARK
# ============================================================

def find_font(size, bold=True):
    candidates = []

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
        if os.path.exists(path):
            try:
                return ImageFont.truetype(
                    path,
                    size
                )
            except Exception:
                pass

    return ImageFont.load_default()


def add_watermark(input_path, output_path):
    try:
        image = Image.open(
            input_path
        ).convert("RGBA")

        width, height = image.size

        # ----------------------------------------------------
        # IMPORTANT:
        # Watermark is deliberately small and capped.
        # It will NOT grow excessively on 4K images.
        # ----------------------------------------------------

        if width >= 3000:
            font_size = 25
        elif width >= 2200:
            font_size = 24
        elif width >= 1600:
            font_size = 22
        elif width >= 1000:
            font_size = 20
        else:
            font_size = 18

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

        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        # Small proportional margin
        margin = max(
            12,
            min(
                int(width * 0.012),
                28
            )
        )

        x = width - text_width - margin
        y = height - text_height - margin

        # Small semi-transparent background
        pad_x = 8
        pad_y = 5

        draw.rounded_rectangle(
            [
                x - pad_x,
                y - pad_y,
                x + text_width + pad_x,
                y + text_height + pad_y
            ],
            radius=6,
            fill=(0, 0, 0, 100)
        )

        # Very subtle shadow
        draw.text(
            (x + 1, y + 1),
            WATERMARK_TEXT,
            font=font,
            fill=(0, 0, 0, 150)
        )

        # Main watermark
        draw.text(
            (x, y),
            WATERMARK_TEXT,
            font=font,
            fill=(255, 255, 255, 205)
        )

        image = image.convert("RGB")

        # Keep output reasonable
        image.save(
            output_path,
            "JPEG",
            quality=91,
            optimize=True
        )

        return output_path

    except Exception as e:
        print(f"Watermark error: {e}")
        return input_path


# ============================================================
# TELEGRAM
# ============================================================

def telegram_api(method):
    return (
        f"https://api.telegram.org/bot"
        f"{BOT_TOKEN}/{method}"
    )


def send_message(text):
    try:
        response = SESSION.post(
            telegram_api("sendMessage"),
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
        print(f"sendMessage error: {e}")

    return False


def send_photo(path, caption):
    try:
        with open(path, "rb") as photo:
            response = SESSION.post(
                telegram_api("sendPhoto"),
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
            print("PHOTO PUBLISHED")
            return True

        print(
            f"sendPhoto failed: "
            f"{response.status_code} "
            f"{response.text[:500]}"
        )

    except Exception as e:
        print(f"sendPhoto error: {e}")

    return False


def send_video(path, caption):
    try:
        with open(path, "rb") as video:
            response = SESSION.post(
                telegram_api("sendVideo"),
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
            print("VIDEO PUBLISHED")
            return True

        print(
            f"sendVideo failed: "
            f"{response.status_code} "
            f"{response.text[:500]}"
        )

    except Exception as e:
        print(f"sendVideo error: {e}")

    return False


# ============================================================
# TELEGRAM CAPTION
# ============================================================

def build_caption(title, body):
    title = clean_title(title)
    body = enforce_short_summary(body)

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

def gemini_request(title, article_text):
    if not AI_API_KEY:
        return None

    if not article_text:
        article_text = title

    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
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
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
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

        result = json.loads(text)

        final_title = clean_title(
            result.get("title", "")
        )

        final_summary = enforce_short_summary(
            result.get("summary", "")
        )

        if not final_title:
            final_title = clean_title(title)

        return {
            "title": final_title,
            "summary": final_summary
        }

    except Exception as e:
        print(f"Gemini exception: {e}")

    return None


# ============================================================
# LOCAL FALLBACK
# ============================================================

def local_news_engine(title, body):
    title = clean_title(title)

    body = clean_content(body)

    summary = enforce_short_summary(
        body
    )

    return {
        "title": title,
        "summary": summary
    }


# ============================================================
# RSS COLLECTION
# ============================================================

def collect_feed(category, url, is_google=False):
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
            f"{len(feed.entries)} | {url}"
        )

        for entry in feed.entries[:12]:

            raw_title = normalize_space(
                entry.get("title", "")
            )

            raw_link = clean_url(
                entry.get("link", "")
            )

            if not raw_title or not raw_link:
                continue

            title = clean_title(
                raw_title
            )

            if not title:
                continue

            if is_roundup_title(title):
                print(
                    f"SKIPPED ROUNDUP: {title}"
                )
                continue

            summary = clean_content(
                entry.get("summary", "")
                or entry.get("description", "")
            )

            published_at = parse_entry_time(
                entry
            )

            image_url = ""

            # RSS media
            media_content = entry.get(
                "media_content",
                []
            )

            for media in media_content:
                if not isinstance(media, dict):
                    continue

                media_url = media.get(
                    "url",
                    ""
                )

                if image_is_acceptable(
                    media_url
                ):
                    if not looks_like_video_url(
                        media_url
                    ):
                        image_url = media_url
                        break

            # RSS enclosure
            if not image_url:
                enclosures = entry.get(
                    "enclosures",
                    []
                )

                for enclosure in enclosures:
                    media_url = enclosure.get(
                        "href",
                        ""
                    ) or enclosure.get(
                        "url",
                        ""
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
                "article_text": "",
                "importance": 0,
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
# COLLECT ALL
# ============================================================

def collect_candidates():
    all_candidates = []

    # Direct sources
    for category, url in DIRECT_RSS_FEEDS:
        items = collect_feed(
            category,
            url,
            is_google=False
        )

        all_candidates.extend(
            items
        )

    # Google News
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
    # Remove exact duplicate links/titles
    # --------------------------------------------------------

    unique = {}

    for item in all_candidates:
        key = (
            normalize_space(
                item.get("title", "")
            ).lower()
            + "|"
            + normalize_space(
                item.get("link", "")
            ).lower()
        )

        if key not in unique:
            unique[key] = item

    all_candidates = list(
        unique.values()
    )

    # --------------------------------------------------------
    # First importance calculation
    # --------------------------------------------------------

    for item in all_candidates:
        item["importance"] = calculate_importance(
            item
        )

    # --------------------------------------------------------
    # Cluster similar stories
    # --------------------------------------------------------

    clustered = cluster_candidates(
        all_candidates
    )

    print(
        f"After story clustering: "
        f"{len(clustered)}"
    )

    # --------------------------------------------------------
    # Resolve only Google/social candidates
    # that have a realistic chance of being selected.
    # This avoids resolving hundreds of URLs.
    # --------------------------------------------------------

    clustered.sort(
        key=lambda x: (
            x.get("importance", 0),
            x.get("published_at") or datetime.min.replace(
                tzinfo=timezone.utc
            )
        ),
        reverse=True
    )

    for item in clustered[:50]:
        link = item.get("link", "")

        if item.get("is_google"):

            resolved = resolve_google_news_url(
                link
            )

            if resolved:
                item["resolved_link"] = resolved

                # Prefer publisher URL
                if not is_social_host(resolved):
                    item["link"] = resolved

        elif is_social_host(link):
            resolved = resolve_google_news_url(
                link
            )

            if resolved:
                item["resolved_link"] = resolved

    # --------------------------------------------------------
    # Recalculate quality after resolving URLs
    # --------------------------------------------------------

    for item in clustered:

        if item.get("resolved_link"):
            item["importance"] += 8

            # Direct publisher is much better
            if not is_social_host(
                item["resolved_link"]
            ):
                item["importance"] += 10

        if is_social_host(
            item.get("link", "")
        ):
            item["importance"] -= 20

        if is_google_host(
            item.get("link", "")
        ):
            item["importance"] -= 15

        item["importance"] += (
            detect_cross_source_bonus(
                item,
                clustered
            )
        )

    # --------------------------------------------------------
    # Remove duplicate stories again after resolution
    # --------------------------------------------------------

    final = []

    for item in clustered:

        duplicate = False

        for existing in final:
            if same_story(
                item,
                existing
            ):
                duplicate = True
                break

        if not duplicate:
            final.append(item)

    final.sort(
        key=lambda x: (
            x.get("importance", 0),
            x.get("published_at") or datetime.min.replace(
                tzinfo=timezone.utc
            )
        ),
        reverse=True
    )

    print(
        f"Candidates found: {len(final)}"
    )

    print("\nTOP PRIORITY NEWS:")

    for item in final[:10]:
        print(
            f"[{item.get('importance', 0)}] "
            f"{item.get('category', '')} - "
            f"{item.get('title', '')}"
        )

    return final


# ============================================================
# PROCESS NEWS
# ============================================================

def process_news(candidate, history):
    original_title = candidate.get(
        "title",
        ""
    )

    link = candidate.get(
        "link",
        ""
    )

    print(
        f"\nProcessing: {original_title}"
    )

    history_key = make_history_key(
        original_title,
        link
    )

    if history_key in history:
        print(
            "SKIPPED: already published"
        )
        return False

    # --------------------------------------------------------
    # Determine best article URL
    # --------------------------------------------------------

    article_url = (
        candidate.get("resolved_link")
        or candidate.get("link")
    )

    # If resolved URL is still social/Google,
    # do not use it as the article.
    if is_google_host(article_url):
        article_url = ""

    if is_social_host(article_url):
        article_url = ""

    # --------------------------------------------------------
    # Fetch article
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

    # Existing RSS image is accepted ONLY if
    # it does not look like Google/social garbage.
    rss_image = candidate.get(
        "image_url",
        ""
    )

    if image_is_acceptable(
        rss_image
    ):
        image_url = rss_image

    # For Google News, ALWAYS prefer actual publisher image.
    if candidate.get("is_google"):

        publisher_image = ""

        if article_url:
            publisher_image = extract_image_from_article(
                article_url
            )

        if publisher_image:
            image_url = publisher_image
        else:
            # Critical:
            # DO NOT use Google News thumbnail.
            image_url = ""

    else:
        # Direct RSS can also be upgraded with article image
        if article_url:
            article_image = extract_image_from_article(
                article_url
            )

            if article_image:
                image_url = article_image

    # --------------------------------------------------------
    # Video
    # --------------------------------------------------------

    video_url = ""

    if article_url:
        video_url = extract_video_from_article(
            article_url
        )

    # If RSS supplied a real video URL
    if not video_url:
        rss_video = candidate.get(
            "video_url",
            ""
        )

        if looks_like_video_url(
            rss_video
        ):
            video_url = rss_video

    # HLS is not directly sent to Telegram
    if is_hls_url(video_url):
        print(
            "HLS video skipped:"
            f" {video_url}"
        )
        video_url = ""

    # --------------------------------------------------------
    # Gemini
    # --------------------------------------------------------

    source_text = (
        article_text
        or candidate.get("summary", "")
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
            f"Gemini title: {final_title}"
        )

    else:
        print(
            "Using local news engine."
        )

        local = local_news_engine(
            original_title,
            source_text
        )

        final_title = local["title"]
        final_summary = local["summary"]

    # Safety cleaning
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

    caption = build_caption(
        final_title,
        final_summary
    )

    # --------------------------------------------------------
    # VIDEO FIRST
    # --------------------------------------------------------

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
                history.add(
                    history_key
                )

                save_history(
                    history
                )

                print(
                    f"PUBLISHED: {final_title}"
                )

                return True

    # --------------------------------------------------------
    # PHOTO
    # --------------------------------------------------------

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
                # Verify image
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
                    if watermarked != downloaded:
                        os.remove(
                            watermarked
                        )
                except Exception:
                    pass

                if success:

                    history.add(
                        history_key
                    )

                    save_history(
                        history
                    )

                    print(
                        f"PUBLISHED: {final_title}"
                    )

                    return True

            except Exception as e:
                print(
                    f"Image processing error: {e}"
                )

                try:
                    os.remove(
                        downloaded
                    )
                except Exception:
                    pass

    # --------------------------------------------------------
    # TEXT FALLBACK
    # --------------------------------------------------------

    success = send_message(
        caption
    )

    if success:

        history.add(
            history_key
        )

        save_history(
            history
        )

        print(
            f"PUBLISHED TEXT: {final_title}"
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

    history = load_history()

    print(
        f"History entries: "
        f"{len(history)}"
    )

    candidates = collect_candidates()

    if not candidates:
        print(
            "No candidates found."
        )
        return

    published = 0

    used_titles = []

    for candidate in candidates:

        if published >= MAX_NEWS_PER_RUN:
            break

        title = candidate.get(
            "title",
            ""
        )

        # Do not publish two extremely similar
        # stories during the same run.
        duplicate_current_run = False

        for used in used_titles:

            if title_similarity(
                title,
                used
            ) >= 0.68:

                duplicate_current_run = True

                print(
                    f"SKIPPED SAME RUN: "
                    f"{title}"
                )

                break

        if duplicate_current_run:
            continue

        success = process_news(
            candidate,
            history
        )

        if success:

            published += 1

            used_titles.append(
                title
            )

            # Small pause to avoid hammering APIs
            time.sleep(1)

    elapsed = time.time() - start_time

    print("\n" + "=" * 60)

    print(
        f"FINISHED - Published: "
        f"{published}"
    )

    print(
        f"Runtime: {elapsed:.1f}s"
    )

    print("=" * 60)


if __name__ == "__main__":
    main()
