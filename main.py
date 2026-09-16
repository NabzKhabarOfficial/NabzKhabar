import os
import re
import html
import hashlib
import logging
import time
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import feedparser
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont


# =========================================================
# CONFIG
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
AI_API_KEY = os.getenv("AI_API_KEY")

CHANNEL = "@NabzKhabarOfficial"

MAX_NEWS_PER_RUN = int(os.getenv("MAX_NEWS_PER_RUN", "4"))

# حداکثر زمان اجرای یک نوبت
RUN_DEADLINE_SECONDS = 180

# حداکثر خبر بررسی‌شده از هر RSS
MAX_ENTRIES_PER_FEED = 8

RSS_TIMEOUT = (5, 8)
ARTICLE_TIMEOUT = (5, 10)
TELEGRAM_TIMEOUT = (10, 20)
AI_TIMEOUT = (8, 20)

HISTORY_FILE = "sent_news.txt"

FONT_BOLD = "Vazirmatn-Bold.ttf"
FONT_REGULAR = "Vazirmatn-Regular.ttf"


# =========================================================
# RSS SOURCES
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
    ("جامعه", "https://www.isna.ir/rss/service/society"),
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
        "AppleWebKit/537.36 Chrome/130 Safari/537.36"
    ),
    "Accept-Language": "fa,en;q=0.8",
})


# =========================================================
# HELPERS
# =========================================================

def clean_text(text):
    if not text:
        return ""

    text = BeautifulSoup(
        str(text),
        "html.parser"
    ).get_text(" ", strip=True)

    text = html.unescape(text)

    # حذف URL
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

    # حذف username
    text = re.sub(
        r"@\w+",
        "",
        text
    )

    # فاصله‌های اضافی
    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def normalize_title(title):
    title = clean_text(title).lower()

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
    base = normalize_title(title) + "|" + (link or "")

    return hashlib.sha256(
        base.encode("utf-8")
    ).hexdigest()


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
                line.strip()
                for line in f
                if line.strip()
            }

    except Exception:
        return set()


def save_history(history):
    try:
        # نگهداری حداکثر 500 شناسه
        items = list(history)[-500:]

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


def deadline_reached(start_time):
    return (
        time.monotonic() - start_time
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
            f"{url} | {e}"
        )

        return category, []


def collect_candidates(history, start_time):
    candidates = []
    seen_ids = set()

    log.info(
        "Collecting RSS feeds..."
    )

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

        for future in as_completed(
            futures
        ):

            if deadline_reached(
                start_time
            ):
                log.info(
                    "Deadline reached while collecting feeds."
                )
                break

            try:
                category, entries = (
                    future.result()
                )
            except Exception:
                continue

            for entry in entries:

                title = clean_text(
                    entry.get(
                        "title",
                        ""
                    )
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

                summary = clean_text(
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
                    "article_text": "",
                    "media": None,
                })

    log.info(
        f"Candidates found: {len(candidates)}"
    )

    return candidates


# =========================================================
# ARTICLE EXTRACTION
# =========================================================

def extract_media_from_soup(soup):

    # اول ویدئو را بررسی می‌کنیم
    og_video = soup.find(
        "meta",
        property="og:video"
    )

    if og_video and og_video.get("content"):

        return {
            "type": "video",
            "url": og_video["content"].strip()
        }

    # ویدئوی HTML
    video = soup.find("video")

    if video:

        source = video.find("source")

        if source and source.get("src"):

            return {
                "type": "video",
                "url": source["src"].strip()
            }

        if video.get("src"):

            return {
                "type": "video",
                "url": video["src"].strip()
            }

    # تصویر اصلی
    og_image = soup.find(
        "meta",
        property="og:image"
    )

    if og_image and og_image.get("content"):

        return {
            "type": "image",
            "url": og_image["content"].strip()
        }

    # twitter image
    twitter_image = soup.find(
        "meta",
        attrs={
            "name": "twitter:image"
        }
    )

    if (
        twitter_image
        and twitter_image.get("content")
    ):

        return {
            "type": "image",
            "url": twitter_image["content"].strip()
        }

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

        for tag in soup([
            "script",
            "style",
            "noscript",
            "nav",
            "footer",
            "header",
            "aside",
            "form"
        ]):
            tag.decompose()

        media = extract_media_from_soup(
            soup
        )

        containers = []

        selectors = [
            "article",
            "[itemprop='articleBody']",
            ".article-body",
            ".article-content",
            ".news-content",
            ".news-detail",
            ".content",
            "main",
        ]

        for selector in selectors:

            try:
                containers.extend(
                    soup.select(selector)
                )
            except Exception:
                pass

        best_text = ""

        for container in containers:

            text = clean_text(
                container.get_text(
                    " ",
                    strip=True
                )
            )

            if len(text) > len(best_text):
                best_text = text

        # fallback: paragraphs
        if len(best_text) < 300:

            paragraphs = soup.find_all(
                "p"
            )

            texts = []

            for p in paragraphs:

                text = clean_text(
                    p.get_text(
                        " ",
                        strip=True
                    )
                )

                if len(text) > 30:
                    texts.append(text)

            best_text = " ".join(
                texts
            )

        return {
            "text": best_text[:12000],
            "media": media
        }

    except Exception as e:

        log.info(
            f"Article fetch failed: "
            f"{url} | {e}"
        )

        return {
            "text": "",
            "media": None
        }


