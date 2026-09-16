import os
import re
import html
import time
import hashlib
import difflib
from urllib.parse import urljoin, urlparse

import requests
import feedparser
from bs4 import BeautifulSoup


# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
AI_API_KEY = os.getenv("AI_API_KEY")

CHAT_ID = "@NabzKhabarOfficial"
HISTORY_FILE = "sent_news.txt"

MAX_NEWS_PER_RUN = int(os.getenv("MAX_NEWS_PER_RUN", "4"))
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

CHANNEL_USERNAME = "@NabzKhabarOfficial"

REQUEST_TIMEOUT = 18
ARTICLE_TIMEOUT = 15
MAX_ARTICLE_CHARS = 12000
MAX_CAPTION_CHARS = 3900

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0 Safari/537.36"
    ),
    "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.7",
}


# ============================================================
# RSS SOURCES
# ============================================================

RSS_FEEDS = [
    # خبر
    ("یورونیوز فارسی", "https://parsi.euronews.com/rss"),
    ("ایسنا", "https://www.isna.ir/rss"),
    ("ایرنا", "https://www.irna.ir/rss"),
    ("مهر", "https://www.mehrnews.com/rss"),
    ("باشگاه خبرنگاران جوان", "https://www.yjc.ir/fa/rss/allnews"),
    ("تابناک", "https://www.tabnak.ir/fa/rss/allnews"),
    ("همشهری", "https://www.hamshahrionline.ir/rss"),
    ("خبرآنلاین", "https://www.khabaronline.ir/rss"),
    ("تسنیم", "https://www.tasnimnews.com/fa/rss/feed/0/8/0"),
    ("مشرق", "https://www.mashreghnews.ir/rss"),
    ("رجانیوز", "https://www.rajanews.com/rss"),

    # ورزش
    ("ورزش سه", "https://www.varzesh3.com/rss"),
    ("ایسنا ورزش", "https://www.isna.ir/rss/service/sports"),
    ("مهر ورزش", "https://www.mehrnews.com/rss/service/sport"),

    # فناوری
    ("زومیت", "https://www.zoomit.ir/feed/"),
    ("دیجیاتو", "https://digiato.com/feed"),
    ("پیوست", "https://peivast.com/feed"),
]


# ============================================================
# HTTP SESSION
# ============================================================

session = requests.Session()
session.headers.update(HEADERS)


# ============================================================
# BASIC HELPERS
# ============================================================

def clean_spaces(text):
    if not text:
        return ""

    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = text.replace("\u200c", "‌")
    text = text.replace("\u200f", "")
    text = text.replace("\u200e", "")

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def normalize_persian(text):
    if not text:
        return ""

    text = str(text)

    replacements = {
        "ي": "ی",
        "ى": "ی",
        "ك": "ک",
        "ۀ": "ه",
        "ة": "ه",
        "ؤ": "و",
        "إ": "ا",
        "أ": "ا",
        "ٱ": "ا",
        "ـ": "",
    }

    for a, b in replacements.items():
        text = text.replace(a, b)

    text = re.sub(r"[\u064B-\u065F\u0670]", "", text)

    text = text.lower()

    return clean_spaces(text)


def meaningful_words(text):
    text = normalize_persian(text)

    words = re.findall(r"[آ-یA-Za-z0-9]+", text)

    stopwords = {
        "از", "به", "در", "با", "برای", "که", "این", "آن",
        "یک", "و", "یا", "را", "های", "ها", "است", "شد",
        "شده", "می", "شود", "کرد", "کرده", "روی", "بر",
        "تا", "اما", "اگر", "هم", "نیز", "او", "آنها",
        "the", "and", "for", "with", "from", "this", "that",
        "a", "an", "of", "to", "in", "on",
    }

    return {
        w for w in words
        if len(w) >= 3 and w not in stopwords
    }


# ============================================================
# DUPLICATE DETECTION
# ============================================================

def normalize_title(title):
    title = normalize_persian(title)

    title = re.sub(
        r"^(خبر فوری|فوری|لحظه‌ای|لحظه اي|اختصاصی)\s*[:\-–—]?\s*",
        "",
        title,
    )

    title = re.sub(r"[^\w\sآ-ی]", " ", title)
    title = re.sub(r"\s+", " ", title)

    return title.strip()


