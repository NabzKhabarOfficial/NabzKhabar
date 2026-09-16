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

CHANNEL = "@NabzKhabarOfficial"

MAX_NEWS_PER_RUN = int(
    os.getenv("MAX_NEWS_PER_RUN", "4")
)

RUN_DEADLINE_SECONDS = 180

MAX_ENTRIES_PER_FEED = 8

RSS_TIMEOUT = (5, 8)
ARTICLE_TIMEOUT = (5, 10)
TELEGRAM_TIMEOUT = (10, 20)

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
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/130 Safari/537.36"
    ),
    "Accept-Language": "fa,en;q=0.8",
})


# =========================================================
# TEXT HELPERS
# =========================================================

def clean_text(text):
    if not text:
        return ""

    text = BeautifulSoup(
        str(text),
        "html.parser"
    ).get_text(" ", strip=True)

    text = html.unescape(text)

    text = text.replace("\u200c", " ")
    text = text.replace("\u200f", "")
    text = text.replace("\u200e", "")

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
                line.strip()
                for line in f
                if line.strip()
            }

    except Exception as e:
        log.info(
            f"History load error: {e}"
        )

        return set()


def save_history(history):

    try:

        items = list(history)

        # حداکثر 500 شناسه
        if len(items) > 500:
            items = items[-500:]

        with open(
            HISTORY_FILE,
            "w",
            encoding="utf-8"
        ) as f:

            for item in items:
                f.write(
                    item + "\n"
                )

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
            f"{url} | {e}"
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


def collect_candidates(
    history,
    start_time
):

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
                    "timestamp":
                        get_entry_timestamp(
                            entry
                        ),
                })

    # خبرهای جدیدتر اول
    candidates.sort(
        key=lambda x: x.get(
            "timestamp",
            0
        ),
        reverse=True
    )

    log.info(
        f"Candidates found: "
        f"{len(candidates)}"
    )

    return candidates


# =========================================================
# UNWANTED ARTICLE CONTENT
# =========================================================

UNWANTED_PATTERNS = [
    "فهرست مطالب",
    "فهرست مطلب",
    "مطالب مرتبط",
    "مطالب پیشنهادی",
    "پیشنهاد سردبیر",
    "بیشتر بخوانید",
    "ادامه مطلب",
    "ادامه خبر",
    "اخبار مرتبط",
    "تبلیغات",
    "تبلیغ",
    "اسپانسر",
    "عضویت در خبرنامه",
    "خبرنامه",
    "اشتراک گذاری",
    "اشتراک‌گذاری",
    "کپی لینک",
    "کد خبر",
    "ارسال نظر",
    "نظرات کاربران",
    "دیدگاه",
    "منبع:",
    "منبع :",
    "منبع خبر:",
    "منبع خبر :",
    "پایان پیام",
]


def is_unwanted_text(text):

    normalized = normalize_title(
        text
    )

    if not normalized:
        return True

    # خیلی کوتاه
    if len(normalized) < 25:
        return True

    # الگوهای واضح منوی سایت/تبلیغات
    for pattern in UNWANTED_PATTERNS:

        if normalize_title(
            pattern
        ) in normalized:

            return True

    # متن‌هایی که فقط فهرست‌وار هستند
    if (
        normalized.count("?") >= 3
        and len(normalized) < 400
    ):
        return True

    return False


def clean_article_paragraphs(
    paragraphs
):

    cleaned = []

    seen = set()

    for paragraph in paragraphs:

        paragraph = clean_text(
            paragraph
        )

        if not paragraph:
            continue

        if is_unwanted_text(
            paragraph
        ):
            continue

        # حذف تکرار
        key = normalize_title(
            paragraph
        )

        if key in seen:
            continue

        seen.add(key)

        # حذف متن‌های خیلی کوتاه
        if len(paragraph) < 35:
            continue

        # حذف خطوطی که فقط عنوان/منو هستند
        if (
            len(paragraph.split())
            <= 5
        ):
            continue

        cleaned.append(
            paragraph
        )

    return cleaned


# =========================================================
# ARTICLE EXTRACTION
# =========================================================

