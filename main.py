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

MAX_NEWS_PER_RUN = int(os.getenv("MAX_NEWS_PER_RUN", "4"))
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
# TEXT CLEANING
# =========================================================

def normalize_spaces(text):
    if not text:
        return ""

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

    text = BeautifulSoup(
        str(text),
        "html.parser"
    ).get_text(
        " ",
        strip=True
    )

    text = normalize_spaces(text)

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
        f"Candidates found: "
        f"{len(candidates)}"
    )

    return candidates


# =========================================================
# BAD CONTENT FILTER
# =========================================================

BAD_PATTERNS = [
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
    "ارسال نظر",
    "نظرات کاربران",
    "دیدگاه",
    "پایان پیام",
    "خبرهای مرتبط",
    "اخبار پیشنهادی",
    "همچنین بخوانید",
    "پست های مرتبط",
    "پست‌های مرتبط",
]


def is_bad_paragraph(text):

    text = clean_text(text)

    if not text:
        return True

    normalized = normalize_title(text)

    if len(text) < 35:
        return True

    for pattern in BAD_PATTERNS:

        if normalize_title(
            pattern
        ) in normalized:

            return True

    if re.search(
        r"^(فهرست|مطالب مرتبط|تبلیغات|اشتراک)",
        normalized
    ):
        return True

    if normalized.count("?") >= 4:
        return True

    return False


def clean_paragraph_list(paragraphs):

    result = []
    seen = set()

    for paragraph in paragraphs:

        paragraph = clean_text(
            paragraph
        )

        if is_bad_paragraph(
            paragraph
        ):
            continue

        key = normalize_title(
            paragraph
        )

        if key in seen:
            continue

        seen.add(key)

        # پاراگراف‌های خیلی کوتاه معمولاً منوی سایت هستند
        if len(paragraph.split()) < 7:
            continue

        result.append(
            paragraph
        )

    return result


# =========================================================
# ARTICLE EXTRACTION
# =========================================================

