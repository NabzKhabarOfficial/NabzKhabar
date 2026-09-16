import os
import re
import json
import html
import hashlib
import logging
import time
import warnings
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import feedparser
from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning
from PIL import Image, ImageDraw, ImageFont


# =========================================================
# WARNING
# =========================================================

warnings.filterwarnings(
    "ignore",
    category=MarkupResemblesLocatorWarning
)


# =========================================================
# CONFIG
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
AI_API_KEY = os.getenv("AI_API_KEY")

CHANNEL = "@NabzKhabarOfficial"

GEMINI_MODEL = "gemini-3.5-flash-lite"

MAX_NEWS_PER_RUN = int(
    os.getenv("MAX_NEWS_PER_RUN", "4")
)

RUN_DEADLINE_SECONDS = 180

MAX_ENTRIES_PER_FEED = 8

RSS_TIMEOUT = (5, 8)
ARTICLE_TIMEOUT = (5, 12)
TELEGRAM_TIMEOUT = (10, 30)
AI_TIMEOUT = (10, 30)

HISTORY_FILE = "sent_news.txt"

FONT_BOLD = "Vazirmatn-Bold.ttf"


# =========================================================
# RSS
# =========================================================

RSS_FEEDS = [
    ("ایران", "https://www.yjc.ir/fa/rss/allnews"),
    ("ایران", "https://www.irna.ir/rss"),
    ("ایران", "https://www.isna.ir/rss"),
    ("ایران", "https://www.mehrnews.com/rss"),

    ("فناوری", "https://www.zoomit.ir/feed/"),
    ("فناوری", "https://digiato.com/feed"),

    ("ورزش", "https://www.isna.ir/rss?serviceid=5"),

    ("اقتصاد", "https://www.isna.ir/rss/service/economy"),

    ("جهان", "https://www.irna.ir/rss/service/world"),
    ("جهان", "https://www.isna.ir/rss/service/world"),

    ("فرهنگ", "https://www.irna.ir/rss/service/culture"),
    ("جامعه", "https://www.irna.ir/rss/service/society"),
]


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s"
)

log = logging.getLogger("NABZ")


# =========================================================
# SESSION
# =========================================================

SESSION = requests.Session()

SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/130 Safari/537.36"
    ),
    "Accept-Language": "fa,en;q=0.8",
})


# =========================================================
# TEXT
# =========================================================

def normalize_spaces(text):

    if not text:
        return ""

    text = str(text)

    text = text.replace("\r", "\n")
    text = text.replace("\u200c", " ")
    text = text.replace("\u200f", "")
    text = text.replace("\u200e", "")

    text = html.unescape(text)

    text = re.sub(
        r"https?://\S+",
        "",
        text,
        flags=re.I
    )

    text = re.sub(
        r"www\.\S+",
        "",
        text,
        flags=re.I
    )

    text = re.sub(
        r"@\w+",
        "",
        text
    )

    text = re.sub(
        r"[ \t]+",
        " ",
        text
    )

    text = re.sub(
        r"\n\s*\n+",
        "\n\n",
        text
    )

    return text.strip()


def clean_text(text):

    if not text:
        return ""

    raw = str(text).strip()

    if re.fullmatch(
        r"https?://\S+",
        raw,
        flags=re.I
    ):
        return ""

    try:
        text = BeautifulSoup(
            raw,
            "html.parser"
        ).get_text(
            " ",
            strip=True
        )
    except Exception:
        text = raw

    return normalize_spaces(text)


# =========================================================
# SOURCE CLEANING
# =========================================================

SOURCE_NAMES = (
    "ایرنا",
    "مهر",
    "ایسنا",
    "تسنیم",
    "فارس",
    "ایلنا",
    "برنا",
    "ایمنا",
    "باشگاه خبرنگاران جوان",
    "خبرگزاری مهر",
    "خبرگزاری ایرنا",
    "خبرگزاری ایسنا",
)


