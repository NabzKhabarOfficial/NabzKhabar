import os
import re
import json
import time
import hashlib
import html
import mimetypes
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, quote_plus

import requests
import feedparser
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont


# =========================================================
# CONFIG
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
AI_API_KEY = os.getenv("AI_API_KEY", "").strip()

CHANNEL_ID = "@NabzKhabarOfficial"

GEMINI_MODEL = "gemini-3.5-flash-lite"

MAX_NEWS_PER_RUN = int(os.getenv("MAX_NEWS_PER_RUN", "4"))

REQUEST_TIMEOUT = 20
ARTICLE_TIMEOUT = 25

MAX_VIDEO_MB = 49
MAX_IMAGE_MB = 15

MAX_BODY_CHARS = 600
MAX_BODY_SENTENCES = 4

HISTORY_FILE = "sent_news.txt"

FONT_BOLD = "Vazirmatn-Bold.ttf"
FONT_REGULAR = "Vazirmatn-Regular.ttf"


# =========================================================
# BASIC HELPERS
# IMPORTANT:
# normalize_space MUST appear before Google News feed creation.
# =========================================================

def normalize_space(text):
    if not text:
        return ""

    text = html.unescape(str(text))

    text = text.replace("\xa0", " ")
    text = text.replace("\u200c", "‌")
    text = text.replace("\u200f", "")
    text = text.replace("\u202a", "")
    text = text.replace("\u202b", "")
    text = text.replace("\u202c", "")

    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)

    return text.strip()


def absolute_url(base_url, url):
    if not url:
        return ""

    return urljoin(base_url, url.strip())


def make_id(title, link):
    raw = f"{normalize_space(title)}|{normalize_space(link)}"

    return hashlib.sha256(
        raw.encode("utf-8", errors="ignore")
    ).hexdigest()


def safe_filename(text, extension):
    text = re.sub(r"[^\w\-]+", "_", text or "file")
    text = text[:60].strip("_")

    if not text:
        text = "media"

    return f"{text}{extension}"


def parse_entry_time(entry):
    for field in ("published_parsed", "updated_parsed", "created_parsed"):
        value = getattr(entry, field, None)

        if value:
            try:
                return datetime(
                    value.tm_year,
                    value.tm_mon,
                    value.tm_mday,
                    value.tm_hour,
                    value.tm_min,
                    value.tm_sec,
                    tzinfo=timezone.utc
                )
            except Exception:
                pass

    return None


def split_sentences(text):
    text = normalize_space(text)

    if not text:
        return []

    parts = re.split(
        r"(?<=[\.\!\؟\!؛])\s+|(?<=\.)\s+",
        text
    )

    return [
        normalize_space(x)
        for x in parts
        if normalize_space(x)
    ]


# =========================================================
# DIRECT RSS SOURCES
# =========================================================

RSS_FEEDS = [
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
    ("جامعه", "https://www.irna.ir/rss/service/society"),
    ("جهان", "https://www.isna.ir/rss/service/world"),
]


# =========================================================
# GOOGLE NEWS
# =========================================================

GOOGLE_NEWS_BASE = "https://news.google.com/rss"

GOOGLE_HL = "fa"
GOOGLE_GL = "IR"
GOOGLE_CEID = "IR:fa"


def google_news_search_url(query):
    encoded = quote_plus(normalize_space(query))

    return (
        f"{GOOGLE_NEWS_BASE}/search?"
        f"q={encoded}"
        f"&hl={GOOGLE_HL}"
        f"&gl={GOOGLE_GL}"
        f"&ceid={GOOGLE_CEID}"
    )