def extract_media_from_soup(
    soup
):

    # -----------------------------------------
    # Video
    # -----------------------------------------

    for property_name in (
        "og:video",
        "og:video:url",
        "og:video:secure_url"
    ):

        video = soup.find(
            "meta",
            property=property_name
        )

        if (
            video
            and video.get("content")
        ):

            return {
                "type": "video",
                "url": video[
                    "content"
                ].strip()
            }

    video_tag = soup.find(
        "video"
    )

    if video_tag:

        source = video_tag.find(
            "source"
        )

        if (
            source
            and source.get("src")
        ):

            return {
                "type": "video",
                "url": source[
                    "src"
                ].strip()
            }

        if video_tag.get("src"):

            return {
                "type": "video",
                "url": video_tag[
                    "src"
                ].strip()
            }

    # -----------------------------------------
    # Image
    # -----------------------------------------

    og_image = soup.find(
        "meta",
        property="og:image"
    )

    if (
        og_image
        and og_image.get("content")
    ):

        return {
            "type": "image",
            "url": og_image[
                "content"
            ].strip()
        }

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
            "url": twitter_image[
                "content"
            ].strip()
        }

    return None


def extract_article_data(
    url
):

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

        media = extract_media_from_soup(
            soup
        )

        # -----------------------------------------
        # حذف عناصر غیرخبری
        # -----------------------------------------

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
            "iframe"
        ]):

            tag.decompose()

        # -----------------------------------------
        # استخراج پاراگراف‌های واقعی
        # -----------------------------------------

        paragraphs = []

        for p in soup.find_all("p"):

            text = clean_text(
                p.get_text(
                    " ",
                    strip=True
                )
            )

            if text:
                paragraphs.append(
                    text
                )

        paragraphs = clean_article_paragraphs(
            paragraphs
        )

        # -----------------------------------------
        # اولویت با article
        # -----------------------------------------

        article_paragraphs = []

        for selector in [
            "article",
            "[itemprop='articleBody']",
            ".article-body",
            ".article-content",
            ".news-content",
            ".news-detail",
        ]:

            try:

                containers = soup.select(
                    selector
                )

            except Exception:
                containers = []

            for container in containers:

                for p in container.find_all(
                    "p"
                ):

                    text = clean_text(
                        p.get_text(
                            " ",
                            strip=True
                        )
                    )

                    if text:
                        article_paragraphs.append(
                            text
                        )

        article_paragraphs = (
            clean_article_paragraphs(
                article_paragraphs
            )
        )

        # اگر article واقعی پیدا شد
        if len(article_paragraphs) >= 2:

            final_paragraphs = (
                article_paragraphs
            )

        else:

            final_paragraphs = paragraphs

        # حذف پاراگراف‌های مشابه
        unique = []
        seen = set()

        for paragraph in final_paragraphs:

            key = normalize_title(
                paragraph
            )

            if key in seen:
                continue

            seen.add(key)

            unique.append(
                paragraph
            )

        final_paragraphs = unique

        # -----------------------------------------
        # حداکثر 10 پاراگراف برای پردازش
        # -----------------------------------------

        final_paragraphs = (
            final_paragraphs[:10]
        )

        article_text = "\n\n".join(
            final_paragraphs
        )

        # حداکثر حجم
        article_text = article_text[
            :12000
        ]

        return {
            "text": article_text,
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

def extract_rss_media(
    entry
):

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
            ).lower()

            if "video" in mime:

                return {
                    "type": "video",
                    "url": url
                }

            if (
                "image" in mime
                or not mime
            ):

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
            ).lower()

            if "video" in mime:

                return {
                    "type": "video",
                    "url": url
                }

            return {
                "type": "image",
                "url": url
            }

    summary = (
        entry.get("summary")
        or entry.get("description")
        or ""
    )

    soup = BeautifulSoup(
        str(summary),
        "html.parser"
    )

    img = soup.find(
        "img"
    )

    if (
        img
        and img.get("src")
    ):

        return {
            "type": "image",
            "url": img[
                "src"
            ].strip()
        }

    return None


# =========================================================
# LOCAL NEWS ENGINE
# =========================================================

def split_sentences(text):

    if not text:
        return []

    text = text.replace(
        "\r",
        "\n"
    )

    # تبدیل فاصله قبل از علائم
    text = re.sub(
        r"\s+([،؛؟.!])",
        r"\1",
        text
    )

    parts = re.split(
        r"(?<=[.!؟])\s+|\n+",
        text
    )

    result = []

    for part in parts:

        part = clean_text(
            part
        )

        if not part:
            continue

        result.append(
            part
        )

    return result