def remove_dateline_source(text):

    if not text:
        return ""

    text = clean_text(text)

    source_pattern = "|".join(
        re.escape(x)
        for x in SOURCE_NAMES
    )

    patterns = [

        rf"^[\u0600-\u06FF‌]+(?:\s*[-–—]\s*)"
        rf"(?:{source_pattern})\s*[-–—:]\s*",

        rf"^[\u0600-\u06FF‌]+(?:\s+[\u0600-\u06FF‌]+)?"
        rf"\s*[-–—]\s*(?:{source_pattern})"
        rf"\s*[-–—:]\s*",

        rf"^(?:{source_pattern})\s*[-–—:]\s*",
    ]

    for pattern in patterns:

        text = re.sub(
            pattern,
            "",
            text,
            flags=re.I
        )

    return text.strip()


def remove_media_marker(text):

    if not text:
        return ""

    text = clean_text(text)

    text = re.sub(
        r"^\s*"
        r"(?:فیلم|ویدئو|ویدیو|تصاویر|گزارش تصویری)"
        r"\s*[|:：\-–—]\s*",
        "",
        text,
        flags=re.I
    )

    return text.strip()


def remove_source_phrase(text):

    if not text:
        return ""

    text = remove_dateline_source(text)

    for _ in range(3):

        old = text

        text = re.sub(
            r"^به گزارش\s+خبرنگار\s+"
            r"[^،:؛.\n]+"
            r"[،:؛.\-–—]\s*",
            "",
            text,
            flags=re.I
        )

        text = re.sub(
            r"^به گزارش\s+خبرگزاری\s+"
            r"[^،:؛.\n]+"
            r"[،:؛.\-–—]\s*",
            "",
            text,
            flags=re.I
        )

        text = re.sub(
            r"^به گزارش\s+"
            r"[^،:؛.\n]+"
            r"[،:؛.\-–—]\s*",
            "",
            text,
            flags=re.I
        )

        text = re.sub(
            r"^به نقل از\s+"
            r"[^،:؛.\n]+"
            r"[،:؛.\-–—]\s*",
            "",
            text,
            flags=re.I
        )

        text = remove_dateline_source(text)

        if text == old:
            break

    return text.strip()


def clean_content(text):

    text = clean_text(text)
    text = remove_media_marker(text)
    text = remove_source_phrase(text)
    text = remove_dateline_source(text)

    return text.strip()


# =========================================================
# TITLE
# =========================================================

def clean_title(title):

    title = clean_content(title)

    title = re.sub(
        r"^\s*(?:خبر فوری|فوری|اختصاصی)"
        r"\s*[:：\-–—]?\s*",
        "",
        title,
        flags=re.I
    )

    title = re.sub(
        r"#\S+",
        "",
        title
    )

    title = re.sub(
        r"\s+",
        " ",
        title
    )

    return title.strip()


def normalize_title(title):

    title = clean_title(title).lower()

    title = title.replace("ي", "ی")
    title = title.replace("ك", "ک")
    title = title.replace("ۀ", "ه")
    title = title.replace("ة", "ه")

    title = re.sub(
        r"[^\w\u0600-\u06ff ]",
        " ",
        title
    )

    title = re.sub(
        r"\s+",
        " ",
        title
    )

    return title.strip()


def make_news_id(title, link):

    base = (
        normalize_title(title)
        + "|"
        + (link or "")
    )

    return hashlib.sha256(
        base.encode("utf-8")
    ).hexdigest()


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
            encoding="utf-8"
        ) as f:

            return {
                x.strip()
                for x in f
                if x.strip()
            }

    except Exception:
        return set()


def save_history(history):

    try:

        items = list(history)

        if len(items) > 500:
            items = items[-500:]

        with open(
            HISTORY_FILE,
            "w",
            encoding="utf-8"
        ) as f:

            for item in items:
                f.write(item + "\n")

    except Exception as e:

        log.info(
            f"History save error: {e}"
        )


# =========================================================
# DEADLINE
# =========================================================

def deadline_reached(start_time):

    return (
        time.monotonic()
        - start_time
        >= RUN_DEADLINE_SECONDS
    )


# =========================================================
# RSS
# =========================================================

def fetch_feed(source):

    category, url = source

    try:

        response = SESSION.get(
            url,
            timeout=RSS_TIMEOUT
        )

        response.raise_for_status()

        parsed = feedparser.parse(
            response.content
        )

        entries = parsed.entries[
            :MAX_ENTRIES_PER_FEED
        ]

        log.info(
            f"RSS OK: {category} | "
            f"{len(entries)} | {url}"
        )

        return category, entries

    except Exception as e:

        log.info(
            f"RSS FAILED: {category} | "
            f"{e}"
        )

        return category, []