def title_similarity(title1, title2):
    a = normalize_title(title1)
    b = normalize_title(title2)

    if not a or not b:
        return 0.0

    seq = difflib.SequenceMatcher(None, a, b).ratio()

    wa = meaningful_words(a)
    wb = meaningful_words(b)

    if not wa or not wb:
        return seq

    overlap = len(wa & wb) / max(1, min(len(wa), len(wb)))

    return max(seq, overlap)


def content_similarity(text1, text2):
    a = meaningful_words(text1)
    b = meaningful_words(text2)

    if not a or not b:
        return 0.0

    return len(a & b) / max(1, min(len(a), len(b)))


def is_same_story(item1, item2):
    title1 = item1.get("title", "")
    title2 = item2.get("title", "")

    body1 = item1.get("body", "")
    body2 = item2.get("body", "")

    ts = title_similarity(title1, title2)

    # عنوان تقریباً یکسان
    if ts >= 0.78:
        return True

    cs = content_similarity(body1, body2)

    # عنوان نسبتاً مشابه + متن مشابه
    if ts >= 0.55 and cs >= 0.30:
        return True

    # متن تقریباً یکسان حتی با عنوان متفاوت
    if cs >= 0.58:
        return True

    return False


def make_news_id(link, title):
    raw = f"{normalize_title(title)}|{link.strip()}"

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


# ============================================================
# HISTORY
# ============================================================

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return set()

    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return {
                line.strip()
                for line in f
                if line.strip()
            }
    except Exception:
        return set()


def save_history(history):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            for item in list(history)[-5000:]:
                f.write(item + "\n")
    except Exception as e:
        print("History save error:", repr(e))


# ============================================================
# RSS
# ============================================================

def get_feed(name, url):
    try:
        response = session.get(
            url,
            timeout=REQUEST_TIMEOUT,
        )

        response.raise_for_status()

        parsed = feedparser.parse(response.content)

        if not parsed.entries:
            print(f"NO ENTRIES: {name}")
            return []

        return parsed.entries

    except Exception as e:
        print(f"RSS ERROR [{name}]: {repr(e)}")
        return []


def get_entry_link(entry):
    link = entry.get("link", "")

    if not link:
        links = entry.get("links", [])

        for item in links:
            href = item.get("href")

            if href:
                link = href
                break

    return link.strip()


def get_entry_summary(entry):
    parts = []

    for key in [
        "summary",
        "description",
        "subtitle",
        "content",
    ]:
        value = entry.get(key)

        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    value = item.get("value", "")
                    break

        if value:
            if isinstance(value, str):
                parts.append(value)

    text = "\n".join(parts)

    soup = BeautifulSoup(text, "html.parser")

    return clean_spaces(
        soup.get_text("\n", strip=True)
    )


# ============================================================
# ARTICLE TEXT EXTRACTION
# ============================================================

BAD_TEXT_PATTERNS = [
    r"کپی\s*شد",
    r"کپی\s*لینک",
    r"دریافت\s*\d+\s*mb",
    r"دانلود\s*\d+\s*mb",
    r"کد\s*مطلب",
    r"کد خبر",
    r"انتهای پیام",
    r"بیشتر بخوانید",
    r"مطالب مرتبط",
    r"اخبار مرتبط",
    r"آخرین اخبار",
    r"پیشنهاد سردبیر",
    r"پربازدید",
    r"محبوب ترین",
    r"نظرات کاربران",
    r"ارسال نظر",
    r"دیدگاه",
    r"عضویت در خبرنامه",
    r"تبلیغات",
]


def is_bad_line(text):
    line = normalize_persian(text)

    if not line:
        return True

    if len(line) < 3:
        return True

    for pattern in BAD_TEXT_PATTERNS:
        if re.search(pattern, line, re.IGNORECASE):
            return True

    # لینک‌های تنها
    if re.fullmatch(r"https?://\S+", line):
        return True

    return False


