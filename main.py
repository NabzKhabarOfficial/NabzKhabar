import os
import io
import re
import html
import time
import hashlib
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from difflib import SequenceMatcher
from urllib.parse import urljoin

import requests
import feedparser
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont


# =========================================================
# NABZ KHABAR - AUTOMATIC NEWS BOT
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
AI_API_KEY = os.getenv("AI_API_KEY")

CHAT_ID = "@NabzKhabarOfficial"
HISTORY_FILE = "sent_news.txt"

BASE_DIR = Path(__file__).resolve().parent

FONT_BOLD = BASE_DIR / "Vazirmatn-Bold.ttf"
FONT_REGULAR = BASE_DIR / "Vazirmatn-Regular.ttf"

MAX_NEWS_PER_RUN = int(os.getenv("MAX_NEWS_PER_RUN", "4"))
MAX_ENTRIES_PER_FEED = 8

REQUEST_TIMEOUT = 15
VIDEO_MAX_SIZE = 50 * 1024 * 1024

TEHRAN_TZ = ZoneInfo("Asia/Tehran")


# =========================================================
# RSS SOURCES
# =========================================================

RSS_FEEDS = {

    # -------------------------
    # ایران / عمومی
    # -------------------------

    "تسنیم - عمومی":
        "https://www.tasnimnews.com/fa/rss/feed/0/0/0/",

    "تسنیم - اقتصاد":
        "https://www.tasnimnews.com/fa/rss/feed/0/8/0/",

    "تسنیم - بین‌الملل":
        "https://www.tasnimnews.com/fa/rss/feed/0/3/0/",

    "ایسنا":
        "https://www.isna.ir/rss",

    "مهر":
        "https://www.mehrnews.com/rss",

    "ایرنا":
        "https://www.irna.ir/rss",

    "خبرآنلاین":
        "https://www.khabaronline.ir/rss",

    "فارس":
        "https://www.farsnews.ir/rss",

    # -------------------------
    # اقتصاد / بازار
    # -------------------------

    "دنیای اقتصاد":
        "https://donya-e-eqtesad.com/fa/tinynews/rss/",

    "گوگل نیوز - اقتصاد":
        "https://news.google.com/rss/search?q=اقتصاد+بورس+دلار+طلا+سکه&hl=fa&gl=IR&ceid=IR:fa",

    "گوگل نیوز - بازار":
        "https://news.google.com/rss/search?q=دلار+طلا+سکه+بورس+ارز&hl=fa&gl=IR&ceid=IR:fa",

    # -------------------------
    # ورزش
    # -------------------------

    "ورزش سه":
        "https://www.varzesh3.com/rss/all",

    "گوگل نیوز - ورزش":
        "https://news.google.com/rss/search?q=ورزش+فوتبال+استقلال+پرسپولیس+تیم+ملی&hl=fa&gl=IR&ceid=IR:fa",

    # -------------------------
    # فناوری
    # -------------------------

    "دیجیاتو":
        "https://digiato.com/feed",

    "زومیت":
        "https://www.zoomit.ir/feed/",

    "گوگل نیوز - فناوری":
        "https://news.google.com/rss/search?q=فناوری+هوش+مصنوعی+موبایل+اینترنت+تکنولوژی&hl=fa&gl=IR&ceid=IR:fa",

    # -------------------------
    # حوادث
    # -------------------------

    "گوگل نیوز - حوادث":
        "https://news.google.com/rss/search?q=حادثه+تصادف+آتش+سوزی+زلزله+انفجار&hl=fa&gl=IR&ceid=IR:fa",

    # -------------------------
    # سلامت
    # -------------------------

    "گوگل نیوز - سلامت":
        "https://news.google.com/rss/search?q=سلامت+پزشکی+بیماری+درمان+بهداشت&hl=fa&gl=IR&ceid=IR:fa",

    # -------------------------
    # خودرو
    # -------------------------

    "گوگل نیوز - خودرو":
        "https://news.google.com/rss/search?q=خودرو+ماشین+خودروسازی+قیمت+خودرو&hl=fa&gl=IR&ceid=IR:fa",

    # -------------------------
    # علم
    # -------------------------

    "گوگل نیوز - علم":
        "https://news.google.com/rss/search?q=علم+فضا+نجوم+پژوهش+دانشگاه&hl=fa&gl=IR&ceid=IR:fa",

    # -------------------------
    # فرهنگ و هنر
    # -------------------------

    "گوگل نیوز - فرهنگ":
        "https://news.google.com/rss/search?q=سینما+موسیقی+هنر+فرهنگ+تلویزیون&hl=fa&gl=IR&ceid=IR:fa",

    # -------------------------
    # اجتماعی
    # -------------------------

    "گوگل نیوز - اجتماعی":
        "https://news.google.com/rss/search?q=اجتماعی+آموزش+دانشگاه+جامعه&hl=fa&gl=IR&ceid=IR:fa",

    # -------------------------
    # جهان
    # -------------------------

    "گوگل نیوز - جهان":
        "https://news.google.com/rss/search?q=جهان+بین‌الملل+اروپا+آمریکا+آسیا&hl=fa&gl=IR&ceid=IR:fa",

    # -------------------------
    # خبر عمومی
    # -------------------------

    "گوگل نیوز - عمومی":
        "https://news.google.com/rss?hl=fa&gl=IR&ceid=IR:fa",
}