GOOGLE_NEWS_FEEDS = [
    ("گوگل نیوز", f"{GOOGLE_NEWS_BASE}?hl={GOOGLE_HL}&gl={GOOGLE_GL}&ceid={GOOGLE_CEID}"),

    ("جهان", f"{GOOGLE_NEWS_BASE}/headlines/section/topic/WORLD?hl={GOOGLE_HL}&gl={GOOGLE_GL}&ceid={GOOGLE_CEID}"),
    ("اقتصاد", f"{GOOGLE_NEWS_BASE}/headlines/section/topic/BUSINESS?hl={GOOGLE_HL}&gl={GOOGLE_GL}&ceid={GOOGLE_CEID}"),
    ("فناوری", f"{GOOGLE_NEWS_BASE}/headlines/section/topic/TECHNOLOGY?hl={GOOGLE_HL}&gl={GOOGLE_GL}&ceid={GOOGLE_CEID}"),
    ("ورزش", f"{GOOGLE_NEWS_BASE}/headlines/section/topic/SPORTS?hl={GOOGLE_HL}&gl={GOOGLE_GL}&ceid={GOOGLE_CEID}"),
    ("سلامت", f"{GOOGLE_NEWS_BASE}/headlines/section/topic/HEALTH?hl={GOOGLE_HL}&gl={GOOGLE_GL}&ceid={GOOGLE_CEID}"),
    ("علم", f"{GOOGLE_NEWS_BASE}/headlines/section/topic/SCIENCE?hl={GOOGLE_HL}&gl={GOOGLE_GL}&ceid={GOOGLE_CEID}"),
    ("فرهنگ", f"{GOOGLE_NEWS_BASE}/headlines/section/topic/ENTERTAINMENT?hl={GOOGLE_HL}&gl={GOOGLE_GL}&ceid={GOOGLE_CEID}"),

    ("ایران", google_news_search_url("ایران")),
    ("خبر فوری ایران", google_news_search_url("ایران خبر فوری")),
    ("خبر مهم ایران", google_news_search_url("ایران خبر مهم")),
    ("حوادث", google_news_search_url("ایران حادثه")),
    ("اقتصاد", google_news_search_url("اقتصاد ایران")),
    ("دلار", google_news_search_url("دلار")),
    ("ارز", google_news_search_url("ارز دلار")),
    ("طلا", google_news_search_url("قیمت طلا")),
    ("سکه", google_news_search_url("قیمت سکه")),
    ("بورس", google_news_search_url("بورس تهران")),
    ("نفت", google_news_search_url("نفت انرژی")),
    ("هوش مصنوعی", google_news_search_url("هوش مصنوعی AI")),
    ("فناوری", google_news_search_url("فناوری تکنولوژی")),
    ("موبایل", google_news_search_url("موبایل گوشی")),
    ("خودرو", google_news_search_url("خودرو ماشین")),
    ("ورزش", google_news_search_url("ورزش فوتبال")),
    ("سلامت", google_news_search_url("سلامت پزشکی")),
    ("علم", google_news_search_url("علم دانش")),
    ("فرهنگ", google_news_search_url("فرهنگ هنر")),
    ("جامعه", google_news_search_url("جامعه آموزش")),
    ("رمزارز", google_news_search_url("ارز دیجیتال بیت کوین")),
]


# =========================================================
# IMPORTANCE KEYWORDS
# =========================================================

VERY_IMPORTANT_KEYWORDS = [
    "فوری",
    "خبر فوری",
    "فوق العاده مهم",
    "بسیار مهم",
    "انفجار",
    "زلزله",
    "سیل",
    "جنگ",
    "حمله",
    "حمله موشکی",
    "حمله هوایی",
    "کشته",
    "کشته شدن",
    "جان باخت",
    "جان‌باخت",
    "ترور",
    "حادثه مرگبار",
    "هشدار",
    "هشدار فوری",
    "تعطیلی",
    "قطعی",
    "بحران",
    "تصمیم مهم",
    "تصمیم فوری",
    "آتش بس",
    "آتش‌بس",
    "تحریم جدید",
    "تحریم",
    "انفجار بزرگ",
    "زلزله شدید",
]

IMPORTANT_KEYWORDS = [
    "رئیس جمهور",
    "رئیس‌جمهور",
    "دولت",
    "مجلس",
    "وزیر",
    "وزارت",
    "بانک مرکزی",
    "دلار",
    "طلا",
    "سکه",
    "بورس",
    "نفت",
    "بنزین",
    "سوخت",
    "تورم",
    "اقتصاد",
    "قیمت",
    "بازار",
    "انتخابات",
    "قانون",
    "مصوبه",
    "اروپا",
    "آمریکا",
    "روسیه",
    "چین",
    "اسرائیل",
    "غزه",
    "اوکراین",
    "فلسطین",
    "ایران",
    "فناوری",
    "هوش مصنوعی",
    "امنیت سایبری",
    "اینترنت",
    "موبایل",
    "سامسونگ",
    "اپل",
    "گوگل",
    "مایکروسافت",
    "فوتبال",
    "ورزش",
    "پزشکی",
    "سلامت",
]


# =========================================================
# ROUNDUP FILTER
# =========================================================

ROUNDUP_PATTERNS = [
    "خبرهایی از",
    "مروری بر",
    "مرور اخبار",
    "مهمترین اخبار",
    "مهم‌ترین اخبار",
    "اخبار مهم امروز",
    "اخبار مهم",
    "چه خبر از",
    "بسته خبری",
    "بسته اخبار",
    "در بسته خبری",
    "نگاهی به مهمترین",
    "نگاهی به مهم‌ترین",
    "اخبار این حوزه",
    "از مهمترین خبرها",
    "از مهم‌ترین خبرها",
    "آخرین اخبار",
]