def get_entry_timestamp(entry):

    for key in (
        "published_parsed",
        "updated_parsed",
        "created_parsed"
    ):

        value = entry.get(key)

        if value:

            try:
                return time.mktime(value)
            except Exception:
                pass

    return 0


def collect_candidates(history, start_time):

    candidates = []
    seen_ids = set()

    with ThreadPoolExecutor(
        max_workers=8
    ) as executor:

        futures = [
            executor.submit(
                fetch_feed,
                source
            )
            for source in RSS_FEEDS
        ]

        for future in as_completed(futures):

            if deadline_reached(start_time):
                break

            try:
                category, entries = future.result()
            except Exception:
                continue

            for entry in entries:

                title = clean_title(
                    entry.get("title", "")
                )

                link = (
                    entry.get("link")
                    or entry.get("id")
                    or ""
                ).strip()

                if not title or not link:
                    continue

                news_id = make_news_id(
                    title,
                    link
                )

                if news_id in history:
                    continue

                if news_id in seen_ids:
                    continue

                seen_ids.add(news_id)

                summary = clean_content(
                    entry.get("summary")
                    or entry.get("description")
                    or entry.get(
                        "content",
                        [{}]
                    )[0].get(
                        "value",
                        ""
                    )
                )

                candidates.append({
                    "id": news_id,
                    "category": category,
                    "title": title,
                    "link": link,
                    "summary": summary,
                    "entry": entry,
                    "timestamp":
                        get_entry_timestamp(
                            entry
                        ),
                })

    candidates.sort(
        key=lambda x: x.get(
            "timestamp",
            0
        ),
        reverse=True
    )

    log.info(
        f"Candidates found: {len(candidates)}"
    )

    return candidates


# =========================================================
# MEDIA DETECTION
# =========================================================

def is_video_title(title):

    return bool(
        re.search(
            r"^\s*(?:فیلم|ویدئو|ویدیو)"
            r"\s*[|:：\-–—]",
            title,
            flags=re.I
        )
    )


def absolute_url(url, base_url):

    if not url:
        return ""

    url = html.unescape(
        str(url).strip()
    )

    if url.startswith("//"):
        return "https:" + url

    if url.startswith("/"):
        from urllib.parse import urljoin
        return urljoin(url, url)

    return url


def extract_video_from_soup(
    soup,
    page_url
):

    # -----------------------------------------------------
    # META
    # -----------------------------------------------------

    for prop in (
        "og:video",
        "og:video:url",
        "og:video:secure_url",
        "twitter:player:stream"
    ):

        tag = soup.find(
            "meta",
            attrs={
                "property": prop
            }
        )

        if not tag:

            tag = soup.find(
                "meta",
                attrs={
                    "name": prop
                }
            )

        if tag and tag.get("content"):

            url = absolute_url(
                tag["content"],
                page_url
            )

            if url:
                return url

    # -----------------------------------------------------
    # VIDEO TAG
    # -----------------------------------------------------

    for video in soup.find_all("video"):

        for source in video.find_all(
            "source"
        ):

            url = (
                source.get("src")
                or source.get("data-src")
            )

            if url:

                url = absolute_url(
                    url,
                    page_url
                )

                if url:
                    return url

        for attr in (
            "src",
            "data-src",
            "data-video"
        ):

            url = video.get(attr)

            if url:

                url = absolute_url(
                    url,
                    page_url
                )

                if url:
                    return url

    # -----------------------------------------------------
    # SOURCE TAG
    # -----------------------------------------------------

    for source in soup.find_all(
        "source"
    ):

        url = (
            source.get("src")
            or source.get("data-src")
        )

        if url:

            url = absolute_url(
                url,
                page_url
            )

            if url:
                return url

    # -----------------------------------------------------
    # JSON-LD
    # -----------------------------------------------------

    for script in soup.find_all(
        "script",
        type="application/ld+json"
    ):

        try:

            data = json.loads(
                script.string or
                script.get_text()
            )

            objects = (
                data
                if isinstance(data, list)
                else [data]
            )

            for obj in objects:

                if not isinstance(obj, dict):
                    continue

                candidates = []

                for key in (
                    "contentUrl",
                    "video",
                    "url"
                ):

                    value = obj.get(key)

                    if isinstance(value, str):
                        candidates.append(value)

                    elif isinstance(value, dict):
                        candidates.append(
                            value.get("contentUrl")
                            or value.get("url")
                            or ""
                        )

                for value in candidates:

                    if not value:
                        continue

                    if (
                        ".mp4" in value.lower()
                        or ".webm" in value.lower()
                        or "video" in value.lower()
                    ):

                        return absolute_url(
                            value,
                            page_url
                        )

        except Exception:
            continue

    return None