def extract_media_from_soup(soup):

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

        media = extract_media_from_soup(
            soup
        )

        # حذف کامل عناصر غیرخبری
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

        # -----------------------------------------
        # اولویت با بدنه واقعی مقاله
        # -----------------------------------------

        containers = []

        selectors = [
            "article",
            "[itemprop='articleBody']",
            ".article-body",
            ".article-content",
            ".news-content",
            ".news-detail",
            ".content",
            ".post-content"
        ]

        for selector in selectors:

            try:

                found = soup.select(
                    selector
                )

                for container in found:
                    containers.append(
                        container
                    )

            except Exception:
                pass

        # -----------------------------------------
        # استخراج پاراگراف‌ها
        # -----------------------------------------

        article_paragraphs = []

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
            clean_paragraph_list(
                article_paragraphs
            )
        )

        # -----------------------------------------
        # اگر article خالی بود، از کل صفحه
        # پاراگراف‌های مناسب را پیدا کن
        # -----------------------------------------

        if len(article_paragraphs) < 2:

            article_paragraphs = []

            for p in soup.find_all(
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
                clean_paragraph_list(
                    article_paragraphs
                )
            )

        # -----------------------------------------
        # حذف پاراگراف‌های تکراری
        # -----------------------------------------

        final_paragraphs = []

        seen = set()

        for paragraph in article_paragraphs:

            key = normalize_title(
                paragraph
            )

            if key in seen:
                continue

            seen.add(key)

            final_paragraphs.append(
                paragraph
            )

        # حداکثر 12 پاراگراف
        final_paragraphs = (
            final_paragraphs[:12]
        )

        return {
            "text": "\n\n".join(
                final_paragraphs
            ),
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

            url = media.get(
                "url"
            )

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
# SENTENCE PROCESSING
# =========================================================

def split_sentences(text):

    if not text:
        return []

    text = text.replace(
        "\r",
        "\n"
    )

    # حفظ پایان جمله‌های فارسی و انگلیسی
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


def sentence_score(
    sentence,
    title,
    position
):

    score = 0

    normalized = normalize_title(
        sentence
    )

    # پاراگراف‌های خیلی کوتاه
    if len(sentence) < 50:
        score -= 3

    # جمله‌های بیش از حد طولانی
    if len(sentence) > 500:
        score -= 2

    # جمله‌هایی که اطلاعات خبری بیشتری دارند
    keywords = [
        "اعلام کرد",
        "گفت",
        "خبر داد",
        "تأکید کرد",
        "تاکید کرد",
        "افزود",
        "اظهار کرد",
        "عنوان کرد",
        "تصمیم",
        "تصمیم‌گیری",
        "منصوب",
        "آغاز",
        "برگزاری",
        "حادثه",
        "کشته",
        "مجروح",
        "زخمی",
        "بازداشت",
        "تولید",
        "افزایش",
        "کاهش",
        "رشد",
        "افت",
        "قیمت",
        "درصد",
        "میلیارد",
        "میلیون",
        "هزار",
        "امروز",
        "امشب",
        "فردا",
    ]

    for keyword in keywords:

        if normalize_title(
            keyword
        ) in normalized:

            score += 2

    # وجود عدد معمولاً نشان‌دهنده اطلاعات مشخص است
    if re.search(
        r"\d",
        sentence
    ):
        score += 1

    # جمله‌های اول مقاله معمولاً لید هستند
    if position == 0:
        score += 6

    elif position == 1:
        score += 4

    elif position == 2:
        score += 2

    # جلوگیری از تکرار عنوان
    if (
        normalize_title(title)
        == normalized
    ):
        score -= 10

    return score


def select_best_sentences(
    title,
    text,
    max_sentences=4,
    max_chars=1700
):

    sentences = split_sentences(
        text
    )

    candidates = []

    seen = set()

    for index, sentence in enumerate(
        sentences
    ):

        if is_bad_paragraph(
            sentence
        ):
            continue

        key = normalize_title(
            sentence
        )

        if not key:
            continue

        if key in seen:
            continue

        seen.add(key)

        score = sentence_score(
            sentence,
            title,
            index
        )

        candidates.append({
            "text": sentence,
            "score": score,
            "position": index
        })

    if not candidates:
        return []

    # جمله‌های با امتیاز بیشتر
    ranked = sorted(
        candidates,
        key=lambda x: (
            -x["score"],
            x["position"]
        )
    )

    selected = []

    total_chars = 0

    # ابتدا بهترین جمله‌ها
    for item in ranked:

        if len(selected) >= max_sentences:
            break

        sentence = item["text"]

        if (
            total_chars
            + len(sentence)
            > max_chars
        ):
            continue

        selected.append(
            item
        )

        total_chars += len(
            sentence
        )

    # برگرداندن ترتیب طبیعی خبر
    selected.sort(
        key=lambda x: x["position"]
    )

    return [
        item["text"]
        for item in selected
    ]


# =========================================================
# LOCAL NEWS WRITER
# =========================================================

def make_news_body(
    title,
    summary,
    article_text
):

    # اول متن مقاله
    source_text = (
        article_text
        if article_text
        else summary
    )

    if not source_text:
        return ""

    # حذف موارد مزاحم
    source_text = clean_text(
        source_text
    )

    # -----------------------------------------
    # انتخاب بهترین جملات
    # -----------------------------------------

    selected = select_best_sentences(
        title,
        source_text,
        max_sentences=4,
        max_chars=1700
    )

    if not selected:
        return ""

    # -----------------------------------------
    # ساخت پاراگراف خبری
    # -----------------------------------------

    paragraphs = []

    # لید
    if selected:

        lead = selected[0]

        paragraphs.append(
            lead
        )

    # ادامه خبر
    if len(selected) >= 2:

        second_block = (
            " ".join(
                selected[1:3]
            )
        )

        if len(second_block) >= 80:

            paragraphs.append(
                second_block
            )

    # جزئیات تکمیلی
    if len(selected) >= 4:

        extra = selected[3]

        if (
            normalize_title(extra)
            != normalize_title(
                paragraphs[-1]
            )
        ):

            paragraphs.append(
                extra
            )

    # -----------------------------------------
    # حذف تکرار
    # -----------------------------------------

    final = []

    seen = set()

    for paragraph in paragraphs:

        paragraph = clean_text(
            paragraph
        )

        key = normalize_title(
            paragraph
        )

        if not paragraph:
            continue

        if key in seen:
            continue

        seen.add(key)

        final.append(
            paragraph
        )

    return "\n\n".join(
        final
    )


# =========================================================
# TITLE CLEANING
# =========================================================

def clean_title(title):

    title = clean_text(
        title
    )

    # حذف برچسب‌های اضافی
    title = re.sub(
        r"^(خبر فوری|فوری|اختصاصی)\s*[:：-]?\s*",
        "",
        title,
        flags=re.I
    )

    title = re.sub(
        r"^\s*[\[\(（].*?[\]\)）]\s*",
        "",
        title
    )

    title = re.sub(
        r"#\S+",
        "",
        title
    )

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


# =========================================================
# QUALITY CONTROL
# =========================================================

def quality_check(
    title,
    body
):

    title = clean_title(
        title
    )

    body = clean_text(
        body
    )

    if len(title) < 8:
        return False

    if len(body) < 100:
        return False

    normalized_body = normalize_title(
        body
    )

    forbidden = [
        "فهرست مطالب",
        "فهرست مطلب",
        "مطالب مرتبط",
        "مطالب پیشنهادی",
        "تبلیغات",
        "خبرنامه",
        "کپی لینک",
        "ارسال نظر",
        "اشتراک گذاری",
        "بیشتر بخوانید",
    ]

    for word in forbidden:

        if normalize_title(
            word
        ) in normalized_body:

            return False

    if len(body) > 2100:
        return False

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

    # حداقل دو جمله
    sentences = split_sentences(
        body
    )

    if len(sentences) < 2:
        return False

    # جلوگیری از تکرار
    normalized_sentences = [
        normalize_title(
            x
        )
        for x in sentences
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

        content_type = response.headers.get(
            "Content-Type",
            ""
        ).lower()

        if "image" not in content_type:
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

    title = clean_title(
        title
    )

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

    # Telegram photo caption limit
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

    log.info(
        f"Processing: {title}"
    )

    media = extract_rss_media(
        news["entry"]
    )

    rss_summary = clean_text(
        news["summary"]
    )

    article_text = rss_summary

    summary_norm = normalize_title(
        rss_summary
    )

    # برای خبرهای مهم، صفحه اصلی خبر را هم بخوان
    needs_article = (
        len(rss_summary) < 700
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

    # ساخت متن خبری
    final_body = make_news_body(
        news["title"],
        rss_summary,
        article_text
    )

    final_title = clean_title(
        news["title"]
    )

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

        log.info(
            "SKIPPED: caption generation failed"
        )

        return False

    published = False

    # -----------------------------------------
    # VIDEO
    # -----------------------------------------

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

        # -------------------------------------
        # IMAGE
        # -------------------------------------

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
    # TEXT FALLBACK
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
    # SAVE HISTORY ONLY AFTER SUCCESS
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
        "AI-FREE LOCAL NEWS ENGINE v2"
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

    # فقط 20 کاندیدای جدید برای پردازش
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