def is_roundup_news(title):
    title = normalize_space(title).lower()

    for pattern in ROUNDUP_PATTERNS:
        if pattern.lower() in title:
            return True

    return False


# =========================================================
# HTTP SESSION
# =========================================================

SESSION = requests.Session()

SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.7",
})


# =========================================================
# CONTENT CLEANING
# =========================================================

def clean_content(text):
    if not text:
        return ""

    text = html.unescape(str(text))

    soup = BeautifulSoup(text, "html.parser")

    for tag in soup([
        "script",
        "style",
        "noscript",
        "iframe",
        "svg"
    ]):
        tag.decompose()

    text = soup.get_text(" ", strip=True)
    text = normalize_space(text)

    # Remove common source/dateline patterns.
    patterns = [
        r"^به گزارش خبرنگار [^،:؛\-]+[،:؛\-]\s*",
        r"^به گزارش [^،:؛\-]+[،:؛\-]\s*",
        r"^در گفت‌وگو با [^،:؛\-]+[،:؛\-]\s*",
        r"^در گفتگو با [^،:؛\-]+[،:؛\-]\s*",
        r"^به نقل از [^،:؛\-]+[،:؛\-]\s*",
        r"^مشهد-\S+-",
        r"^تهران-\S+-",
        r"^ایران-\S+-",
        r"^بغداد-\S+-",
        r"^لندن-\S+-",
        r"^واشنگتن-\S+-",
        r"^نیویورک-\S+-",
        r"^پاریس-\S+-",
    ]

    for pattern in patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)

    # Remove media markers.
    text = re.sub(
        r"\[(?:فیلم|ویدئو|ویدیو|عکس|تصویر|گزارش تصویری)[^\]]*\]",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"(?:فیلم|ویدئو|ویدیو)\s*[:\-]\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    # Remove excessive repeated spaces.
    text = normalize_space(text)

    return text[:5000]


# =========================================================
# HISTORY
# =========================================================

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return set()

    try:
        with open(
            HISTORY_FILE,
            "r",
            encoding="utf-8",
            errors="ignore"
        ) as f:
            return {
                line.strip()
                for line in f
                if line.strip()
            }
    except Exception:
        return set()


def save_history(history):
    try:
        with open(
            HISTORY_FILE,
            "w",
            encoding="utf-8"
        ) as f:
            for item in sorted(history):
                f.write(item + "\n")

    except Exception as e:
        print("History save error:", e)


# =========================================================
# SENTENCE / SUMMARY ENGINE
# =========================================================

def sentence_score(sentence):
    score = 0
    lower = sentence.lower()

    important_terms = VERY_IMPORTANT_KEYWORDS + IMPORTANT_KEYWORDS

    for keyword in important_terms:
        if keyword.lower() in lower:
            score += 3 if keyword in VERY_IMPORTANT_KEYWORDS else 1

    if any(char.isdigit() for char in sentence):
        score += 1

    if 40 <= len(sentence) <= 260:
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

    # Always keep the first useful sentence.
    first = sentences[0]

    if first:
        selected.append(first)

    remaining = sentences[1:]

    scored = sorted(
        enumerate(remaining),
        key=lambda x: (
            sentence_score(x[1]),
            -x[0]
        ),
        reverse=True
    )

    for _, sentence in scored:
        if len(selected) >= MAX_BODY_SENTENCES:
            break

        candidate = " ".join(selected + [sentence])

        if len(candidate) <= MAX_BODY_CHARS:
            selected.append(sentence)

    result = " ".join(selected)
    result = normalize_space(result)

    return result[:MAX_BODY_CHARS].rstrip()


# =========================================================
# TITLE CLEANING
# =========================================================

def clean_title(title):
    title = clean_content(title)

    # Remove leading media labels.
    title = re.sub(
        r"^(فیلم|ویدئو|ویدیو|عکس|تصویر)\s*[\:\|\-]\s*",
        "",
        title,
        flags=re.IGNORECASE
    )

    # Remove common source prefixes.
    title = re.sub(
        r"^(به گزارش[^:]+:)\s*",
        "",
        title,
        flags=re.IGNORECASE
    )

    title = re.sub(
        r"^[^:]{1,30}-(?:ایرنا|ایسنا|مهر|فارس|تسنیم)-\s*",
        "",
        title,
        flags=re.IGNORECASE
    )

    title = normalize_space(title)

    return title[:220].strip()


# =========================================================
# IMPORTANCE
# =========================================================

def calculate_keyword_importance(title, body):
    text = f"{title} {body}".lower()

    score = 0

    for keyword in VERY_IMPORTANT_KEYWORDS:
        if keyword.lower() in text:
            score += 15

    for keyword in IMPORTANT_KEYWORDS:
        if keyword.lower() in text:
            score += 4

    return score


def calculate_recency_score(entry):
    dt = parse_entry_time(entry)

    if not dt:
        return 0

    now = datetime.now(timezone.utc)

    try:
        age_hours = max(
            0,
            (now - dt).total_seconds() / 3600
        )
    except Exception:
        return 0

    if age_hours <= 1:
        return 20

    if age_hours <= 3:
        return 15

    if age_hours <= 6:
        return 10

    if age_hours <= 12:
        return 5

    if age_hours <= 24:
        return 2

    return 0


def source_priority(source_name):
    priorities = {
        "گوگل نیوز": 3,
        "ایران": 3,
        "جهان": 3,
        "اقتصاد": 3,
        "فناوری": 3,
        "ورزش": 2,
        "فرهنگ": 2,
        "جامعه": 2,
        "سلامت": 2,
        "علم": 2,
        "حوادث": 3,
        "دلار": 3,
        "طلا": 3,
        "سکه": 3,
        "بورس": 3,
        "نفت": 3,
        "رمزارز": 2,
        "موبایل": 2,
        "خودرو": 2,
    }

    return priorities.get(source_name, 1)


def calculate_importance(title, body, source_name, entry):
    score = 0

    score += calculate_keyword_importance(
        title,
        body
    )

    score += calculate_recency_score(entry)

    score += source_priority(source_name)

    if is_roundup_news(title):
        score -= 30

    return score


# =========================================================
# TITLE SIMILARITY / CROSS SOURCE
# =========================================================

def title_tokens(title):
    title = clean_title(title).lower()

    title = re.sub(
        r"[^\w\u0600-\u06ff]+",
        " ",
        title
    )

    stopwords = {
        "از",
        "به",
        "در",
        "با",
        "برای",
        "و",
        "که",
        "این",
        "آن",
        "یک",
        "را",
        "است",
        "شد",
        "شدند",
        "کرد",
        "کرده",
        "می",
        "شود",
        "شده",
    }

    return {
        token
        for token in title.split()
        if token and token not in stopwords
    }


def title_similarity(a, b):
    a_tokens = title_tokens(a)
    b_tokens = title_tokens(b)

    if not a_tokens or not b_tokens:
        return 0

    intersection = len(a_tokens & b_tokens)
    union = len(a_tokens | b_tokens)

    if union == 0:
        return 0

    return intersection / union


def detect_cross_source_bonus(candidate, candidates):
    bonus = 0

    for other in candidates:
        if other is candidate:
            continue

        similarity = title_similarity(
            candidate["title"],
            other["title"]
        )

        if similarity >= 0.65:
            bonus = 8
            break

    return bonus


# =========================================================
# GEMINI
# =========================================================

def gemini_request(title, content):
    if not AI_API_KEY:
        return None

    prompt = f"""
تو ویراستار حرفه‌ای یک کانال خبری فارسی هستی.

عنوان اولیه:
{title}

متن خبر:
{content}

وظیفه:
1. یک تیتر خبری کوتاه، دقیق و جذاب فارسی بنویس.
2. متن را فقط بر اساس اطلاعات موجود خلاصه کن.
3. هیچ واقعیت جدیدی اضافه نکن.
4. نام رسانه، نام خبرنگار، عبارت «به گزارش ...»، لینک و منبع را حذف کن.
5. متن تبلیغاتی و تکراری را حذف کن.
6. حداکثر 4 جمله بنویس.
7. لحن حرفه‌ای، خبری و بی‌طرف باشد.
8. اگر موضوع حساس سیاسی است، از قضاوت و تحلیل شخصی خودداری کن.
9. خروجی فقط JSON معتبر باشد.

فرمت:
{{
  "title": "تیتر",
  "summary": "خلاصه خبر"
}}
"""

    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"models/{GEMINI_MODEL}:generateContent"
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ]
    }

    try:
        response = SESSION.post(
            url,
            params={"key": AI_API_KEY},
            json=payload,
            timeout=ARTICLE_TIMEOUT
        )

        if response.status_code != 200:
            print(
                "Gemini HTTP error:",
                response.status_code,
                response.text[:500]
            )
            return None

        data = response.json()

        candidates = data.get(
            "candidates",
            []
        )

        if not candidates:
            return None

        parts = (
            candidates[0]
            .get("content", {})
            .get("parts", [])
        )

        text = ""

        for part in parts:
            if "text" in part:
                text += part["text"]

        text = text.strip()

        if not text:
            return None

        # Remove markdown code fences.
        text = re.sub(
            r"^```(?:json)?\s*",
            "",
            text,
            flags=re.IGNORECASE
        )

        text = re.sub(
            r"\s*```$",
            "",
            text
        )

        parsed = json.loads(text)

        new_title = clean_title(
            parsed.get("title", "")
        )

        summary = enforce_short_summary(
            parsed.get("summary", "")
        )

        if not new_title:
            new_title = clean_title(title)

        if not summary:
            summary = enforce_short_summary(content)

        return {
            "title": new_title,
            "summary": summary,
        }

    except Exception as e:
        print("Gemini error:", e)
        return None