def extract_rss_media(entry):

    # media_content
    for media in entry.get(
        "media_content",
        []
    ):

        url = (
            media.get("url")
            or media.get("href")
        )

        if not url:
            continue

        mime = (
            media.get("type")
            or ""
        ).lower()

        if (
            "video" in mime
            or re.search(
                r"\.(mp4|webm|mov)(?:\?|$)",
                url,
                re.I
            )
        ):

            return {
                "type": "video",
                "url": url
            }

        if "image" in mime:

            return {
                "type": "image",
                "url": url
            }

    # enclosures
    for enclosure in entry.get(
        "enclosures",
        []
    ):

        url = (
            enclosure.get("href")
            or enclosure.get("url")
        )

        if not url:
            continue

        mime = (
            enclosure.get("type")
            or ""
        ).lower()

        if (
            "video" in mime
            or re.search(
                r"\.(mp4|webm|mov)(?:\?|$)",
                url,
                re.I
            )
        ):

            return {
                "type": "video",
                "url": url
            }

        return {
            "type": "image",
            "url": url
        }

    # RSS HTML
    raw = (
        entry.get("summary")
        or entry.get("description")
        or ""
    )

    try:

        soup = BeautifulSoup(
            str(raw),
            "html.parser"
        )

        video = soup.find("video")

        if video:

            url = (
                video.get("src")
                or (
                    video.find("source")
                    or {}
                ).get("src")
            )

            if url:

                return {
                    "type": "video",
                    "url": url
                }

        img = soup.find("img")

        if img and img.get("src"):

            return {
                "type": "image",
                "url": img["src"]
            }

    except Exception:
        pass

    return None


def extract_article_data(url):

    try:

        response = SESSION.get(
            url,
            timeout=ARTICLE_TIMEOUT
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.content,
            "html.parser"
        )

        media = extract_video_from_soup(
            soup,
            url
        )

        image_url = None

        if not media:

            og = soup.find(
                "meta",
                property="og:image"
            )

            if og and og.get("content"):
                image_url = absolute_url(
                    og["content"],
                    url
                )

        # remove useless page elements
        for tag in soup([
            "script",
            "style",
            "noscript",
            "nav",
            "footer",
            "header",
            "aside",
            "form",
            "button",
            "svg",
            "iframe",
            "figure",
            "figcaption"
        ]):

            tag.decompose()

        containers = []

        for selector in (
            "article",
            "[itemprop='articleBody']",
            ".article-body",
            ".article-content",
            ".news-content",
            ".news-detail",
            ".content",
            ".post-content",
            ".single-content",
            ".entry-content",
            ".post-body",
            ".story-body",
            ".news-body"
        ):

            try:
                containers.extend(
                    soup.select(selector)
                )
            except Exception:
                pass

        paragraphs = []

        for container in containers:

            for p in container.find_all("p"):

                text = clean_content(
                    p.get_text(
                        " ",
                        strip=True
                    )
                )

                if len(text) >= 35:
                    paragraphs.append(text)

        if len(paragraphs) < 2:

            paragraphs = []

            for p in soup.find_all("p"):

                text = clean_content(
                    p.get_text(
                        " ",
                        strip=True
                    )
                )

                if len(text) >= 35:
                    paragraphs.append(text)

        unique = []
        seen = set()

        for p in paragraphs:

            key = normalize_title(p)

            if key in seen:
                continue

            seen.add(key)
            unique.append(p)

        article_text = "\n\n".join(
            unique[:20]
        )

        result_media = None

        if media:
            result_media = {
                "type": "video",
                "url": media
            }

        elif image_url:

            result_media = {
                "type": "image",
                "url": image_url
            }

        return {
            "text": article_text,
            "media": result_media
        }

    except Exception as e:

        log.info(
            f"Article extraction failed: {e}"
        )

        return {
            "text": "",
            "media": None
        }