def clean_article_lines(lines):
    cleaned = []

    for line in lines:
        line = clean_spaces(line)

        if is_bad_line(line):
            continue

        # خطوط خیلی کوتاه که معمولاً منو/دسته‌بندی هستند
        if len(line) < 12:
            continue

        # کد مطلب / اعداد تنها
        if re.fullmatch(r"[\d\s:/\-]+", line):
            continue

        cleaned.append(line)

    # حذف تکرارهای پشت‌سرهم
    final = []

    for line in cleaned:
        if final and normalize_persian(line) == normalize_persian(final[-1]):
            continue

        final.append(line)

    return final


def extract_article_text(url):
    if not url:
        return ""

    try:
        response = session.get(
            url,
            timeout=ARTICLE_TIMEOUT,
            allow_redirects=True,
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.content,
            "html.parser",
        )

        # حذف قطعی بخش‌هایی که خبر نیستند
        for tag in soup([
            "script",
            "style",
            "noscript",
            "svg",
            "iframe",
            "form",
            "nav",
            "footer",
            "header",
            "aside",
            "button",
        ]):
            tag.decompose()

        # حذف کلاس‌ها و idهای متداول برای محتوای اضافی
        bad_keywords = [
            "related",
            "recommend",
            "recommended",
            "sidebar",
            "footer",
            "header",
            "menu",
            "navigation",
            "comment",
            "comments",
            "share",
            "social",
            "advert",
            "ads",
            "banner",
            "newsletter",
            "tag",
            "tags",
            "breadcrumb",
        ]

        for tag in soup.find_all(True):
            classes = " ".join(tag.get("class", []))
            tag_id = tag.get("id", "")

            identifier = (
                f"{classes} {tag_id}"
            ).lower()

            if any(word in identifier for word in bad_keywords):
                try:
                    tag.decompose()
                except Exception:
                    pass

        # اولویت با articleBody
        selectors = [
            "[itemprop='articleBody']",
            "article",
            ".article-body",
            ".article__body",
            ".article-content",
            ".article-body-content",
            ".post-content",
            ".entry-content",
            ".news-content",
            ".news-detail",
            ".content-news",
            "main",
        ]

        candidates = []

        for selector in selectors:
            try:
                for node in soup.select(selector):
                    text = node.get_text(
                        "\n",
                        strip=True,
                    )

                    if len(text) > 250:
                        candidates.append(text)
            except Exception:
                pass

        # اگر ساختار اختصاصی پیدا نشد
        if not candidates:
            body = soup.body

            if body:
                candidates.append(
                    body.get_text(
                        "\n",
                        strip=True,
                    )
                )

        if not candidates:
            return ""

        # بهترین candidate
        candidates.sort(
            key=lambda x: len(x),
            reverse=True,
        )

        raw = candidates[0]

        lines = raw.splitlines()

        lines = clean_article_lines(lines)

        # تشخیص آلودگی با تیترهای زیاد
        if len(lines) > 10:
            suspicious = 0

            for line in lines:
                # تیترهای خیلی کوتاه در میان متن
                if 12 <= len(line) <= 65:
                    if not line.endswith(
                        (".", "؟", "!", "؛", "،", ":")
                    ):
                        suspicious += 1

            if suspicious > max(8, len(lines) * 0.60):
                print("ARTICLE REJECTED: suspicious page structure")
                return ""

        text = "\n\n".join(lines)

        text = clean_spaces(text)

        # حذف لینک‌ها
        text = re.sub(
            r"https?://\S+",
            "",
            text,
        )

        # حذف باقی‌مانده کدها
        text = re.sub(
            r"کد\s*(?:مطلب|خبر)\s*[:：]?\s*\d+",
            "",
            text,
            flags=re.IGNORECASE,
        )

        # حذف تاریخ‌های تنها
        text = re.sub(
            r"\b\d{1,2}\s+(?:شهریور|مهر|آبان|آذر|دی|بهمن|اسفند|فروردین|اردیبهشت|خرداد|تیر|مرداد)\s+\d{4}\b",
            "",
            text,
        )

        text = clean_spaces(text)

        return text[:MAX_ARTICLE_CHARS]

    except Exception as e:
        print(
            f"ARTICLE ERROR [{url}]: {repr(e)}"
        )
        return ""


# ============================================================
# MEDIA EXTRACTION
# ============================================================

def absolute_url(base, value):
    if not value:
        return ""

    value = value.strip()

    if value.startswith("//"):
        return "https:" + value

    return urljoin(base, value)