# =========================================================
# LOCAL FALLBACK
# =========================================================

def local_news_engine(title, content):
    title = clean_title(title)
    summary = enforce_short_summary(content)

    if not summary:
        summary = title

    return {
        "title": title,
        "summary": summary
    }


# =========================================================
# ARTICLE EXTRACTION
# =========================================================

def fetch_article(url):
    if not url:
        return ""

    try:
        response = SESSION.get(
            url,
            timeout=ARTICLE_TIMEOUT,
            allow_redirects=True
        )

        if response.status_code >= 400:
            return ""

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        for tag in soup([
            "script",
            "style",
            "noscript",
            "iframe",
            "svg",
            "nav",
            "footer",
            "header"
        ]):
            tag.decompose()

        selectors = [
            "article",
            "[itemprop='articleBody']",
            ".article-body",
            ".article__body",
            ".news-body",
            ".news-text",
            ".content",
            ".post-content",
            ".entry-content",
            "main",
        ]

        for selector in selectors:
            node = soup.select_one(selector)

            if node:
                text = node.get_text(
                    " ",
                    strip=True
                )

                text = clean_content(text)

                if len(text) >= 100:
                    return text[:8000]

        paragraphs = soup.find_all("p")

        texts = []

        for p in paragraphs:
            text = clean_content(
                p.get_text(" ", strip=True)
            )

            if len(text) >= 40:
                texts.append(text)

        result = " ".join(texts)

        return result[:8000]

    except Exception as e:
        print("Article extraction error:", e)
        return ""