# =========================================================
# GEMINI
# =========================================================

def gemini_request(
    title,
    category,
    article_text
):

    if not AI_API_KEY:
        return None

    endpoint = (
        "https://generativelanguage.googleapis.com/"
        "v1beta/models/"
        f"{GEMINI_MODEL}:generateContent"
        f"?key={AI_API_KEY}"
    )

    prompt = f"""
تو ویراستار حرفه‌ای یک کانال خبری فارسی هستی.

خبر زیر را برای انتشار در کانال «نبض خبر» آماده کن.

دستورهای بسیار مهم:

1. هیچ واقعیت جدیدی اضافه نکن.
2. عددها، نام اشخاص، سمت‌ها، تاریخ‌ها و آمار را دقیقاً حفظ کن.
3. منبع خبر، نام خبرگزاری، لینک، عبارت «به گزارش»،
   «به نقل از»، «ایرنا»، «مهر»، «ایسنا» و مشابه آن
   را در متن نهایی نیاور.
4. اگر عنوان با «فیلم|»، «ویدئو|»، «ویدیو|» یا «تصاویر|»
   شروع شده، این برچسب را حذف کن.
5. متن را طبیعی، روان و حرفه‌ای فارسی کن.
6. از لحن تبلیغاتی و اغراق‌آمیز استفاده نکن.
7. اگر خبر کوتاه است، آن را بی‌دلیل طولانی نکن.
8. اطلاعات تکراری را حذف کن.
9. حداکثر 3 پاراگراف کوتاه بنویس.
10. متن باید مستقیماً قابل انتشار باشد.
11. source و link اصلاً در خروجی نباشد.
12. فقط JSON معتبر برگردان.

دسته:
{category}

عنوان:
{title}

متن:
{article_text}

فرمت دقیق خروجی:

{{
  "title": "عنوان تمیز و حرفه‌ای",
  "body": "متن خبر در چند پاراگراف",
  "is_video": true
}}

اگر خبر ویدئویی نیست:
"is_video": false
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
            "responseMimeType": "application/json"
        }
    }

    try:

        response = SESSION.post(
            endpoint,
            json=payload,
            timeout=AI_TIMEOUT
        )

        if response.status_code == 429:

            log.info(
                "Gemini 429 - using local fallback."
            )

            return None

        if not response.ok:

            log.info(
                "Gemini error: "
                + response.text[:500]
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

        text = parts[0].get(
            "text",
            ""
        ).strip()

        text = re.sub(
            r"^```json\s*",
            "",
            text,
            flags=re.I
        )

        text = re.sub(
            r"\s*```$",
            "",
            text
        )

        result = json.loads(text)

        if not isinstance(result, dict):
            return None

        final_title = clean_title(
            result.get("title", "")
        )

        final_body = clean_content(
            result.get("body", "")
        )

        if not final_title or not final_body:
            return None

        return {
            "title": final_title,
            "body": final_body,
            "is_video": bool(
                result.get(
                    "is_video",
                    False
                )
            )
        }

    except Exception as e:

        log.info(
            f"Gemini failed: {e}"
        )

        return None


# =========================================================
# LOCAL FALLBACK
# =========================================================

def split_sentences(text):

    text = clean_content(text)

    if not text:
        return []

    parts = re.split(
        r"(?<=[.!؟])\s+|\n+",
        text
    )

    result = []

    for p in parts:

        p = clean_content(p)

        if len(p) >= 35:
            result.append(p)

    return result


def similarity(a, b):

    wa = set(
        normalize_title(a).split()
    )

    wb = set(
        normalize_title(b).split()
    )

    if not wa or not wb:
        return 0

    return len(
        wa & wb
    ) / max(
        1,
        len(wa | wb)
    )


def local_news_writer(
    title,
    text
):

    title = clean_title(title)

    sentences = split_sentences(
        text
    )

    if not sentences:
        return None

    selected = []

    for sentence in sentences:

        if any(
            similarity(
                sentence,
                old
            ) >= 0.72
            for old in selected
        ):
            continue

        selected.append(sentence)

        if len(selected) >= 4:
            break

    body = " ".join(selected)

    if len(body) > 1800:

        body = body[:1800]

        last_space = body.rfind(" ")

        if last_space > 100:
            body = body[:last_space]

        body += "…"

    if len(body) < 80:
        return None

    return {
        "title": title,
        "body": body,
        "is_video": is_video_title(title)
    }


# =========================================================
# IMAGE
# =========================================================

def download_image(url):

    try:

        response = SESSION.get(
            url,
            timeout=ARTICLE_TIMEOUT
        )

        response.raise_for_status()

        if (
            "image"
            not in response.headers.get(
                "Content-Type",
                ""
            ).lower()
        ):
            return None

        image = Image.open(
            BytesIO(response.content)
        ).convert("RGB")

        image.thumbnail(
            (1600, 1600)
        )

        return image

    except Exception as e:

        log.info(
            f"Image download failed: {e}"
        )

        return None


def add_watermark(image):

    try:

        draw = ImageDraw.Draw(
            image
        )

        try:

            font = ImageFont.truetype(
                FONT_BOLD,
                max(
                    24,
                    image.width // 35
                )
            )

        except Exception:

            font = ImageFont.load_default()

        text = "نبض خبر | NABZ"

        bbox = draw.textbbox(
            (0, 0),
            text,
            font=font
        )

        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]

        margin = max(
            15,
            image.width // 60
        )

        x = (
            image.width
            - tw
            - margin
        )

        y = (
            image.height
            - th
            - margin
        )

        draw.text(
            (
                x + 2,
                y + 2
            ),
            text,
            font=font,
            fill=(0, 0, 0)
        )

        draw.text(
            (
                x,
                y
            ),
            text,
            font=font,
            fill=(255, 255, 255)
        )

        return image

    except Exception:
        return image


def image_to_bytes(image):

    output = BytesIO()

    image.save(
        output,
        format="JPEG",
        quality=88,
        optimize=True
    )

    output.seek(0)

    return output


# =========================================================
# VIDEO
# =========================================================

def download_video(url):

    try:

        log.info(
            f"Downloading video: {url}"
        )

        response = SESSION.get(
            url,
            timeout=ARTICLE_TIMEOUT,
            stream=True,
            allow_redirects=True
        )

        response.raise_for_status()

        content_type = (
            response.headers.get(
                "Content-Type",
                ""
            ).lower()
        )

        content_length = response.headers.get(
            "Content-Length"
        )

        if content_length:

            try:

                size_mb = (
                    int(content_length)
                    / 1024
                    / 1024
                )

                if size_mb > 49:

                    log.info(
                        f"Video too large: "
                        f"{size_mb:.1f} MB"
                    )

                    return None

            except Exception:
                pass

        data = BytesIO()

        total = 0

        for chunk in response.iter_content(
            chunk_size=1024 * 256
        ):

            if not chunk:
                continue

            total += len(chunk)

            if total > 49 * 1024 * 1024:

                log.info(
                    "Video exceeded size limit."
                )

                return None

            data.write(chunk)

        data.seek(0)

        if (
            "video" not in content_type
            and not re.search(
                r"\.(mp4|webm|mov)(?:\?|$)",
                url,
                re.I
            )
        ):

            log.info(
                f"Not a direct video file: "
                f"{content_type}"
            )

            return None

        return data

    except Exception as e:

        log.info(
            f"Video download failed: {e}"
        )

        return None


# =========================================================
# TELEGRAM
# =========================================================

def telegram_url(method):

    return (
        f"https://api.telegram.org/bot"
        f"{BOT_TOKEN}/{method}"
    )


def send_video(video_data, caption):

    try:

        files = {
            "video": (
                "nabz.mp4",
                video_data,
                "video/mp4"
            )
        }

        data = {
            "chat_id": CHANNEL,
            "caption": caption,
            "parse_mode": "HTML"
        }

        response = SESSION.post(
            telegram_url("sendVideo"),
            data=data,
            files=files,
            timeout=TELEGRAM_TIMEOUT
        )

        if response.ok:

            log.info(
                "VIDEO PUBLISHED"
            )

            return True

        log.info(
            "Telegram video error: "
            + response.text[:500]
        )

    except Exception as e:

        log.info(
            f"Telegram video exception: {e}"
        )

    return False


def send_photo(image, caption):

    try:

        files = {
            "photo": (
                "nabz.jpg",
                image,
                "image/jpeg"
            )
        }

        data = {
            "chat_id": CHANNEL,
            "caption": caption,
            "parse_mode": "HTML"
        }

        response = SESSION.post(
            telegram_url("sendPhoto"),
            data=data,
            files=files,
            timeout=TELEGRAM_TIMEOUT
        )

        if response.ok:

            log.info(
                "PHOTO PUBLISHED"
            )

            return True

        log.info(
            "Telegram photo error: "
            + response.text[:500]
        )

    except Exception as e:

        log.info(
            f"Telegram photo exception: {e}"
        )

    return False


def send_text(caption):

    try:

        data = {
            "chat_id": CHANNEL,
            "text": caption,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }

        response = SESSION.post(
            telegram_url("sendMessage"),
            data=data,
            timeout=TELEGRAM_TIMEOUT
        )

        if response.ok:

            log.info(
                "TEXT PUBLISHED"
            )

            return True

        log.info(
            "Telegram text error: "
            + response.text[:500]
        )

    except Exception as e:

        log.info(
            f"Telegram text exception: {e}"
        )

    return False


# =========================================================
# CAPTION
# =========================================================

def make_caption(
    title,
    body
):

    title = clean_title(title)
    body = clean_content(body)

    if not title or not body:
        return None

    title = html.escape(title)
    body = html.escape(body)

    caption = (
        f"📰 <b>{title}</b>\n\n"
        f"{body}\n\n"
        f"#نبض_خبر"
    )

    if len(caption) > 1024:

        available = (
            1024
            - len(
                f"📰 <b>{title}</b>\n\n"
                f"\n\n#نبض_خبر"
            )
            - 10
        )

        if available < 100:
            return None

        shortened = body[:available]

        last_space = shortened.rfind(" ")

        if last_space > 80:
            shortened = shortened[
                :last_space
            ]

        caption = (
            f"📰 <b>{title}</b>\n\n"
            f"{shortened}…\n\n"
            f"#نبض_خبر"
        )

    return caption


# =========================================================
# QUALITY
# =========================================================

def quality_check(
    title,
    body
):

    title = clean_title(title)
    body = clean_content(body)

    if len(title) < 8:
        return False

    if len(body) < 50:
        return False

    forbidden = [
        "فهرست مطالب",
        "مطالب مرتبط",
        "مطالب پیشنهادی",
        "تبلیغات",
        "خبرنامه",
        "کپی لینک",
        "ارسال نظر",
        "اشتراک گذاری",
        "بیشتر بخوانید",
        "ادامه مطلب",
        "به گزارش خبرنگار",
        "به گزارش خبرگزاری",
        "به نقل از خبرگزاری"
    ]

    normalized = normalize_title(
        body
    )

    for word in forbidden:

        if normalize_title(word) in normalized:
            return False

    if re.search(
        r"https?://|www\.",
        body,
        flags=re.I
    ):
        return False

    return True


# =========================================================
# PROCESS
# =========================================================

def process_news(
    news,
    history,
    start_time
):

    if deadline_reached(start_time):
        return False

    original_title = news["title"]

    log.info(
        f"Processing: {original_title}"
    )

    # -----------------------------------------------------
    # RSS MEDIA
    # -----------------------------------------------------

    media = extract_rss_media(
        news["entry"]
    )

    # -----------------------------------------------------
    # ARTICLE
    # -----------------------------------------------------

    article = extract_article_data(
        news["link"]
    )

    article_text = article.get(
        "text",
        ""
    )

    article_media = article.get(
        "media"
    )

    # Prefer actual article video
    if (
        article_media
        and article_media.get("type")
        == "video"
    ):

        media = article_media

    elif not media and article_media:

        media = article_media

    # -----------------------------------------------------
    # COMBINE TEXT
    # -----------------------------------------------------

    text = article_text

    if len(text) < 100:

        text = news["summary"]

    if not text:

        text = news["summary"]

    # -----------------------------------------------------
    # GEMINI
    # -----------------------------------------------------

    ai_result = gemini_request(
        original_title,
        news["category"],
        text
    )

    if ai_result:

        final_title = ai_result["title"]
        final_body = ai_result["body"]

        ai_video = ai_result.get(
            "is_video",
            False
        )

        if (
            ai_video
            and media
            and media.get("type")
            == "image"
        ):

            video_data = extract_article_data(
                news["link"]
            )

            if (
                video_data.get("media")
                and video_data["media"].get(
                    "type"
                ) == "video"
            ):

                media = video_data["media"]

    else:

        log.info(
            "Using local news engine."
        )

        local = local_news_writer(
            original_title,
            text
        )

        if not local:
            return False

        final_title = local["title"]
        final_body = local["body"]

    # -----------------------------------------------------
    # TITLE VIDEO MARKER
    # -----------------------------------------------------

    video_expected = (
        is_video_title(
            original_title
        )
        or (
            ai_result
            and ai_result.get(
                "is_video",
                False
            )
        )
    )

    # -----------------------------------------------------
    # IF VIDEO NEWS, FORCE VIDEO SEARCH
    # -----------------------------------------------------

    if video_expected:

        if not (
            media
            and media.get("type")
            == "video"
        ):

            log.info(
                "Video news detected. "
                "Searching page for video..."
            )

            fresh = extract_article_data(
                news["link"]
            )

            if (
                fresh.get("media")
                and fresh["media"].get(
                    "type"
                ) == "video"
            ):

                media = fresh["media"]

    # -----------------------------------------------------
    # QUALITY
    # -----------------------------------------------------

    if not quality_check(
        final_title,
        final_body
    ):

        log.info(
            "SKIPPED: quality check failed"
        )

        return False

    caption = make_caption(
        final_title,
        final_body
    )

    if not caption:
        return False

    published = False

    # =====================================================
    # VIDEO FIRST
    # =====================================================

    if (
        media
        and media.get("type")
        == "video"
    ):

        video_url = media.get(
            "url"
        )

        if video_url:

            video_data = download_video(
                video_url
            )

            if video_data:

                published = send_video(
                    video_data,
                    caption
                )

    # =====================================================
    # IMAGE
    # =====================================================

    if (
        not published
        and media
        and media.get("type")
        == "image"
    ):

        image_url = media.get(
            "url"
        )

        if image_url:

            image = download_image(
                image_url
            )

            if image:

                image = add_watermark(
                    image
                )

                image_bytes = image_to_bytes(
                    image
                )

                published = send_photo(
                    image_bytes,
                    caption
                )

    # =====================================================
    # TEXT FALLBACK
    # =====================================================

    if not published:

        published = send_text(
            caption
        )

    # =====================================================
    # HISTORY
    # =====================================================

    if published:

        history.add(
            news["id"]
        )

        save_history(history)

        log.info(
            f"PUBLISHED: {final_title}"
        )

        return True

    log.info(
        f"FAILED: {final_title}"
    )

    return False


# =========================================================
# MAIN
# =========================================================

def main():

    start_time = time.monotonic()

    log.info("")
    log.info(
        "===================================="
    )
    log.info(
        "NABZ KHABAR BOT v5"
    )
    log.info(
        "GEMINI + VIDEO ENGINE"
    )
    log.info(
        "===================================="
    )

    if not BOT_TOKEN:

        log.info(
            "ERROR: BOT_TOKEN missing."
        )

        return

    if AI_API_KEY:

        log.info(
            f"Gemini enabled: {GEMINI_MODEL}"
        )

    else:

        log.info(
            "Gemini disabled - local mode."
        )

    history = load_history()

    log.info(
        f"History entries: {len(history)}"
    )

    candidates = collect_candidates(
        history,
        start_time
    )

    if not candidates:

        log.info(
            "No new candidates."
        )

        return

    candidates = candidates[:20]

    published_count = 0

    for news in candidates:

        if (
            published_count
            >= MAX_NEWS_PER_RUN
        ):
            break

        if deadline_reached(
            start_time
        ):
            break

        if process_news(
            news,
            history,
            start_time
        ):

            published_count += 1

        time.sleep(1)

    elapsed = (
        time.monotonic()
        - start_time
    )

    log.info("")
    log.info(
        "===================================="
    )
    log.info(
        f"FINISHED - Published: "
        f"{published_count}"
    )
    log.info(
        f"Runtime: {elapsed:.1f}s"
    )
    log.info(
        "===================================="
    )


# =========================================================
# START
# =========================================================

if __name__ == "__main__":
    main()