def is_video_url(url):
    if not url:
        return False

    lower = url.lower()

    return any(
        ext in lower
        for ext in [
            ".mp4",
            ".mov",
            ".m4v",
            ".webm",
            ".mkv",
        ]
    )


def is_image_url(url):
    if not url:
        return False

    lower = url.lower()

    return any(
        ext in lower
        for ext in [
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
        ]
    )


def extract_media(entry, article_url):
    media = []

    # RSS enclosures
    for enclosure in entry.get("enclosures", []):
        href = enclosure.get("href") or enclosure.get("url")

        if href:
            media.append(
                absolute_url(article_url, href)
            )

    # media_content
    for item in entry.get("media_content", []):
        href = (
            item.get("url")
            or item.get("href")
        )

        if href:
            media.append(
                absolute_url(article_url, href)
            )

    # media_thumbnail
    for item in entry.get("media_thumbnail", []):
        href = item.get("url")

        if href:
            media.append(
                absolute_url(article_url, href)
            )

    # خود صفحه
    try:
        response = session.get(
            article_url,
            timeout=ARTICLE_TIMEOUT,
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.content,
            "html.parser",
        )

        # OpenGraph image
        for prop in [
            "og:image",
            "twitter:image",
        ]:
            tag = soup.find(
                "meta",
                attrs={
                    "property": prop
                },
            )

            if not tag:
                tag = soup.find(
                    "meta",
                    attrs={
                        "name": prop
                    },
                )

            if tag and tag.get("content"):
                media.append(
                    absolute_url(
                        article_url,
                        tag["content"],
                    )
                )

        # OpenGraph video
        for prop in [
            "og:video",
            "og:video:url",
            "og:video:secure_url",
        ]:
            tag = soup.find(
                "meta",
                attrs={
                    "property": prop
                },
            )

            if tag and tag.get("content"):
                value = absolute_url(
                    article_url,
                    tag["content"],
                )

                if is_video_url(value):
                    media.insert(0, value)

        # video/source
        for tag in soup.find_all([
            "video",
            "source",
        ]):
            for attr in [
                "src",
                "data-src",
                "data-video",
            ]:
                value = tag.get(attr)

                if value:
                    media.append(
                        absolute_url(
                            article_url,
                            value,
                        )
                    )

        # لینک مستقیم ویدئو
        for tag in soup.find_all("a"):
            href = tag.get("href")

            if href:
                full = absolute_url(
                    article_url,
                    href,
                )

                if is_video_url(full):
                    media.insert(0, full)

    except Exception as e:
        print(
            f"MEDIA ERROR [{article_url}]: {repr(e)}"
        )

    # unique
    result = []

    for item in media:
        if not item:
            continue

        if item not in result:
            result.append(item)

    # اول ویدئو
    videos = [
        x for x in result
        if is_video_url(x)
    ]

    images = [
        x for x in result
        if is_image_url(x)
    ]

    return videos + images


# ============================================================
# CATEGORY
# ============================================================

def detect_category(title, body):
    text = normalize_persian(
        f"{title} {body}"
    )

    categories = {
        "ورزش": [
            "فوتبال",
            "استقلال",
            "پرسپولیس",
            "سپاهان",
            "لیگ",
            "جام",
            "بازیکن",
            "مربی",
            "گل",
            "والیبال",
            "بسکتبال",
            "تنیس",
        ],
        "فناوری": [
            "هوش مصنوعی",
            "ai",
            "گوگل",
            "اپل",
            "سامسونگ",
            "مایکروسافت",
            "آیفون",
            "اندروید",
            "تکنولوژی",
            "اینترنت",
            "فضایی",
            "اسپیس ایکس",
        ],
        "اقتصاد": [
            "دلار",
            "یورو",
            "طلا",
            "سکه",
            "بورس",
            "اقتصاد",
            "بانک",
            "تورم",
            "قیمت",
            "بازار",
        ],
        "حوادث": [
            "تصادف",
            "حادثه",
            "آتش سوزی",
            "آتش‌سوزی",
            "زلزله",
            "مفقود",
            "سقوط",
            "انفجار",
        ],
        "سلامت": [
            "پزشک",
            "بیمار",
            "سلامت",
            "درمان",
            "بیماری",
            "دارو",
            "وزارت بهداشت",
        ],
    }

    for category, words in categories.items():
        for word in words:
            if normalize_persian(word) in text:
                return category

    return "خبر"