# =========================================================
# IMAGE EXTRACTION
# =========================================================

def extract_image_url(entry, article_url):
    # RSS media fields.
    media_content = entry.get("media_content", [])

    if isinstance(media_content, list):
        for item in media_content:
            if not isinstance(item, dict):
                continue

            url = (
                item.get("url")
                or item.get("href")
                or item.get("src")
            )

            if url:
                return absolute_url(
                    article_url,
                    url
                )

    media_thumbnail = entry.get(
        "media_thumbnail",
        []
    )

    if isinstance(media_thumbnail, list):
        for item in media_thumbnail:
            if not isinstance(item, dict):
                continue

            url = item.get("url")

            if url:
                return absolute_url(
                    article_url,
                    url
                )

    for link in entry.get("links", []):
        if not isinstance(link, dict):
            continue

        href = link.get("href", "")
        link_type = link.get("type", "")

        if href and link_type.startswith("image/"):
            return absolute_url(
                article_url,
                href
            )

    # Try article HTML.
    try:
        response = SESSION.get(
            article_url,
            timeout=ARTICLE_TIMEOUT
        )

        if response.status_code >= 400:
            return ""

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        meta_candidates = [
            ("meta", {"property": "og:image"}),
            ("meta", {"property": "og:image:url"}),
            ("meta", {"name": "twitter:image"}),
            ("meta", {"name": "twitter:image:src"}),
        ]

        for tag_name, attrs in meta_candidates:
            tag = soup.find(
                tag_name,
                attrs=attrs
            )

            if tag and tag.get("content"):
                return absolute_url(
                    article_url,
                    tag["content"]
                )

        # First reasonably sized image.
        for img in soup.find_all("img"):
            src = (
                img.get("src")
                or img.get("data-src")
                or img.get("data-original")
            )

            if not src:
                continue

            if src.startswith("data:"):
                continue

            absolute = absolute_url(
                article_url,
                src
            )

            if absolute:
                return absolute

    except Exception as e:
        print("Image extraction error:", e)

    return ""


# =========================================================
# VIDEO EXTRACTION
# =========================================================