# =========================================================
# CATEGORY DETECTION
# =========================================================

CATEGORY_RULES = {

    "ورزش": [
        "فوتبال", "ورزش", "استقلال", "پرسپولیس",
        "تیم ملی", "لیگ", "جام جهانی", "والیبال",
        "بسکتبال", "تنیس", "کشتی", "المپیک"
    ],

    "اقتصاد": [
        "دلار", "یورو", "طلا", "سکه", "بورس",
        "اقتصاد", "بانک", "تورم", "ارز",
        "بازار", "سهام", "قیمت", "نفت"
    ],

    "فناوری": [
        "فناوری", "تکنولوژی", "هوش مصنوعی",
        "موبایل", "اینترنت", "گوگل", "اپل",
        "مایکروسافت", "سامسونگ", "آیفون",
        "اندروید", "کامپیوتر", "نرم‌افزار"
    ],

    "حوادث": [
        "تصادف", "حادثه", "انفجار", "آتش‌سوزی",
        "زلزله", "سیل", "سقوط", "واژگونی",
        "مفقود", "نجات", "فوت", "جان باخت"
    ],

    "سلامت": [
        "سلامت", "پزشکی", "بیماری", "درمان",
        "دارو", "بیمارستان", "پزشک", "بهداشت",
        "ویروس", "واکسن"
    ],

    "خودرو": [
        "خودرو", "ماشین", "خودروسازی",
        "ایران خودرو", "سایپا", "خودروی",
        "قیمت خودرو"
    ],

    "علم": [
        "علم", "دانشمند", "پژوهش", "تحقیقات",
        "فضا", "ناسا", "نجوم", "سیاره",
        "دانشگاه", "کشف"
    ],

    "فرهنگ": [
        "سینما", "فیلم", "سریال", "موسیقی",
        "خواننده", "بازیگر", "فرهنگ", "هنر",
        "تلویزیون"
    ],

    "جهان": [
        "آمریکا", "اروپا", "روسیه", "چین",
        "اوکراین", "اسرائیل", "جهان",
        "بین‌الملل", "لندن", "واشنگتن"
    ],

    "اجتماعی": [
        "اجتماعی", "آموزش", "مدرسه", "دانشگاه",
        "جامعه", "شهرداری", "وزارت", "کارگران"
    ],
}


IMPORTANT_KEYWORDS = [
    "فوری",
    "هشدار",
    "زلزله",
    "انفجار",
    "آتش‌سوزی",
    "تصادف",
    "سقوط",
    "جان باخت",
    "کشته",
    "مفقود",
    "حادثه",
    "حمله",
    "درگیری",
]


CATEGORY_ICONS = {
    "فوری": "🚨",
    "ورزش": "⚽",
    "اقتصاد": "💰",
    "فناوری": "💻",
    "حوادث": "🚨",
    "سلامت": "🏥",
    "خودرو": "🚗",
    "علم": "🔬",
    "فرهنگ": "🎬",
    "جهان": "🌍",
    "اجتماعی": "🏙️",
    "ایران": "🇮🇷",
    "عمومی": "📰",
}


# =========================================================
# HTTP
# =========================================================