# ============================================================
# AI
# ============================================================

def ai_rewrite(title, body, category):
    if not AI_API_KEY:
        return title, body

    if not body:
        return title, body

    prompt = f"""
تو دبیر حرفه‌ای یک کانال خبری فارسی به نام «نبض خبر» هستی.

عنوان خبر:
{title}

دسته:
{category}

متن خام خبر:
{body}

وظیفه:

1. عنوان را حرفه‌ای، کوتاه و جذاب کن.
2. فقط بر اساس اطلاعات موجود در متن بنویس.
3. هیچ واقعیت، عدد، نام، نقل قول یا جزئیات جدیدی اضافه نکن.
4. متن را به فارسی روان و طبیعی تبدیل کن.
5. تبلیغات، منو، اخبار مرتبط، پیشنهادها، کد مطلب، تاریخ‌های تکراری،
   «کپی شد»، لینک، نام سایت و موارد غیرخبری را حذف کن.
6. خبر را به شکل چند پاراگراف کوتاه و خوانا تنظیم کن.
7. متن نباید حالت ماشینی و خشک داشته باشد.
8. اگر اطلاعاتی در متن نیست، آن را حدس نزن.
9. هیچ لینک اینترنتی در خروجی قرار نده.
10. نام منبع یا سایت را در خروجی قرار نده.
11. خروجی فقط JSON معتبر باشد:

{{
  "title": "عنوان نهایی",
  "body": "متن نهایی"
}}
"""

    try:
        url = (
            "https://generativelanguage.googleapis.com/"
            f"v1beta/models/{GEMINI_MODEL}:generateContent"
        )

        response = session.post(
            url,
            params={
                "key": AI_API_KEY
            },
            json={
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
                    "temperature": 0.2,
                    "maxOutputTokens": 2500,
                },
            },
            timeout=30,
        )

        if response.status_code != 200:
            print(
                "AI ERROR:",
                response.status_code,
                response.text[:1000],
            )
            return title, body

        data = response.json()

        candidates = data.get(
            "candidates",
            [],
        )

        if not candidates:
            return title, body

        parts = candidates[0].get(
            "content",
            {}
        ).get("parts", [])

        if not parts:
            return title, body

        text = parts[0].get(
            "text",
            ""
        ).strip()

        # حذف markdown احتمالی
        text = re.sub(
            r"^```json\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )

        text = re.sub(
            r"\s*```$",
            "",
            text,
        )

        import json

        result = json.loads(text)

        new_title = clean_spaces(
            result.get("title", "")
        )

        new_body = clean_spaces(
            result.get("body", "")
        )

        if not new_title:
            new_title = title

        if not new_body:
            new_body = body

        return new_title, new_body

    except Exception as e:
        print(
            "AI PARSE/REQUEST ERROR:",
            repr(e),
        )
        return title, body


# ============================================================
# QUALITY CONTROL
# ============================================================

def is_valid_news(title, body):
    title = clean_spaces(title)
    body = clean_spaces(body)

    if len(title) < 8:
        return False

    if len(body) < 80:
        return False

    # متن‌هایی که احتمالاً صفحه آلوده است
    bad_count = 0

    bad_terms = [
        "کد مطلب",
        "کپی شد",
        "مطالب مرتبط",
        "اخبار مرتبط",
        "پیشنهاد سردبیر",
        "دریافت mb",
        "دانلود mb",
        "عضویت در خبرنامه",
    ]

    combined = normalize_persian(
        f"{title} {body}"
    )

    for term in bad_terms:
        if normalize_persian(term) in combined:
            bad_count += 1

    if bad_count >= 2:
        return False

    # اگر متن پر از لینک باشد
    urls = re.findall(
        r"https?://\S+",
        body,
    )

    if len(urls) >= 2:
        return False

    return True


# ============================================================
# CAPTION
# ============================================================

def make_caption(title, body, category):
    title = clean_spaces(title)
    body = clean_spaces(body)

    # حذف لینک‌ها از متن
    body = re.sub(
        r"https?://\S+",
        "",
        body,
    )

    caption = (
        f"📰 <b>{html.escape(title)}</b>\n\n"
        f"{html.escape(body)}\n\n"
        f"<i>#{html.escape(category)}</i>\n\n"
        f"<b>{CHANNEL_USERNAME}</b>"
    )

    # Telegram caption limit
    if len(caption) > MAX_CAPTION_CHARS:
        allowed = MAX_CAPTION_CHARS - 250

        shortened = body[:allowed]

        # قطع در نقطه مناسب
        last_space = shortened.rfind(" ")

        if last_space > 300:
            shortened = shortened[:last_space]

        caption = (
            f"📰 <b>{html.escape(title)}</b>\n\n"
            f"{html.escape(shortened)}…\n\n"
            f"<i>#{html.escape(category)}</i>\n\n"
            f"<b>{CHANNEL_USERNAME}</b>"
        )

    return caption


# ============================================================
# TELEGRAM
# ============================================================

def telegram_api(method):
    return (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/{method}"
    )


def send_photo(photo_url, caption):
    try:
        response = session.post(
            telegram_api("sendPhoto"),
            data={
                "chat_id": CHAT_ID,
                "photo": photo_url,
                "caption": caption,
                "parse_mode": "HTML",
            },
            timeout=30,
        )

        if response.status_code == 200:
            return True

        print(
            "PHOTO SEND ERROR:",
            response.status_code,
            response.text[:1000],
        )

    except Exception as e:
        print(
            "PHOTO SEND EXCEPTION:",
            repr(e),
        )

    return False


def send_video(video_url, caption):
    try:
        response = session.post(
            telegram_api("sendVideo"),
            data={
                "chat_id": CHAT_ID,
                "video": video_url,
                "caption": caption,
                "parse_mode": "HTML",
                "supports_streaming": "true",
            },
            timeout=60,
        )

        if response.status_code == 200:
            return True

        print(
            "VIDEO SEND ERROR:",
            response.status_code,
            response.text[:1000],
        )

    except Exception as e:
        print(
            "VIDEO SEND EXCEPTION:",
            repr(e),
        )

    return False


def send_text(caption):
    try:
        response = session.post(
            telegram_api("sendMessage"),
            data={
                "chat_id": CHAT_ID,
                "text": caption,
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            },
            timeout=30,
        )

        if response.status_code == 200:
            return True

        print(
            "TEXT SEND ERROR:",
            response.status_code,
            response.text[:1000],
        )

    except Exception as e:
        print(
            "TEXT SEND EXCEPTION:",
            repr(e),
        )

    return False


# ============================================================
# DOWNLOAD MEDIA
# ============================================================

def download_media(url, filename):
    try:
        response = session.get(
            url,
            timeout=60,
            stream=True,
        )

        response.raise_for_status()

        with open(filename, "wb") as f:
            for chunk in response.iter_content(
                chunk_size=1024 * 256
            ):
                if chunk:
                    f.write(chunk)

        return filename

    except Exception as e:
        print(
            "MEDIA DOWNLOAD ERROR:",
            repr(e),
        )

        return ""


# ============================================================
# CANDIDATES
# ============================================================

def collect_candidates(history):
    candidates = []
    seen_titles = []

    print("Collecting news...")

    for source_name, feed_url in RSS_FEEDS:

        entries = get_feed(
            source_name,
            feed_url,
        )

        # فقط تعداد معقولی از جدیدترین‌ها
        entries = entries[:8]

        for entry in entries:

            title = clean_spaces(
                BeautifulSoup(
                    str(entry.get("title", "")),
                    "html.parser",
                ).get_text(" ", strip=True)
            )

            if not title:
                continue

            link = get_entry_link(entry)

            if not link:
                continue

            news_id = make_news_id(
                link,
                title,
            )

            if news_id in history:
                continue

            # جلوگیری از تکرار عنوان در همین اجرا
            duplicate_title = False

            for old_title in seen_titles:
                if title_similarity(
                    title,
                    old_title,
                ) >= 0.78:
                    duplicate_title = True
                    break

            if duplicate_title:
                continue

            rss_body = get_entry_summary(
                entry
            )

            # متن کامل صفحه
            article_body = extract_article_text(
                link
            )

            # اگر استخراج صفحه موفق بود، آن را ترجیح بده
            if article_body:
                body = article_body
            else:
                body = rss_body

            # رسانه
            media = extract_media(
                entry,
                link,
            )

            # برای حفظ کیفیت، خبر بدون رسانه فعلاً کنار گذاشته می‌شود
            if not media:
                print(
                    f"SKIP NO MEDIA: {title[:80]}"
                )
                continue

            item = {
                "title": title,
                "body": body,
                "link": link,
                "source": source_name,
                "media": media,
                "news_id": news_id,
            }

            # کیفیت اولیه
            if not is_valid_news(
                title,
                body,
            ):
                print(
                    f"SKIP BAD ARTICLE: {title[:80]}"
                )
                continue

            # بررسی با خبرهای قبلی همین اجرا
            duplicate = False

            for old_item in candidates:
                if is_same_story(
                    item,
                    old_item,
                ):
                    duplicate = True
                    print(
                        "DUPLICATE BLOCKED:",
                        title[:100],
                    )
                    break

            if duplicate:
                continue

            candidates.append(item)
            seen_titles.append(title)

            print(
                f"CANDIDATE: {title[:100]}"
            )

    print(
        f"Candidates found: {len(candidates)}"
    )

    return candidates


# ============================================================
# PUBLISH
# ============================================================

def publish_item(item):
    original_title = item["title"]
    original_body = item["body"]
    category = detect_category(
        original_title,
        original_body,
    )

    print(
        "Preparing:",
        original_title[:100],
    )

    # AI فقط برای مرتب‌سازی
    title, body = ai_rewrite(
        original_title,
        original_body,
        category,
    )

    # اگر AI خروجی خراب داد، متن اصلی
    if not is_valid_news(
        title,
        body,
    ):
        title = original_title
        body = original_body

    # یک کنترل نهایی
    if not is_valid_news(
        title,
        body,
    ):
        print(
            "FINAL QUALITY CHECK FAILED:",
            original_title[:100],
        )
        return False

    caption = make_caption(
        title,
        body,
        category,
    )

    media = item.get(
        "media",
        [],
    )

    # اول ویدئو
    videos = [
        x for x in media
        if is_video_url(x)
    ]

    images = [
        x for x in media
        if is_image_url(x)
    ]

    # ----------------------------------------
    # VIDEO
    # ----------------------------------------

    for video in videos[:3]:

        print(
            "Trying VIDEO:",
            video[:150],
        )

        if send_video(
            video,
            caption,
        ):
            print(
                "Video published successfully."
            )
            return True

    # ----------------------------------------
    # IMAGE
    # ----------------------------------------

    for image in images[:4]:

        print(
            "Trying PHOTO:",
            image[:150],
        )

        if send_photo(
            image,
            caption,
        ):
            print(
                "Photo published successfully."
            )
            return True

    # ----------------------------------------
    # TEXT FALLBACK
    # ----------------------------------------

    print(
        "Media failed, trying text fallback..."
    )

    if send_text(caption):
        print(
            "Text published successfully."
        )
        return True

    return False


# ============================================================
# MAIN
# ============================================================

def main():
    print("NABZ KHABAR BOT STARTED")

    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN is missing.")
        return

    history = load_history()

    print(
        f"History entries: {len(history)}"
    )

    candidates = collect_candidates(
        history
    )

    published = 0

    for item in candidates:

        if published >= MAX_NEWS_PER_RUN:
            break

        print(
            "\n----------------------------------------"
        )

        success = publish_item(item)

        if success:

            history.add(
                item["news_id"]
            )

            # همچنین hash عنوان برای جلوگیری بهتر
            title_hash = hashlib.sha256(
                normalize_title(
                    item["title"]
                ).encode("utf-8")
            ).hexdigest()

            history.add(
                f"title:{title_hash}"
            )

            published += 1

            print(
                f"PUBLISHED {published}/{MAX_NEWS_PER_RUN}:",
                item["title"][:100],
            )

            # کمی فاصله برای جلوگیری از فشار به Telegram
            time.sleep(2)

        else:
            print(
                "FAILED:",
                item["title"][:100],
            )

    save_history(history)

    print(
        f"\nFINISHED - Published: {published}"
    )


if __name__ == "__main__":
    main()