def extract_video_url(entry, article_url):
    # RSS media content.
    for field in (
        "media_content",
        "media_player",
    ):
        items = entry.get(field, [])

        if not isinstance(items, list):
            items = [items]

        for item in items:
            if not isinstance(item, dict):
                continue

            url = (
                item.get("url")
                or item.get("href")
            )

            media_type = (
                item.get("type")
                or ""
            ).lower()

            if url and (
                "video" in media_type
                or re.search(
                    r"\.(mp4|webm|mov)(?:\?|$)",
                    url,
                    re.IGNORECASE
                )
            ):
                return absolute_url(
                    article_url,
                    url
                )

    try:
        response = SESSION.get(
            article_url,
            timeout=ARTICLE_TIMEOUT
        )

        if response.status_code >= 400:
            return ""

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        # OpenGraph.
        meta_names = [
            "og:video",
            "og:video:url",
            "og:video:secure_url",
            "twitter:player:stream",
        ]

        for name in meta_names:
            tag = soup.find(
                "meta",
                attrs={
                    "property": name
                }
            )

            if not tag:
                tag = soup.find(
                    "meta",
                    attrs={
                        "name": name
                    }
                )

            if tag and tag.get("content"):
                url = absolute_url(
                    article_url,
                    tag["content"]
                )

                if url:
                    return url

        # HTML video/source.
        for video in soup.find_all("video"):
            for source in video.find_all("source"):
                src = (
                    source.get("src")
                    or source.get("data-src")
                )

                if src:
                    return absolute_url(
                        article_url,
                        src
                    )

            src = (
                video.get("src")
                or video.get("data-src")
            )

            if src:
                return absolute_url(
                    article_url,
                    src
                )

        # JSON-LD.
        for script in soup.find_all(
            "script",
            attrs={
                "type": "application/ld+json"
            }
        ):
            raw = script.string or script.get_text()

            if not raw:
                continue

            try:
                data = json.loads(raw)
            except Exception:
                continue

            objects = data

            if isinstance(data, dict):
                objects = [data]

                if isinstance(
                    data.get("@graph"),
                    list
                ):
                    objects += data["@graph"]

            if not isinstance(objects, list):
                objects = [objects]

            for obj in objects:
                if not isinstance(obj, dict):
                    continue

                for key in (
                    "contentUrl",
                    "embedUrl"
                ):
                    value = obj.get(key)

                    if isinstance(value, str):
                        if (
                            ".mp4" in value.lower()
                            or ".webm" in value.lower()
                            or ".mov" in value.lower()
                            or "video" in value.lower()
                        ):
                            return absolute_url(
                                article_url,
                                value
                            )

    except Exception as e:
        print("Video extraction error:", e)

    return ""


# =========================================================
# DOWNLOAD MEDIA
# =========================================================

def download_file(url, prefix):
    if not url:
        return None

    try:
        parsed = urlparse(url)

        extension = os.path.splitext(
            parsed.path
        )[1].lower()

        if extension not in [
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
            ".gif",
            ".mp4",
            ".webm",
            ".mov"
        ]:
            extension = ".bin"

        filename = safe_filename(
            prefix,
            extension
        )

        max_bytes = (
            MAX_VIDEO_MB * 1024 * 1024
            if extension in [".mp4"]
            else MAX_IMAGE_MB * 1024 * 1024
        )

        print("Downloading media:", url)

        with SESSION.get(
            url,
            stream=True,
            timeout=ARTICLE_TIMEOUT
        ) as response:

            if response.status_code >= 400:
                print(
                    "Download HTTP error:",
                    response.status_code
                )
                return None

            content_length = response.headers.get(
                "Content-Length"
            )

            if content_length:
                try:
                    if int(content_length) > max_bytes:
                        print("Media too large")
                        return None
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

                    total += len(chunk)

                    if total > max_bytes:
                        print(
                            "Media exceeded size limit"
                        )

                        try:
                            os.remove(filename)
                        except Exception:
                            pass

                        return None

                    f.write(chunk)

        print(
            f"Downloaded: {total / 1024 / 1024:.2f} MB"
        )

        return filename

    except Exception as e:
        print("Download error:", e)
        return None


# =========================================================
# WATERMARK
# =========================================================

def add_watermark(image_path):
    if not image_path:
        return None

    try:
        image = Image.open(
            image_path
        ).convert("RGB")

        calculated_size = int(
            image.width * 0.022
        )

        font_size = max(
            18,
            min(calculated_size, 42)
        )

        try:
            font = ImageFont.truetype(
                FONT_BOLD,
                font_size
            )
        except Exception:
            font = ImageFont.load_default()

        draw = ImageDraw.Draw(image)

        text = "نبض خبر | NABZ"

        bbox = draw.textbbox(
            (0, 0),
            text,
            font=font
        )

        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        margin = max(
            10,
            int(image.width * 0.018)
        )

        x = image.width - text_width - margin
        y = image.height - text_height - margin

        # Shadow.
        draw.text(
            (x + 2, y + 2),
            text,
            font=font,
            fill=(0, 0, 0)
        )

        # White watermark.
        draw.text(
            (x, y),
            text,
            font=font,
            fill=(255, 255, 255)
        )

        output = image_path.rsplit(
            ".",
            1
        )[0] + "_watermarked.jpg"

        image.save(
            output,
            "JPEG",
            quality=92,
            optimize=True
        )

        return output

    except Exception as e:
        print("Watermark error:", e)
        return image_path