# =========================================================
# RSS MEDIA
# =========================================================

def extract_rss_media(entry):

    media_content = entry.get(
        "media_content"
    )

    if media_content:

        for media in media_content:

            url = media.get("url")

            if not url:
                continue

            mime = media.get(
                "type",
                ""
            )

            if "video" in mime:

                return {
                    "type": "video",
                    "url": url
                }

            return {
                "type": "image",
                "url": url
            }

    enclosures = entry.get(
        "enclosures"
    )

    if enclosures:

        for enclosure in enclosures:

            url = (
                enclosure.get("href")
                or enclosure.get("url")
            )

            if not url:
                continue

            mime = enclosure.get(
                "type",
                ""
            )

            if "video" in mime:

                return {
                    "type": "video",
                    "url": url
                }

            return {
                "type": "image",
                "url": url
            }

    # بعض RSSها تصویر را داخل HTML می‌گذارند
    summary = (
        entry.get("summary")
        or entry.get("description")
        or ""
    )

    soup = BeautifulSoup(
        str(summary),
        "html.parser"
    )

    img = soup.find("img")

    if img and img.get("src"):

        return {
            "type": "image",
            "url": img["src"].strip()
        }

    return None


# =========================================================
# GEMINI
# =========================================================

# اگر Gemini در این اجرا quota را رد کند،
# دیگر هیچ درخواست AI ارسال نمی‌شود.
gemini_disabled = False