def sentence_is_good(
    sentence,
    title=""
):

    sentence = clean_text(
        sentence
    )

    if len(sentence) < 45:
        return False

    if len(sentence) > 700:
        return False

    if is_unwanted_text(
        sentence
    ):
        return False

    title_norm = normalize_title(
        title
    )

    sentence_norm = normalize_title(
        sentence
    )

    # اگر کل جمله همان عنوان است
    if (
        title_norm
        and sentence_norm
        == title_norm
    ):
        return False

    # جمله‌های فهرست‌وار
    if (
        "فهرست مطالب" in sentence_norm
        or "مطالب مرتبط" in sentence_norm
    ):
        return False

    return True


def remove_duplicate_sentences(
    text
):

    sentences = split_sentences(
        text
    )

    result = []
    seen = set()

    for sentence in sentences:

        key = normalize_title(
            sentence
        )

        if not key:
            continue

        if key in seen:
            continue

        seen.add(key)

        result.append(
            sentence
        )

    return "\n\n".join(
        result
    )


def local_summarize(
    title,
    summary,
    article_text
):

    # اولویت با متن مقاله
    source = (
        article_text
        or summary
        or ""
    )

    source = remove_unwanted_content(
        source
    )

    if not source:
        return (
            clean_text(title),
            ""
        )

    sentences = split_sentences(
        source
    )

    good_sentences = []

    seen = set()

    for sentence in sentences:

        if not sentence_is_good(
            sentence,
            title
        ):
            continue

        key = normalize_title(
            sentence
        )

        if key in seen:
            continue

        seen.add(key)

        good_sentences.append(
            sentence
        )

    # -----------------------------------------
    # انتخاب حداکثر 5 جمله
    # -----------------------------------------

    selected = []

    total_length = 0

    for sentence in good_sentences:

        if len(selected) >= 5:
            break

        # سقف کلی
        if (
            total_length
            + len(sentence)
            > 1800
        ):
            break

        selected.append(
            sentence
        )

        total_length += len(
            sentence
        )

    # اگر متن خیلی کوتاه بود
    if not selected:

        return (
            clean_text(title),
            ""
        )

    body = "\n\n".join(
        selected
    )

    body = remove_duplicate_sentences(
        body
    )

    body = remove_unwanted_content(
        body
    )

    return (
        clean_text(title),
        body
    )


# =========================================================
# FINAL QUALITY CONTROL
# =========================================================

def quality_check(
    title,
    body
):

    title = clean_text(
        title
    )

    body = clean_text(
        body
    )

    if len(title) < 8:
        return False

    if len(body) < 80:
        return False

    normalized_body = normalize_title(
        body
    )

    # -----------------------------------------
    # جلوگیری از فهرست مطالب
    # -----------------------------------------

    forbidden = [
        "فهرست مطالب",
        "فهرست مطلب",
        "مطالب مرتبط",
        "ادامه مطلب",
        "تبلیغات",
        "خبرنامه",
        "کپی لینک",
        "ارسال نظر",
    ]

    for word in forbidden:

        if normalize_title(
            word
        ) in normalized_body:

            return False

    # -----------------------------------------
    # جلوگیری از متن خام خیلی طولانی
    # -----------------------------------------

    if len(body) > 2200:
        return False

    # -----------------------------------------
    # URL / username
    # -----------------------------------------

    if re.search(
        r"https?://|www\.",
        body,
        flags=re.I
    ):
        return False

    if re.search(
        r"@\w+",
        body
    ):
        return False

    # -----------------------------------------
    # بررسی تکرار جمله
    # -----------------------------------------

    sentences = split_sentences(
        body
    )

    normalized_sentences = [
        normalize_title(
            x
        )
        for x in sentences
    ]

    normalized_sentences = [
        x
        for x in normalized_sentences
        if x
    ]

    if (
        len(normalized_sentences)
        != len(
            set(normalized_sentences)
        )
    ):
        return False

    return True


def clean_title(
    title
):

    title = clean_text(
        title
    )

    # حذف تگ‌های رایج ابتدای عنوان
    title = re.sub(
        r"^(خبر فوری|فوری|اختصاصی)\s*[:：-]?\s*",
        "",
        title,
        flags=re.I
    )

    # حذف هشتگ
    title = re.sub(
        r"#\S+",
        "",
        title
    )

    # حذف URL
    title = re.sub(
        r"https?://\S+",
        "",
        title,
        flags=re.I
    )

    title = re.sub(
        r"\s+",
        " ",
        title
    )

    return title.strip()