# =========================================================
# TELEGRAM
# =========================================================

def telegram_api(method):
    return (
        f"https://api.telegram.org/bot"
        f"{BOT_TOKEN}/{method}"
    )


def send_video(video_path, caption):
    if not video_path:
        return False

    try:
        with open(
            video_path,
            "rb"
        ) as video:

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

        if response.status_code == 200:
            print("VIDEO PUBLISHED")
            return True

        print(
            "Telegram video error:",
            response.status_code,
            response.text[:500]
        )

    except Exception as e:
        print("Video send error:", e)

    return False


def send_photo(photo_path, caption):
    if not photo_path:
        return False

    try:
        with open(
            photo_path,
            "rb"
        ) as photo:

            response = SESSION.post(
                telegram_api("sendPhoto"),
                data={
                    "chat_id": CHANNEL_ID,
                    "caption": caption,
                },
                files={
                    "photo": photo
                },
                timeout=120
            )

        if response.status_code == 200:
            print("PHOTO PUBLISHED")
            return True

        print(
            "Telegram photo error:",
            response.status_code,
            response.text[:500]
        )

    except Exception as e:
        print("Photo send error:", e)

    return False


def send_text(caption):
    try:
        response = SESSION.post(
            telegram_api("sendMessage"),
            data={
                "chat_id": CHANNEL_ID,
                "text": caption,
                "disable_web_page_preview": "false",
            },
            timeout=60
        )

        if response.status_code == 200:
            print("TEXT PUBLISHED")
            return True

        print(
            "Telegram text error:",
            response.status_code,
            response.text[:500]
        )

    except Exception as e:
        print("Text send error:", e)

    return False


# =========================================================
# CAPTION
# =========================================================

def make_caption(title, summary):
    title = clean_title(title)
    summary = enforce_short_summary(summary)

    if not title:
        title = "خبر جدید"

    if not summary:
        summary = title

    return (
        f"📰 {title}\n\n"
        f"{summary}\n\n"
        f"#نبض_خبر"
    )


# =========================================================
# RSS COLLECTION
# =========================================================

def collect_feed(
    source_name,
    feed_url,
    max_entries=8
):
    results = []

    try:
        response = SESSION.get(
            feed_url,
            timeout=REQUEST_TIMEOUT
        )

        if response.status_code >= 400:
            print(
                "RSS HTTP error:",
                source_name,
                response.status_code
            )
            return results

        parsed = feedparser.parse(
            response.content
        )

        entries = parsed.entries[:max_entries]

        print(
            f"RSS OK: {source_name} | "
            f"{len(entries)} | {feed_url}"
        )

        for entry in entries:
            raw_title = (
                entry.get("title")
                or ""
            )

            title = clean_title(
                raw_title
            )

            if not title:
                continue

            link = (
                entry.get("link")
                or ""
            )

            if not link:
                continue

            link = absolute_url(
                feed_url,
                link
            )

            summary = (
                entry.get("summary")
                or entry.get("description")
                or ""
            )

            summary = clean_content(
                summary
            )

            # Google News summaries often contain
            # related links rather than useful article text.
            if source_name == "گوگل نیوز":
                summary = ""

            entry_time = parse_entry_time(
                entry
            )

            importance = calculate_importance(
                title,
                summary,
                source_name,
                entry
            )

            results.append({
                "title": title,
                "link": link,
                "summary": summary,
                "source": source_name,
                "entry": entry,
                "published": entry_time,
                "importance": importance,
            })

    except Exception as e:
        print(
            f"RSS ERROR: {source_name}: {e}"
        )

    return results


# =========================================================
# CANDIDATE COLLECTION
# =========================================================

def collect_candidates(history):
    candidates = []

    # Direct RSS feeds.
    for source_name, feed_url in RSS_FEEDS:
        candidates.extend(
            collect_feed(
                source_name,
                feed_url,
                max_entries=8
            )
        )

    # Google News.
    for source_name, feed_url in GOOGLE_NEWS_FEEDS:
        candidates.extend(
            collect_feed(
                source_name,
                feed_url,
                max_entries=10
            )
        )

    # Remove exact duplicates.
    unique = {}

    for item in candidates:
        item_id = make_id(
            item["title"],
            item["link"]
        )

        if item_id in history:
            continue

        if item_id not in unique:
            item["id"] = item_id
            unique[item_id] = item

    candidates = list(unique.values())

    # Smart roundup filtering.
    filtered = []

    for item in candidates:
        if is_roundup_news(
            item["title"]
        ):
            print(
                "SKIPPED ROUNDUP:",
                item["title"]
            )
            continue

        filtered.append(item)

    candidates = filtered

    # Cross-source bonus.
    for item in candidates:
        item["importance"] += (
            detect_cross_source_bonus(
                item,
                candidates
            )
        )

    # Sort by importance first,
    # then by freshness.
    candidates.sort(
        key=lambda x: (
            x.get("importance", 0),
            x.get("published")
            or datetime(
                1970,
                1,
                1,
                tzinfo=timezone.utc
            )
        ),
        reverse=True
    )

    print(
        "Candidates found:",
        len(candidates)
    )

    print("\nTOP PRIORITY NEWS:")

    for item in candidates[:10]:
        print(
            f"[{item['importance']}] "
            f"{item['source']} - "
            f"{item['title']}"
        )

    print()

    return candidates