def generate_news_text(
    title,
    text,
    category
):

    global gemini_disabled

    if not AI_API_KEY:
        return None

    if gemini_disabled:
        return None

    if not text:
        text = title

    prompt = f"""
تو ویراستار حرفه‌ای یک کانال خبری فارسی به نام «نبض خبر» هستی.

دسته‌بندی:
{category}

عنوان اولیه:
{title}

متن خبر:
{text}

خبر را برای انتشار در تلگرام بازنویسی کن.

قوانین:

1. هیچ واقعیت جدیدی اضافه نکن.
2. چیزی را حدس نزن.
3. لحن کاملاً خبری، حرفه‌ای و خنثی باشد.
4. اگر عنوان اولیه جهت‌دار یا احساسی است، آن را خنثی و خبری کن.
5. متن را واضح و روان بنویس.
6. اطلاعات مهم خبر حفظ شود.
7. از تکرار جمله‌ها جلوگیری کن.
8. متن در 2 تا 4 پاراگراف کوتاه باشد.
9. هیچ لینک، URL، @username یا هشتگ تولید نکن.
10. نام منبع را در متن ننویس.
11. از عبارت‌های تبلیغاتی استفاده نکن.
12. اطلاعات تأییدنشده را قطعی ننویس.

فقط با این قالب پاسخ بده:

TITLE:
عنوان حرفه‌ای خبر

BODY:
متن خبر در چند پاراگراف کوتاه
"""

    try:

        url = (
            "https://generativelanguage.googleapis.com/"
            "v1beta/models/gemini-3.6-flash:generateContent"
            f"?key={AI_API_KEY}"
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

        response = SESSION.post(
            url,
            json=payload,
            timeout=AI_TIMEOUT
        )

        if response.status_code != 200:

            log.info(
                f"Gemini error "
                f"{response.status_code}: "
                f"{response.text[:500]}"
            )

            # 429 = quota/rate limit
            # از اینجا به بعد در همین اجرا
            # دیگر AI را صدا نمی‌زنیم.
            if response.status_code in (
                400,
                401,
                403,
                404,
                429
            ):

                gemini_disabled = True

                if response.status_code == 429:
                    log.info(
                        "Gemini disabled for "
                        "the rest of this run "
                        "because quota/rate limit "
                        "was reached."
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

        output = "\n".join(
            part.get("text", "")
            for part in parts
        ).strip()

        return (
            output
            if output
            else None
        )

    except Exception as e:

        log.info(
            f"Gemini exception: {e}"
        )

        return None


# =========================================================
# TEXT CLEANING
# =========================================================

def normalize_sentence(text):

    text = clean_text(text)

    text = text.replace(
        "‌",
        ""
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def remove_duplicate_sentences(text):

    if not text:
        return ""

    text = text.replace(
        "\r",
        "\n"
    )

    # تبدیل فاصله‌های چندگانه
    text = re.sub(
        r"[ \t]+",
        " ",
        text
    )

    # جدا کردن پاراگراف‌ها
    raw_parts = re.split(
        r"\n+",
        text
    )

    paragraphs = []

    for part in raw_parts:

        part = normalize_sentence(
            part
        )

        if part:
            paragraphs.append(part)

    # حذف پاراگراف‌های دقیقاً تکراری
    unique_paragraphs = []
    seen_paragraphs = set()

    for paragraph in paragraphs:

        key = normalize_title(
            paragraph
        )

        if not key:
            continue

        if key in seen_paragraphs:
            continue

        seen_paragraphs.add(key)

        unique_paragraphs.append(
            paragraph
        )

    text = "\n\n".join(
        unique_paragraphs
    )

    # جدا کردن جمله‌ها
    sentences = re.split(
        r"(?<=[.!؟])\s+",
        text
    )

    cleaned = []
    seen_sentences = set()

    for sentence in sentences:

        sentence = normalize_sentence(
            sentence
        )

        if not sentence:
            continue

        key = normalize_title(
            sentence
        )

        if not key:
            continue

        if key in seen_sentences:
            continue

        seen_sentences.add(key)

        cleaned.append(sentence)

    return "\n\n".join(
        cleaned
    )


def remove_unwanted_content(text):

    if not text:
        return ""

    # URL
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

    # username
    text = re.sub(
        r"@\w+",
        "",
        text
    )

    # hashtagهای ورودی
    text = re.sub(
        r"#\S+",
        "",
        text
    )

    # کلمات رایج تبلیغاتی/منبعی در انتهای متن
    text = re.sub(
        r"(منبع|منبع خبر|ادامه خبر|جزئیات بیشتر)"
        r"\s*[:：-]?\s*$",
        "",
        text,
        flags=re.I
    )

    text = re.sub(
        r"[ \t]+",
        " ",
        text
    )

    text = re.sub(
        r"\n\s*\n\s*\n+",
        "\n\n",
        text
    )

    return text.strip()


def parse_ai_output(
    output,
    fallback_title
):

    if not output:
        return (
            fallback_title,
            ""
        )

    output = output.replace(
        "**",
        ""
    )

    # حذف code fence احتمالی
    output = re.sub(
        r"```.*?```",
        "",
        output,
        flags=re.S
    )

    title_match = re.search(
        r"TITLE\s*:\s*(.*?)(?:\n|BODY\s*:)",
        output,
        flags=re.I | re.S
    )

    body_match = re.search(
        r"BODY\s*:\s*(.*)",
        output,
        flags=re.I | re.S
    )

    if title_match:

        title = clean_text(
            title_match.group(1)
        )

    else:

        title = fallback_title

    if body_match:

        body = body_match.group(1)

    else:

        body = output

    body = remove_unwanted_content(
        body
    )

    body = remove_duplicate_sentences(
        body
    )

    return (
        title or fallback_title,
        body
    )


def fallback_news_text(
    title,
    summary,
    article_text
):

    source_text = (
        article_text
        or summary
        or ""
    )

    source_text = remove_unwanted_content(
        source_text
    )

    if not source_text:
        return (
            clean_text(title),
            ""
        )

    normalized_title = normalize_title(
        title
    )

    # حذف عنوانی که دوباره در متن آمده
    sentences = re.split(
        r"(?<=[.!؟])\s+",
        source_text
    )

    result = []

    seen = set()

    for sentence in sentences:

        sentence = normalize_sentence(
            sentence
        )

        if not sentence:
            continue

        normalized = normalize_title(
            sentence
        )

        if not normalized:
            continue

        # حذف جمله‌ای که دقیقاً عنوان است
        if normalized == normalized_title:
            continue

        # حذف جمله تکراری
        if normalized in seen:
            continue

        seen.add(normalized)

        result.append(sentence)

    body = "\n\n".join(
        result
    )

    body = remove_duplicate_sentences(
        body
    )

    body = remove_unwanted_content(
        body
    )

    # محدودیت مناسب برای تلگرام
    if len(body) > 2200:

        body = body[:2200]

        last_space = body.rfind(
            " "
        )

        if last_space > 1500:
            body = body[:last_space]

        body = body.rstrip(
            " .،؛:!"
        )

        body += "…"

    return (
        clean_text(title),
        body
    )


# =========================================================
# IMAGE
# =========================================================

def download_image(url):

    try:

        response = SESSION.get(
            url,
            timeout=ARTICLE_TIMEOUT,
            headers={
                "User-Agent":
                    SESSION.headers[
                        "User-Agent"
                    ]
            }
        )

        response.raise_for_status()

        content_type = response.headers.get(
            "Content-Type",
            ""
        )

        if (
            "image" not in
            content_type.lower()
        ):
            return None

        image = Image.open(
            BytesIO(
                response.content
            )
        ).convert("RGB")

        image.thumbnail(
            (1600, 1600)
        )

        return image

    except Exception as e:

        log.info(
            f"Image download failed: "
            f"{e}"
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

        # سایه
        draw.text(
            (
                x + 2,
                y + 2
            ),
            text,
            font=font,
            fill=(0, 0, 0)
        )

        # متن
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

    except Exception as e:

        log.info(
            f"Watermark error: {e}"
        )

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
# TELEGRAM
# =========================================================

def telegram_url(method):

    return (
        f"https://api.telegram.org/bot"
        f"{BOT_TOKEN}/{method}"
    )


def send_photo(
    image,
    caption
):

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
            "parse_mode": "HTML",
        }

        response = SESSION.post(
            telegram_url(
                "sendPhoto"
            ),
            data=data,
            files=files,
            timeout=TELEGRAM_TIMEOUT
        )

        if response.ok:
            return True

        log.info(
            "Telegram photo error: "
            + response.text[:500]
        )

    except Exception as e:

        log.info(
            f"Telegram photo exception: "
            f"{e}"
        )

    return False


def send_video(
    video_url,
    caption
):

    try:

        response = SESSION.get(
            video_url,
            timeout=ARTICLE_TIMEOUT,
            stream=True
        )

        response.raise_for_status()

        # جلوگیری از ویدئوهای بسیار بزرگ
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

                if size_mb > 45:

                    log.info(
                        f"Video skipped: "
                        f"{size_mb:.1f} MB"
                    )

                    return False

            except Exception:
                pass

        video_data = BytesIO(
            response.content
        )

        video_data.seek(0)

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
            "parse_mode": "HTML",
        }

        result = SESSION.post(
            telegram_url(
                "sendVideo"
            ),
            data=data,
            files=files,
            timeout=TELEGRAM_TIMEOUT
        )

        if result.ok:
            return True

        log.info(
            "Telegram video error: "
            + result.text[:500]
        )

    except Exception as e:

        log.info(
            f"Video error: {e}"
        )

    return False


def send_text(caption):

    try:

        data = {
            "chat_id": CHANNEL,
            "text": caption,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        response = SESSION.post(
            telegram_url(
                "sendMessage"
            ),
            data=data,
            timeout=TELEGRAM_TIMEOUT
        )

        if response.ok:
            return True

        log.info(
            "Telegram text error: "
            + response.text[:500]
        )

    except Exception as e:

        log.info(
            f"Telegram text exception: "
            f"{e}"
        )

    return False


# =========================================================
# CAPTION
# =========================================================

def make_caption(
    title,
    body
):

    title = remove_unwanted_content(
        title
    )

    body = remove_unwanted_content(
        body
    )

    title = title.strip()
    body = body.strip()

    if not title:
        title = "خبر جدید"

    if not body:
        body = (
            "جزئیات این خبر در حال تکمیل است."
        )

    # تمیز کردن HTML از متن ورودی
    title = html.escape(
        title
    )

    body = html.escape(
        body
    )

    caption = (
        f"📰 <b>{title}</b>\n\n"
        f"{body}\n\n"
        f"#نبض_خبر"
    )

    # محدودیت کپشن تلگرام
    if len(caption) > 1024:

        fixed = (
            f"📰 <b>{title}</b>\n\n"
            f"\n\n#نبض_خبر"
        )

        max_body = (
            1024
            - len(fixed)
            - 10
        )

        if max_body < 100:
            max_body = 100

        # برش روی فاصله
        shortened = body[
            :max_body
        ]

        last_space = shortened.rfind(
            " "
        )

        if last_space > 80:
            shortened = shortened[
                :last_space
            ]

        body = shortened.rstrip()

        caption = (
            f"📰 <b>{title}</b>\n\n"
            f"{body}…\n\n"
            f"#نبض_خبر"
        )

    return caption


# =========================================================
# PROCESS NEWS
# =========================================================

def process_news(
    news,
    history,
    start_time
):

    if deadline_reached(
        start_time
    ):
        return False

    title = news["title"]
    category = news["category"]

    log.info(
        f"Processing: {title}"
    )

    # -----------------------------------------
    # Media از RSS
    # -----------------------------------------

    media = extract_rss_media(
        news["entry"]
    )

    article_text = news["summary"]

    # -----------------------------------------
    # اگر مدیا یا متن کافی نداریم،
    # صفحه خبر را باز می‌کنیم.
    # -----------------------------------------

    if (
        not media
        or len(article_text) < 500
    ):

        data = extract_article_data(
            news["link"]
        )

        if data.get("text"):
            article_text = data[
                "text"
            ]

        if not media:
            media = data.get(
                "media"
            )

    news["article_text"] = (
        article_text
    )

    news["media"] = media

    # -----------------------------------------
    # Gemini
    # -----------------------------------------

    ai_output = generate_news_text(
        title,
        article_text,
        category
    )

    if ai_output:

        final_title, final_body = (
            parse_ai_output(
                ai_output,
                title
            )
        )

    else:

        final_title, final_body = (
            fallback_news_text(
                title,
                news["summary"],
                article_text
            )
        )

    # پاک‌سازی نهایی حتی بعد از AI
    final_title = remove_unwanted_content(
        final_title
    )

    final_body = remove_unwanted_content(
        final_body
    )

    final_body = remove_duplicate_sentences(
        final_body
    )

    if not final_title:
        final_title = clean_text(
            title
        )

    caption = make_caption(
        final_title,
        final_body
    )

    # -----------------------------------------
    # Publish
    # -----------------------------------------

    published = False

    if media:

        media_type = media.get(
            "type"
        )

        media_url = media.get(
            "url"
        )

        if (
            media_type == "video"
            and media_url
        ):

            log.info(
                f"Trying video: "
                f"{media_url}"
            )

            published = send_video(
                media_url,
                caption
            )

        elif (
            media_type == "image"
            and media_url
        ):

            log.info(
                f"Trying image: "
                f"{media_url}"
            )

            image = download_image(
                media_url
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

    # اگر عکس/ویدئو ارسال نشد
    # خبر متنی ارسال می‌شود.
    if not published:

        log.info(
            "Falling back to text post."
        )

        published = send_text(
            caption
        )

    if published:

        history.add(
            news["id"]
        )

        save_history(
            history
        )

        log.info(
            f"PUBLISHED: "
            f"{final_title}"
        )

        return True

    log.info(
        f"FAILED TO PUBLISH: "
        f"{title}"
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
        "NABZ KHABAR BOT STARTED"
    )
    log.info(
        "===================================="
    )

    if not BOT_TOKEN:

        log.info(
            "ERROR: BOT_TOKEN is missing."
        )

        return

    history = load_history()

    log.info(
        f"History entries: "
        f"{len(history)}"
    )

    candidates = collect_candidates(
        history,
        start_time
    )

    if not candidates:

        log.info(
            "No new candidates."
        )

        log.info(
            "FINISHED - Published: 0"
        )

        return

    # فقط تعداد محدودی خبر را پردازش می‌کنیم
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

            log.info(
                "Run deadline reached."
            )

            break

        success = process_news(
            news,
            history,
            start_time
        )

        if success:
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


if __name__ == "__main__":
    main()