def remove_unwanted_content(
    text
):

    if not text:
        return ""

    text = BeautifulSoup(
        str(text),
        "html.parser"
    ).get_text(
        " ",
        strip=True
    )

    text = html.unescape(
        text
    )

    text = text.replace(
        "\u200c",
        " "
    )

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
        r"#\S+",
        "",
        text
    )

    # حذف عبارات فهرست و تبلیغات
    for pattern in [
        r"فهرست مطالب.*?(?=چرا|بااینحال|با این حال|این فعالیت|بالا رفتن|$)",
        r"فهرست مطلب.*?(?=چرا|بااینحال|با این حال|این فعالیت|بالا رفتن|$)",
    ]:

        text = re.sub(
            pattern,
            "",
            text,
            flags=re.I
        )

    for pattern in [
        r"تبلیغات.*?(?=\n|$)",
        r"عضویت در خبرنامه.*?(?=\n|$)",
        r"مطالب مرتبط.*?(?=\n|$)",
        r"بیشتر بخوانید.*?(?=\n|$)",
        r"ادامه مطلب.*?(?=\n|$)",
        r"اشتراک.?گذاری.*?(?=\n|$)",
    ]:

        text = re.sub(
            pattern,
            "",
            text,
            flags=re.I
        )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# =========================================================
# IMAGE
# =========================================================

def download_image(
    url
):

    try:

        response = SESSION.get(
            url,
            timeout=ARTICLE_TIMEOUT
        )

        response.raise_for_status()

        content_type = response.headers.get(
            "Content-Type",
            ""
        ).lower()

        if (
            "image" not in content_type
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


def add_watermark(
    image
):

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

        tw = (
            bbox[2]
            - bbox[0]
        )

        th = (
            bbox[3]
            - bbox[1]
        )

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

    except Exception as e:

        log.info(
            f"Watermark error: {e}"
        )

        return image


def image_to_bytes(
    image
):

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

def telegram_url(
    method
):

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


def send_text(
    caption
):

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

    title = clean_title(
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
        return None

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

    # Telegram caption limit
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
            return None

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

        shortened = shortened.rstrip(
            " .،؛:!"
        )

        caption = (
            f"📰 <b>{title}</b>\n\n"
            f"{shortened}…\n\n"
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

    title = news[
        "title"
    ]

    category = news[
        "category"
    ]

    log.info(
        f"Processing: {title}"
    )

    # -----------------------------------------
    # Media from RSS
    # -----------------------------------------

    media = extract_rss_media(
        news["entry"]
    )

    article_text = clean_text(
        news["summary"]
    )

    # -----------------------------------------
    # Article page
    # -----------------------------------------

    # برای جلوگیری از متن‌های خام،
    # اگر خلاصه کوتاه است یا مشکوک به فهرست است،
    # صفحه اصلی خبر را می‌خوانیم.
    summary_norm = normalize_title(
        article_text
    )

    needs_article = (
        len(article_text) < 500
        or "فهرست مطالب" in summary_norm
        or "مطالب مرتبط" in summary_norm
        or not media
    )

    if needs_article:

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

    news[
        "article_text"
    ] = article_text

    news[
        "media"
    ] = media

    # -----------------------------------------
    # LOCAL AI-FREE PROCESSING
    # -----------------------------------------

    final_title, final_body = (
        local_summarize(
            title,
            news["summary"],
            article_text
        )
    )

    final_title = clean_title(
        final_title
    )

    final_body = remove_unwanted_content(
        final_body
    )

    final_body = remove_duplicate_sentences(
        final_body
    )

    # -----------------------------------------
    # Quality gate
    # -----------------------------------------

    if not quality_check(
        final_title,
        final_body
    ):

        log.info(
            "SKIPPED: "
            "quality check failed"
        )

        return False

    caption = make_caption(
        final_title,
        final_body
    )

    if not caption:

        log.info(
            "SKIPPED: "
            "caption generation failed"
        )

        return False

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

    # -----------------------------------------
    # Text fallback
    # -----------------------------------------

    if not published:

        log.info(
            "Media unavailable. "
            "Sending text post."
        )

        published = send_text(
            caption
        )

    # -----------------------------------------
    # History
    # -----------------------------------------

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
        "AI-FREE LOCAL NEWS ENGINE"
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

    # فقط 20 کاندید برای هر اجرا
    candidates = candidates[
        :20
    ]

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