# =========================================================
# PROCESS ONE NEWS ITEM
# =========================================================

def process_news(item):
    title = item["title"]
    link = item["link"]

    print(
        "Processing:",
        title
    )

    # For Google News, fetch publisher page.
    article_text = ""

    if item.get("summary"):
        article_text = item["summary"]

    if len(article_text) < 150:
        extracted = fetch_article(link)

        if extracted:
            article_text = extracted

    # AI.
    ai_result = gemini_request(
        title,
        article_text
    )

    if ai_result:
        final_title = ai_result["title"]
        final_summary = ai_result["summary"]

        print(
            "Gemini generated:",
            final_title
        )

    else:
        print(
            "Using local news engine."
        )

        local_result = local_news_engine(
            title,
            article_text
        )

        final_title = local_result["title"]
        final_summary = local_result["summary"]

    if not final_title:
        final_title = clean_title(title)

    if not final_summary:
        final_summary = enforce_short_summary(
            article_text
        )

    caption = make_caption(
        final_title,
        final_summary
    )

    # =====================================================
    # VIDEO FIRST
    # =====================================================

    video_url = extract_video_url(
        item["entry"],
        link
    )

    if video_url:
        print(
            "Video found:",
            video_url
        )

        video_path = download_file(
            video_url,
            "nabz_video"
        )

        if video_path:
            if send_video(
                video_path,
                caption
            ):
                try:
                    os.remove(video_path)
                except Exception:
                    pass

                print(
                    "PUBLISHED:",
                    final_title
                )

                return True

            try:
                os.remove(video_path)
            except Exception:
                pass

    # =====================================================
    # IMAGE FALLBACK
    # =====================================================

    image_url = extract_image_url(
        item["entry"],
        link
    )

    if image_url:
        print(
            "Image found:",
            image_url
        )

        image_path = download_file(
            image_url,
            "nabz_image"
        )

        if image_path:
            watermarked = add_watermark(
                image_path
            )

            if watermarked:
                image_path = watermarked

            if send_photo(
                image_path,
                caption
            ):
                # Clean temporary files.
                try:
                    if os.path.exists(
                        image_path
                    ):
                        os.remove(
                            image_path
                        )
                except Exception:
                    pass

                print(
                    "PUBLISHED:",
                    final_title
                )

                return True

            try:
                if os.path.exists(
                    image_path
                ):
                    os.remove(
                        image_path
                    )
            except Exception:
                pass

    # =====================================================
    # TEXT FALLBACK
    # =====================================================

    if send_text(caption):
        print(
            "PUBLISHED:",
            final_title
        )

        return True

    return False


# =========================================================
# MAIN
# =========================================================

def main():
    started = time.time()

    print("=" * 60)
    print("NABZ KHABAR BOT")
    print("GEMINI + GOOGLE NEWS + VIDEO + SMART FILTER")
    print("SHORT SUMMARY + WATERMARK")
    print("=" * 60)

    if not BOT_TOKEN:
        print(
            "ERROR: BOT_TOKEN secret is missing."
        )
        return

    print(
        "Gemini enabled:",
        bool(AI_API_KEY)
    )

    print(
        "Gemini model:",
        GEMINI_MODEL
    )

    history = load_history()

    print(
        "History entries:",
        len(history)
    )

    candidates = collect_candidates(
        history
    )

    published_count = 0

    for item in candidates:
        if published_count >= MAX_NEWS_PER_RUN:
            break

        item_id = item["id"]

        if item_id in history:
            continue

        try:
            success = process_news(
                item
            )

            if success:
                history.add(item_id)

                published_count += 1

                # Save immediately so a later failure
                # does not cause duplicate posting.
                save_history(history)

                time.sleep(2)

        except Exception as e:
            print(
                "PROCESS ERROR:",
                e
            )

    runtime = time.time() - started

    print()
    print("=" * 60)
    print(
        f"FINISHED - Published: "
        f"{published_count}"
    )
    print(
        f"Runtime: {runtime:.1f}s"
    )
    print("=" * 60)


if __name__ == "__main__":
    main()