SESSION = requests.Session()

SESSION.headers.update({
    "User-Agent":
        "Mozilla/5.0 (compatible; NabzKhabarBot/1.0; +https://t.me/NabzKhabarOfficial)"
})


def http_get(url, timeout=REQUEST_TIMEOUT, **kwargs):

    for attempt in range(3):

        try:

            response = SESSION.get(
                url,
                timeout=timeout,
                **kwargs
            )

            if response.status_code == 200:
                return response

            print(
                f"HTTP {response.status_code}: {url}"
            )

        except Exception as e:

            print(
                f"HTTP attempt {attempt + 1} failed: {e}"
            )

        time.sleep(1.5 * (attempt + 1))

    return None


# =========================================================
# TEXT CLEANING
# =========================================================

def clean_text(text, is_title=False):

    if not text:
        return ""

    soup = BeautifulSoup(str(text), "html.parser")

    text = soup.get_text(
        separator=" ",
        strip=True
    )

    text = re.sub(
        r"The post.*?appeared first on.*",
        "",
        text,
        flags=re.I
    )

    text = re.sub(
        r"appeared first on.*",
        "",
        text,
        flags=re.I
    )

    if is_title:

        text = re.sub(
            r"\s*[\(\[]?\s*(عکس|تصاویر|جدول|فیلم|ویدیو|صوت|گزارش تصویری)\s*[\)\]]?",
            "",
            text,
            flags=re.I
        )

    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    return text


def normalize_text(text):

    text = clean_text(text)

    replacements = {
        "ي": "ی",
        "ى": "ی",
        "ك": "ک",
        "ۀ": "ه",
        "ة": "ه",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return text.strip()


# =========================================================
# HISTORY
# =========================================================

def load_sent_news():

    if not os.path.exists(HISTORY_FILE):
        return []

    try:

        with open(
            HISTORY_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            return [
                line.strip()
                for line in f
                if line.strip()
            ]

    except Exception as e:

        print(f"History read error: {e}")
        return []


def save_sent_news(history):

    # Keep order and remove duplicates.
    history = list(dict.fromkeys(history))

    # Keep latest 500 items.
    history = history[-500:]

    try:

        with open(
            HISTORY_FILE,
            "w",
            encoding="utf-8"
        ) as f:

            for item in history:
                f.write(item + "\n")

    except Exception as e:

        print(f"History save error: {e}")


def history_contains(history, value):

    return value in set(history)


# =========================================================
# NEWS ID
# =========================================================

def make_news_id(entry, source_name):

    link = entry.get("link", "").strip()

    if link:
        return link

    guid = entry.get("id", "").strip()

    if guid:
        return guid

    title = normalize_text(
        entry.get("title", "")
    )

    raw = f"{source_name}|{title}"

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


# =========================================================
# SIMILARITY
# =========================================================

def is_similar(title1, title2):

    a = normalize_text(title1)
    b = normalize_text(title2)

    if not a or not b:
        return False

    return SequenceMatcher(
        None,
        a,
        b
    ).ratio() >= 0.78


# =========================================================
# CATEGORY
# =========================================================

def detect_category(title, source_name=""):

    text = normalize_text(
        f"{title} {source_name}"
    )

    if any(
        keyword in text
        for keyword in IMPORTANT_KEYWORDS
    ):
        return "فوری"

    for category, keywords in CATEGORY_RULES.items():

        if any(
            keyword in text
            for keyword in keywords
        ):
            return category

    if "تسنیم" in source_name or \
       "ایسنا" in source_name or \
       "مهر" in source_name or \
       "ایرنا" in source_name or \
       "فارس" in source_name:

        return "ایران"

    return "عمومی"


# =========================================================
# RSS FETCH
# =========================================================

def fetch_feed(feed_url):

    response = http_get(
        feed_url,
        timeout=REQUEST_TIMEOUT
    )

    if not response:
        return None

    try:

        return feedparser.parse(
            response.content
        )

    except Exception as e:

        print(f"Feed parse error: {e}")
        return None


# =========================================================
# MEDIA EXTRACTION
# =========================================================

def extract_media(entry, article_url):

    video_url = None
    image_url = None

    try:

        # -------------------------
        # Enclosures
        # -------------------------

        for enclosure in entry.get(
            "enclosures",
            []
        ):

            href = enclosure.get("href")
            enc_type = (
                enclosure.get("type", "")
                or ""
            ).lower()

            if not href:
                continue

            if "video" in enc_type:
                video_url = urljoin(
                    article_url,
                    href
                )
                break

            if "image" in enc_type and not image_url:
                image_url = urljoin(
                    article_url,
                    href
                )

        # -------------------------
        # Media content
        # -------------------------

        if not video_url and not image_url:

            for media in entry.get(
                "media_content",
                []
            ):

                url = media.get("url")
                media_type = (
                    media.get("type", "")
                    or media.get("medium", "")
                    or ""
                ).lower()

                if not url:
                    continue

                if "video" in media_type:
                    video_url = urljoin(
                        article_url,
                        url
                    )
                    break

                if (
                    "image" in media_type
                    and not image_url
                ):
                    image_url = urljoin(
                        article_url,
                        url
                    )

        # -------------------------
        # RSS HTML
        # -------------------------

        raw = entry.get(
            "summary",
            entry.get("description", "")
        )

        soup = BeautifulSoup(
            raw,
            "html.parser"
        )

        if not video_url:

            video_tag = soup.find("video")

            if video_tag:

                src = (
                    video_tag.get("src")
                    or video_tag.get("data-src")
                )

                if src:
                    video_url = urljoin(
                        article_url,
                        src
                    )

        if not image_url:

            img = soup.find("img")

            if img:

                src = (
                    img.get("src")
                    or img.get("data-src")
                    or img.get("data-original")
                )

                if src:
                    image_url = urljoin(
                        article_url,
                        src
                    )

    except Exception as e:

        print(f"RSS media extraction error: {e}")

    # -----------------------------------------------------
    # If RSS did not provide media, inspect article page.
    # -----------------------------------------------------

    if not video_url or not image_url:

        page = http_get(
            article_url,
            timeout=12
        )

        if page:

            try:

                soup = BeautifulSoup(
                    page.text,
                    "html.parser"
                )

                # -------------------------
                # OpenGraph image
                # -------------------------

                if not image_url:

                    og_image = soup.find(
                        "meta",
                        property="og:image"
                    )

                    if og_image and og_image.get("content"):

                        image_url = urljoin(
                            article_url,
                            og_image["content"]
                        )

                # -------------------------
                # Video tags
                # -------------------------

                if not video_url:

                    for video in soup.find_all(
                        "video"
                    ):

                        src = (
                            video.get("src")
                            or video.get("data-src")
                        )

                        if src:

                            video_url = urljoin(
                                article_url,
                                src
                            )

                            break

                        source = video.find(
                            "source"
                        )

                        if source and source.get("src"):

                            video_url = urljoin(
                                article_url,
                                source["src"]
                            )

                            break

                # -------------------------
                # Direct MP4 links
                # -------------------------

                if not video_url:

                    for tag in soup.find_all(
                        ["a", "source"]
                    ):

                        src = (
                            tag.get("href")
                            or tag.get("src")
                        )

                        if src and re.search(
                            r"\.(mp4|mov|m4v|webm)(\?|$)",
                            src,
                            flags=re.I
                        ):

                            video_url = urljoin(
                                article_url,
                                src
                            )

                            break

            except Exception as e:

                print(
                    f"Article media extraction error: {e}"
                )

    if video_url:
        return video_url, "video"

    if image_url:
        return image_url, "photo"

    return None, None


# =========================================================
# AI REWRITE
# =========================================================

def ai_rewrite(title, raw_text):

    if not AI_API_KEY:
        return None

    # We deliberately use a model that can be changed
    # from one place without touching the rest of the bot.
    model = os.getenv(
        "GEMINI_MODEL",
        "gemini-2.5-flash"
    )

    endpoint = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/{model}:generateContent"
    )

    prompt = f"""
تو دبیر ارشد یک کانال خبری حرفه‌ای فارسی هستی.

خبر زیر را برای انتشار در کانال «نبض خبر» بازنویسی کن.

قوانین بسیار مهم:

1. هیچ واقعیت جدیدی اختراع نکن.
2. نام افراد، اعداد، تاریخ‌ها، مکان‌ها، نقل‌قول‌ها و علت حادثه را تغییر نده.
3. اگر اطلاعاتی در متن نیست، درباره آن حدس نزن.
4. تیتر باید کوتاه، جذاب و خبری باشد.
5. لید باید مهم‌ترین بخش خبر را سریع منتقل کند.
6. متن نهایی بین 1 تا 3 پاراگراف کوتاه باشد.
7. متن تبلیغاتی، کلیشه‌های خبرگزاری و جمله‌های اضافی حذف شوند.
8. از Markdown استفاده نکن.
9. از ایموجی استفاده نکن؛ ایموجی توسط برنامه اضافه می‌شود.
10. اگر خبر سیاسی است، کاملاً بی‌طرف بمان و ادعاها را به منبع یا گوینده نسبت بده.
11. اگر خبر حادثه است، از اغراق و جزئیات تأییدنشده خودداری کن.
12. اگر متن خام ناقص است، آن را با حدس تکمیل نکن.

خروجی فقط JSON معتبر باشد:

{{
  "title": "تیتر نهایی",
  "body": "متن نهایی"
}}

تیتر اصلی:
{title}

متن خام:
{raw_text}
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
            "temperature": 0.25,
            "maxOutputTokens": 900,
            "responseMimeType": "application/json"
        }
    }

    try:

        response = SESSION.post(
            endpoint,
            params={"key": AI_API_KEY},
            json=payload,
            timeout=25
        )

        if not response.ok:

            print(
                f"Gemini error {response.status_code}: "
                f"{response.text[:500]}"
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

        if not parts:
            return None

        result_text = parts[0].get(
            "text",
            ""
        ).strip()

        # Remove accidental code fences.
        result_text = re.sub(
            r"^```(?:json)?",
            "",
            result_text,
            flags=re.I
        )

        result_text = re.sub(
            r"```$",
            "",
            result_text
        ).strip()

        import json

        result = json.loads(
            result_text
        )

        new_title = clean_text(
            result.get("title", "")
        )

        new_body = clean_text(
            result.get("body", "")
        )

        if not new_title:
            new_title = title

        if not new_body:
            return None

        return new_title, new_body

    except Exception as e:

        print(
            f"AI rewrite failed: {e}"
        )

        return None


# =========================================================
# FALLBACK NEWS TEXT
# =========================================================

def fallback_body(raw_text, title):

    text = clean_text(raw_text)

    if not text:
        return ""

    sentences = re.split(
        r"(?<=[.!؟؛])\s+",
        text
    )

    useful = []

    for sentence in sentences:

        sentence = sentence.strip()

        if len(sentence) < 35:
            continue

        if normalize_text(sentence) == normalize_text(title):
            continue

        useful.append(sentence)

        if len(useful) >= 3:
            break

    if not useful:
        return text[:700]

    return "\n\n".join(
        f"🔹 {sentence}"
        for sentence in useful
    )


# =========================================================
# WATERMARK
# =========================================================

def add_watermark(image_url):

    response = http_get(
        image_url,
        timeout=15
    )

    if not response:
        return None

    try:

        image = Image.open(
            io.BytesIO(response.content)
        ).convert("RGBA")

        width, height = image.size

        scale = max(
            1,
            min(width, height) / 900
        )

        font_size_fa = max(
            18,
            int(24 * scale)
        )

        font_size_en = max(
            11,
            int(14 * scale)
        )

        try:

            font_fa = ImageFont.truetype(
                str(FONT_BOLD),
                font_size_fa
            )

            font_en = ImageFont.truetype(
                str(FONT_REGULAR),
                font_size_en
            )

        except Exception:

            font_fa = ImageFont.load_default()
            font_en = ImageFont.load_default()

        overlay = Image.new(
            "RGBA",
            image.size,
            (255, 255, 255, 0)
        )

        draw = ImageDraw.Draw(
            overlay
        )

        padding = max(
            10,
            int(12 * scale)
        )

        text_fa = "نبض خبر"
        text_en = "@NabzKhabarOfficial"

        bbox1 = draw.textbbox(
            (0, 0),
            text_fa,
            font=font_fa
        )

        bbox2 = draw.textbbox(
            (0, 0),
            text_en,
            font=font_en
        )

        text_width = max(
            bbox1[2] - bbox1[0],
            bbox2[2] - bbox2[0]
        )

        box_width = (
            text_width
            + padding * 2
        )

        box_height = int(
            62 * scale
        )

        x = (
            width
            - box_width
            - int(15 * scale)
        )

        y = (
            height
            - box_height
            - int(15 * scale)
        )

        draw.rounded_rectangle(
            [
                x,
                y,
                x + box_width,
                y + box_height
            ],
            radius=int(8 * scale),
            fill=(0, 0, 0, 165)
        )

        draw.text(
            (
                x + padding,
                y + int(5 * scale)
            ),
            text_fa,
            fill=(255, 255, 255, 245),
            font=font_fa
        )

        draw.text(
            (
                x + padding,
                y + int(35 * scale)
            ),
            text_en,
            fill=(220, 230, 255, 235),
            font=font_en
        )

        final_image = Image.alpha_composite(
            image,
            overlay
        ).convert("RGB")

        output = io.BytesIO()

        final_image.save(
            output,
            format="JPEG",
            quality=93,
            optimize=True
        )

        output.seek(0)

        return output

    except Exception as e:

        print(
            f"Watermark error: {e}"
        )

        return None


# =========================================================
# TELEGRAM CAPTION
# =========================================================

def make_caption(
    title,
    body,
    source_name,
    article_url,
    category
):

    icon = CATEGORY_ICONS.get(
        category,
        "📰"
    )

    if category == "فوری":

        headline = (
            f"{icon} <b>فوری | "
            f"{html.escape(title)}</b>"
        )

    else:

        headline = (
            f"{icon} <b>"
            f"{html.escape(title)}"
            f"</b>"
        )

    caption = headline

    if body:

        caption += (
            "\n\n"
            f"{html.escape(body)}"
        )

    if source_name:

        caption += (
            "\n\n"
            f"📡 <b>منبع:</b> "
            f"{html.escape(source_name)}"
        )

    if article_url:

        caption += (
            "\n"
            f"🔗 <a href=\""
            f"{html.escape(article_url, quote=True)}"
            f"\">متن کامل خبر</a>"
        )

    caption += (
        "\n\n"
        "#نبض_خبر"
    )

    # Telegram media caption limit.
    if len(caption) > 1000:

        caption = caption[:995] + "…"

    return caption


# =========================================================
# TELEGRAM API
# =========================================================

def telegram_request(
    method,
    data=None,
    files=None,
    timeout=30
):

    if not BOT_TOKEN:
        print("BOT_TOKEN is missing.")
        return False

    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/{method}"
    )

    try:

        response = SESSION.post(
            url,
            data=data,
            files=files,
            timeout=timeout
        )

        if response.ok:

            result = response.json()

            if result.get("ok"):
                return True

        print(
            f"Telegram {method} error: "
            f"{response.text[:1000]}"
        )

    except Exception as e:

        print(
            f"Telegram request error: {e}"
        )

    return False


# =========================================================
# SEND PHOTO
# =========================================================

def send_photo(
    caption,
    image_url
):

    processed = add_watermark(
        image_url
    )

    if not processed:

        print(
            "Photo processing failed."
        )

        return False

    files = {
        "photo": (
            "nabz-news.jpg",
            processed,
            "image/jpeg"
        )
    }

    data = {
        "chat_id": CHAT_ID,
        "caption": caption,
        "parse_mode": "HTML",
        "disable_notification": False
    }

    return telegram_request(
        "sendPhoto",
        data=data,
        files=files,
        timeout=30
    )


# =========================================================
# SEND VIDEO
# =========================================================

def send_video(
    caption,
    video_url
):

    print(
        f"Downloading video: {video_url}"
    )

    try:

        response = SESSION.get(
            video_url,
            stream=True,
            timeout=25
        )

        if response.status_code != 200:

            print(
                f"Video download failed: "
                f"{response.status_code}"
            )

            return False

        content_length = response.headers.get(
            "Content-Length"
        )

        if content_length:

            try:

                if int(content_length) > VIDEO_MAX_SIZE:

                    print(
                        "Video is larger than "
                        "Telegram bot upload limit."
                    )

                    return False

            except ValueError:
                pass

        buffer = io.BytesIO()

        total = 0

        for chunk in response.iter_content(
            chunk_size=1024 * 256
        ):

            if not chunk:
                continue

            total += len(chunk)

            if total > VIDEO_MAX_SIZE:

                print(
                    "Video exceeded 50MB."
                )

                return False

            buffer.write(chunk)

        if total == 0:

            print(
                "Downloaded video is empty."
            )

            return False

        buffer.seek(0)

        files = {
            "video": (
                "nabz-news.mp4",
                buffer,
                "video/mp4"
            )
        }

        data = {
            "chat_id": CHAT_ID,
            "caption": caption,
            "parse_mode": "HTML",
            "supports_streaming": True,
            "disable_notification": False
        }

        return telegram_request(
            "sendVideo",
            data=data,
            files=files,
            timeout=60
        )

    except Exception as e:

        print(
            f"Video send error: {e}"
        )

        return False


# =========================================================
# SEND NEWS
# =========================================================

def send_news(
    title,
    body,
    source_name,
    article_url,
    category,
    media_url,
    media_type
):

    caption = make_caption(
        title,
        body,
        source_name,
        article_url,
        category
    )

    # Video gets priority.
    if media_type == "video":

        print(
            f"Trying VIDEO for: {title}"
        )

        if send_video(
            caption,
            media_url
        ):

            print(
                "Video published successfully."
            )

            return True

        print(
            "Video failed. Trying image fallback..."
        )

        # If video fails, try article image.
        image_url, fallback_type = (
            extract_media(
                {},
                article_url
            )
        )

        if image_url and fallback_type == "photo":

            return send_photo(
                caption,
                image_url
            )

        return False

    if media_type == "photo":

        print(
            f"Trying PHOTO for: {title}"
        )

        return send_photo(
            caption,
            media_url
        )

    return False


# =========================================================
# MARKET PRICES
# =========================================================

def get_nobitex_usdt():

    try:

        response = http_get(
            "https://api.nobitex.ir/v2/orderbook/USDTIRT",
            timeout=8
        )

        if not response:
            return None

        data = response.json()

        value = data.get(
            "lastTradePrice"
        )

        if value is None:
            return None

        # Nobitex gives IRR.
        return int(
            float(value) / 10
        )

    except Exception as e:

        print(
            f"USDT price error: {e}"
        )

        return None


def send_market_prices(history):

    now = datetime.now(
        TEHRAN_TZ
    )

    # 3 updates per Tehran day.
    block = now.hour // 8

    key = (
        f"MARKET_"
        f"{now.strftime('%Y-%m-%d')}_"
        f"{block}"
    )

    if key in history:

        return False

    usdt = get_nobitex_usdt()

    if not usdt:
        return False

    caption = (
        "📊 <b>نبض بازار</b>\n\n"
        f"💵 <b>تتر / دلار تقریبی:</b> "
        f"{usdt:,} تومان\n\n"
        "ℹ️ نرخ‌ها ممکن است با بازار نقدی "
        "تفاوت داشته باشند.\n\n"
        "#نبض_بازار"
    )

    success = telegram_request(
        "sendMessage",
        data={
            "chat_id": CHAT_ID,
            "text": caption,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        },
        timeout=15
    )

    if success:

        history.append(key)
        save_sent_news(history)

    return success


# =========================================================
# COLLECT NEWS
# =========================================================

def collect_candidates(history):

    candidates = []

    seen_titles = []

    sent_set = set(history)

    for source_name, feed_url in RSS_FEEDS.items():

        print(
            f"Checking: {source_name}"
        )

        feed = fetch_feed(
            feed_url
        )

        if not feed:
            continue

        entries = feed.entries[
            :MAX_ENTRIES_PER_FEED
        ]

        for entry in entries:

            title = clean_text(
                entry.get("title", ""),
                is_title=True
            )

            title = title.strip()

            if not title:
                continue

            article_url = (
                entry.get("link", "")
                or ""
            ).strip()

            if not article_url:
                continue

            news_id = make_news_id(
                entry,
                source_name
            )

            if news_id in sent_set:
                continue

            # Duplicate inside current run.
            duplicate = False

            for previous in seen_titles:

                if is_similar(
                    title,
                    previous
                ):

                    duplicate = True
                    break

            if duplicate:
                continue

            raw_text = clean_text(
                entry.get(
                    "summary",
                    entry.get(
                        "description",
                        ""
                    )
                )
            )

            media_url, media_type = extract_media(
                entry,
                article_url
            )

            # We do NOT mark media-less stories as sent.
            # They can be retried in the next run.
            if not media_url:
                print(
                    f"No media found: {title}"
                )
                continue

            category = detect_category(
                title,
                source_name
            )

            candidates.append({
                "id": news_id,
                "title": title,
                "raw_text": raw_text,
                "source": source_name,
                "url": article_url,
                "media_url": media_url,
                "media_type": media_type,
                "category": category,
            })

            seen_titles.append(title)

    return candidates


# =========================================================
# PRIORITY
# =========================================================

def candidate_priority(item):

    category = item["category"]

    score = 0

    if category == "فوری":
        score += 100

    if item["media_type"] == "video":
        score += 20

    # Give underrepresented categories a little room.
    category_bonus = {
        "ورزش": 8,
        "اقتصاد": 8,
        "فناوری": 8,
        "حوادث": 12,
        "سلامت": 6,
        "خودرو": 5,
        "علم": 4,
        "فرهنگ": 4,
        "جهان": 7,
        "اجتماعی": 5,
        "ایران": 7,
        "عمومی": 2,
    }

    score += category_bonus.get(
        category,
        0
    )

    return score


# =========================================================
# AI + FALLBACK PREPARATION
# =========================================================

def prepare_news(item):

    title = item["title"]
    raw_text = item["raw_text"]

    ai_result = ai_rewrite(
        title,
        raw_text
    )

    if ai_result:

        final_title, final_body = ai_result

    else:

        final_title = title
        final_body = fallback_body(
            raw_text,
            title
        )

    return final_title, final_body


# =========================================================
# MAIN
# =========================================================

def main():

    print("=" * 60)
    print("NABZ KHABAR BOT STARTED")
    print("=" * 60)

    if not BOT_TOKEN:

        print(
            "ERROR: BOT_TOKEN secret is missing."
        )

        return

    history = load_sent_news()

    print(
        f"History entries: {len(history)}"
    )

    # ---------------------------------------------
    # Market update
    # ---------------------------------------------

    try:

        send_market_prices(
            history
        )

    except Exception as e:

        print(
            f"Market update skipped: {e}"
        )

    # ---------------------------------------------
    # Collect
    # ---------------------------------------------

    candidates = collect_candidates(
        history
    )

    print(
        f"Candidates found: {len(candidates)}"
    )

    if not candidates:

        print(
            "No publishable news found."
        )

        save_sent_news(history)

        return

    # ---------------------------------------------
    # Priority
    # ---------------------------------------------

    candidates.sort(
        key=candidate_priority,
        reverse=True
    )

    published = 0

    used_categories = set()

    # ---------------------------------------------
    # First pass:
    # Prefer category diversity.
    # ---------------------------------------------

    ordered = []

    for item in candidates:

        if item["category"] not in used_categories:

            ordered.append(item)

            used_categories.add(
                item["category"]
            )

    # ---------------------------------------------
    # Second pass:
    # Fill remaining slots.
    # ---------------------------------------------

    for item in candidates:

        if item not in ordered:

            ordered.append(item)

    # ---------------------------------------------
    # Publish
    # ---------------------------------------------

    for item in ordered:

        if published >= MAX_NEWS_PER_RUN:
            break

        print("-" * 60)

        print(
            f"Publishing: {item['title']}"
        )

        final_title, final_body = prepare_news(
            item
        )

        success = send_news(
            title=final_title,
            body=final_body,
            source_name=item["source"],
            article_url=item["url"],
            category=item["category"],
            media_url=item["media_url"],
            media_type=item["media_type"]
        )

        if success:

            history.append(
                item["id"]
            )

            save_sent_news(
                history
            )

            published += 1

            print(
                f"Published successfully: "
                f"{published}/{MAX_NEWS_PER_RUN}"
            )

            time.sleep(3)

        else:

            print(
                "Publication failed; "
                "news will NOT be marked as sent."
            )

    save_sent_news(
        history
    )

    print("=" * 60)

    print(
        f"FINISHED - Published: {published}"
    )

    print("=" * 60)


if __name__ == "__main__":
    main()
