import os
import re
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
# WARNING CONTROL
# =========================================================

warnings.filterwarnings(
    "ignore",
    category=MarkupResemblesLocatorWarning
)


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
# HTTP SESSION
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
# TEXT NORMALIZATION
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


def collect_candidates(history, start_time):

    candidates = []
    seen_ids = set()

    log.info("Collecting RSS feeds...")

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

                title = clean_text(
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
        f"Candidates found: {len(candidates)}"
    )

    return candidates


# =========================================================
# SOURCE / BOILERPLATE CLEANING
# =========================================================

SOURCE_PATTERNS = [

    r"^به گزارش\s+",
    r"^به گزارش خبرنگار\s+",
    r"^به گزارش خبرگزاری\s+",
    r"^به نقل از\s+",
    r"^در گفت‌وگو با\s+",
    r"^در گفتگو با\s+",
    r"^به نقل از خبرگزاری\s+",
    r"^خبرگزاری\s+\S+\s*[-–—:]\s*",
    r"^خبرنگار\s+\S+\s*[-–—:]\s*",
    r"^ایرنا\s*[-–—:]\s*",
    r"^مهر\s*[-–—:]\s*",
]


def remove_source_phrase(text):

    if not text:
        return ""

    text = clean_text(text)

    for pattern in SOURCE_PATTERNS:

        text = re.sub(
            pattern,
            "",
            text,
            flags=re.I
        )

    return text.strip()


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
    "خبرهای مرتبط",
    "اخبار پیشنهادی",
    "همچنین بخوانید",

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

    "پست های مرتبط",
    "پست‌های مرتبط",

    "پایان پیام",

    "منبع:",
    "منبع خبر:",
]


def is_bad_paragraph(text):

    text = remove_source_phrase(text)

    if not text:
        return True

    normalized = normalize_title(text)

    if len(text) < 35:
        return True

    for pattern in BAD_PATTERNS:

        if normalize_title(pattern) in normalized:
            return True

    if re.search(
        r"^(فهرست|مطالب مرتبط|"
        r"تبلیغات|اشتراک|کپی لینک)",
        normalized
    ):
        return True

    if normalized.count("?") >= 4:
        return True

    return False


# =========================================================
# PARAGRAPH CLEANING
# =========================================================

def clean_paragraph_list(paragraphs):

    result = []
    seen = set()

    for paragraph in paragraphs:

        paragraph = remove_source_phrase(
            paragraph
        )

        if is_bad_paragraph(paragraph):
            continue

        key = normalize_title(paragraph)

        if key in seen:
            continue

        seen.add(key)

        if len(paragraph.split()) < 7:
            continue

        result.append(paragraph)

    return result


# =========================================================
# MEDIA EXTRACTION
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

        if video and video.get("content"):

            return {
                "type": "video",
                "url": video["content"].strip()
            }

    video_tag = soup.find("video")

    if video_tag:

        source = video_tag.find("source")

        if source and source.get("src"):

            return {
                "type": "video",
                "url": source["src"].strip()
            }

        if video_tag.get("src"):

            return {
                "type": "video",
                "url": video_tag["src"].strip()
            }

    og_image = soup.find(
        "meta",
        property="og:image"
    )

    if og_image and og_image.get("content"):

        return {
            "type": "image",
            "url": og_image["content"].strip()
        }

    twitter_image = soup.find(
        "meta",
        attrs={"name": "twitter:image"}
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


# =========================================================
# ARTICLE EXTRACTION
# =========================================================

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

        selectors = [

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
            ".news-body",

        ]

        for selector in selectors:

            try:

                found = soup.select(selector)

                for container in found:
                    containers.append(container)

            except Exception:
                pass

        article_paragraphs = []

        for container in containers:

            for p in container.find_all("p"):

                text = clean_text(
                    p.get_text(
                        " ",
                        strip=True
                    )
                )

                text = remove_source_phrase(
                    text
                )

                if text:
                    article_paragraphs.append(text)

        article_paragraphs = clean_paragraph_list(
            article_paragraphs
        )

        if len(article_paragraphs) < 2:

            article_paragraphs = []

            for p in soup.find_all("p"):

                text = clean_text(
                    p.get_text(
                        " ",
                        strip=True
                    )
                )

                text = remove_source_phrase(
                    text
                )

                if text:
                    article_paragraphs.append(text)

            article_paragraphs = clean_paragraph_list(
                article_paragraphs
            )

        final_paragraphs = []

        seen = set()

        for paragraph in article_paragraphs:

            key = normalize_title(paragraph)

            if key in seen:
                continue

            seen.add(key)

            final_paragraphs.append(paragraph)

        final_paragraphs = final_paragraphs[:15]

        return {
            "text": "\n\n".join(final_paragraphs),
            "media": media
        }

    except Exception as e:

        log.info(
            f"Article fetch failed: {url} | {e}"
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

    try:

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

    except Exception:
        pass

    return None


# =========================================================
# SENTENCE ENGINE
# =========================================================

def split_sentences(text):

    if not text:
        return []

    text = text.replace(
        "\r",
        "\n"
    )

    parts = re.split(
        r"(?<=[.!؟])\s+|\n+",
        text
    )

    result = []

    for part in parts:

        part = remove_source_phrase(part)

        if not part:
            continue

        result.append(part)

    return result


def sentence_key(text):

    text = normalize_title(text)

    # حذف برخی علائم برای مقایسه بهتر
    text = re.sub(
        r"[،؛:!؟.,]",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def word_set(text):

    return {
        w
        for w in sentence_key(text).split()
        if len(w) > 2
    }


def similarity(a, b):

    wa = word_set(a)
    wb = word_set(b)

    if not wa or not wb:
        return 0

    return (
        len(wa & wb)
        / max(
            1,
            len(wa | wb)
        )
    )


# =========================================================
# SENTENCE QUALITY
# =========================================================

def is_malformed_sentence(sentence):

    if not sentence:
        return True

    sentence = clean_text(sentence)

    if len(sentence) < 45:
        return True

    if len(sentence) > 700:
        return True

    normalized = normalize_title(sentence)

    # علائم واضح استخراج خراب
    if "همچنین بر" in normalized and "فرماندار" in normalized:
        if normalized.count("فرماندار") >= 2:
            return True

    if "همچنین" in normalized and normalized.count("همچنین") >= 3:
        return True

    if normalized.count("،") > 10:
        return True

    # چند تیتر/عبارت چسبیده
    if re.search(
        r"(فرماندار|رئیس|مدیر|وزیر).{0,30}"
        r"(همچنین|وی همچنین).{0,10}"
        r"(فرماندار|رئیس|مدیر|وزیر)",
        normalized
    ):
        return True

    # جمله‌هایی که ناگهان با یک عنوان جدید ادامه پیدا می‌کنند
    if re.search(
        r"\b(رئیس|فرماندار|وزیر|مدیرعامل)\s+\S+"
        r".{0,20}\b(همچنین|افزود|گفت)\b",
        normalized
    ) and len(sentence) > 500:

        return True

    return False


# =========================================================
# IMPORTANT SENTENCE SCORING
# =========================================================

IMPORTANT_WORDS = [

    "اعلام",
    "خبر",
    "گفت",
    "افزود",

    "تأکید",
    "تاکید",

    "اظهار",
    "عنوان",

    "بیان کرد",
    "اعلام کرد",

    "آغاز",
    "برگزار",
    "برگزاری",

    "تصمیم",
    "توافق",
    "مذاکره",

    "حادثه",
    "کشته",
    "مجروح",
    "زخمی",

    "بازداشت",

    "افزایش",
    "کاهش",
    "رشد",
    "افت",

    "قیمت",
    "تولید",

    "رقابت",
    "مسابقه",
    "دیدار",
    "سفر",

    "پرونده",
    "مختومه",
    "سازش",

    "جنگ",
    "درگیری",
    "حمله",

    "امکانات",
    "برنامه",
    "پروژه",
]


def score_sentence(sentence, index):

    score = 0

    normalized = normalize_title(sentence)

    if index == 0:
        score += 5

    elif index == 1:
        score += 3

    elif index == 2:
        score += 2

    for word in IMPORTANT_WORDS:

        if normalize_title(word) in normalized:
            score += 2

    # عدد معمولاً در خبرهای آماری مهم است
    if re.search(r"\d", sentence):
        score += 3

    # درصد
    if "%" in sentence or "درصد" in sentence:
        score += 2

    # طول مناسب
    words = len(sentence.split())

    if 12 <= words <= 45:
        score += 2

    # جملات بیش از حد طولانی جریمه شوند
    if words > 65:
        score -= 3

    return score


# =========================================================
# LOCAL NEWS WRITER v4
# =========================================================

def make_news_body(
    title,
    summary,
    article_text
):

    title = clean_title(title)

    source_text = (
        article_text
        if article_text
        else summary
    )

    source_text = clean_text(
        source_text
    )

    if not source_text:
        return ""

    paragraphs = []

    for raw_paragraph in re.split(
        r"\n{2,}",
        source_text
    ):

        raw_paragraph = remove_source_phrase(
            raw_paragraph
        )

        if is_bad_paragraph(
            raw_paragraph
        ):
            continue

        paragraphs.append(
            raw_paragraph
        )

    # اگر پاراگراف‌بندی خراب بود
    if len(paragraphs) < 2:

        paragraphs = split_sentences(
            source_text
        )

    sentences = []

    for paragraph in paragraphs:

        parts = split_sentences(
            paragraph
        )

        for sentence in parts:

            sentence = remove_source_phrase(
                sentence
            )

            if not sentence:
                continue

            if is_bad_paragraph(
                sentence
            ):
                continue

            if is_malformed_sentence(
                sentence
            ):
                continue

            sentences.append(
                sentence
            )

    # حذف تکرار
    unique_sentences = []

    for sentence in sentences:

        duplicate = False

        for previous in unique_sentences:

            if similarity(
                sentence,
                previous
            ) >= 0.72:

                duplicate = True
                break

        if not duplicate:

            unique_sentences.append(
                sentence
            )

    sentences = unique_sentences

    if not sentences:
        return ""

    # -----------------------------------------------------
    # اگر خبر خیلی کوتاه است
    # -----------------------------------------------------

    if len(sentences) <= 2:

        selected = sentences

    else:

        scored = []

        for index, sentence in enumerate(
            sentences
        ):

            scored.append({
                "sentence": sentence,
                "index": index,
                "score": score_sentence(
                    sentence,
                    index
                )
            })

        # لید را از سه جمله اول انتخاب کن
        lead_candidates = scored[:5]

        lead = max(
            lead_candidates,
            key=lambda x: x["score"]
        )

        selected = [
            lead["sentence"]
        ]

        total_length = len(
            lead["sentence"]
        )

        # برای حفظ ترتیب طبیعی خبر
        remaining = sorted(
            [
                item
                for item in scored
                if item["sentence"]
                != lead["sentence"]
            ],
            key=lambda x: x["index"]
        )

        for item in remaining:

            sentence = item["sentence"]

            if len(selected) >= 4:
                break

            if any(
                similarity(
                    sentence,
                    old
                ) >= 0.65
                for old in selected
            ):
                continue

            if (
                total_length
                + len(sentence)
                + 2
                > 1700
            ):
                continue

            selected.append(
                sentence
            )

            total_length += len(
                sentence
            )

    # -----------------------------------------------------
    # حذف جمله‌های خیلی کم‌ارزش
    # -----------------------------------------------------

    cleaned_selected = []

    for sentence in selected:

        sentence = clean_text(
            sentence
        )

        sentence = remove_source_phrase(
            sentence
        )

        if not sentence:
            continue

        if is_bad_paragraph(
            sentence
        ):
            continue

        cleaned_selected.append(
            sentence
        )

    selected = cleaned_selected

    if not selected:
        return ""

    # -----------------------------------------------------
    # ساخت پاراگراف‌ها
    # -----------------------------------------------------

    # خبرهای خیلی کوتاه
    if len(selected) == 1:

        return selected[0]

    # لید جدا + جزئیات
    lead = selected[0]

    details = []

    for sentence in selected[1:]:

        if similarity(
            lead,
            sentence
        ) >= 0.65:
            continue

        details.append(
            sentence
        )

    if not details:

        return lead

    return (
        lead
        + "\n\n"
        + " ".join(details)
    )


# =========================================================
# TITLE CLEANING
# =========================================================

def clean_title(title):

    title = clean_text(title)

    title = re.sub(
        r"^(خبر فوری|فوری|اختصاصی)"
        r"\s*[:：-]?\s*",
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

def quality_check(title, body):

    title = clean_title(title)

    body = body.strip()

    if len(title) < 8:
        return False

    if len(body) < 80:
        return False

    if len(body) > 1900:
        return False

    normalized_body = normalize_title(body)

    forbidden = [

        "فهرست مطالب",
        "فهرست مطلب",

        "مطالب مرتبط",
        "مطالب پیشنهادی",
        "پیشنهاد سردبیر",

        "تبلیغات",
        "تبلیغ",

        "خبرنامه",

        "کپی لینک",

        "ارسال نظر",

        "اشتراک گذاری",
        "اشتراک‌گذاری",

        "بیشتر بخوانید",

        "ادامه مطلب",
        "ادامه خبر",

        "اخبار مرتبط",

        "به گزارش خبرنگار",
        "به گزارش خبرگزاری",
        "به نقل از خبرگزاری",
        "به گزارش",
    ]

    for word in forbidden:

        if normalize_title(word) in normalized_body:

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

    sentences = split_sentences(body)

    if len(sentences) < 1:
        return False

    # جملات کاملاً تکراری
    normalized_sentences = [
        sentence_key(x)
        for x in sentences
        if sentence_key(x)
    ]

    if (
        len(normalized_sentences)
        != len(set(normalized_sentences))
    ):
        return False

    # اگر یک جمله به شکل غیرعادی طولانی باشد
    for sentence in sentences:

        if len(sentence) > 800:
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

        draw = ImageDraw.Draw(image)

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
            "parse_mode": "HTML",
        }

        response = SESSION.post(
            telegram_url("sendPhoto"),
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
            f"Telegram photo exception: {e}"
        )

    return False


def send_video(video_url, caption):

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
            telegram_url("sendVideo"),
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
            telegram_url("sendMessage"),
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
            f"Telegram text exception: {e}"
        )

    return False


# =========================================================
# CAPTION
# =========================================================

def make_caption(title, body):

    title = clean_title(title)

    body = body.strip()

    if not title:
        title = "خبر جدید"

    if not body:
        return None

    title = html.escape(title)
    body = html.escape(body)

    caption = (
        f"📰 <b>{title}</b>\n\n"
        f"{body}\n\n"
        f"#نبض_خبر"
    )

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

        shortened = body[:max_body]

        last_space = shortened.rfind(" ")

        if last_space > 80:
            shortened = shortened[:last_space]

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

def process_news(news, history, start_time):

    if deadline_reached(start_time):
        return False

    title = news["title"]

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

    needs_article = (
        len(rss_summary) < 900
        or "فهرست مطالب" in summary_norm
        or "مطالب مرتبط" in summary_norm
        or "بیشتر بخوانید" in summary_norm
        or len(rss_summary.split()) < 80
        or not media
    )

    if needs_article:

        data = extract_article_data(
            news["link"]
        )

        if data.get("text"):
            article_text = data["text"]

        if not media:
            media = data.get("media")

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

    # -----------------------------------------------------
    # VIDEO
    # -----------------------------------------------------

    if media:

        media_type = media.get("type")
        media_url = media.get("url")

        if (
            media_type == "video"
            and media_url
        ):

            log.info(
                f"Trying video: {media_url}"
            )

            published = send_video(
                media_url,
                caption
            )

        # -------------------------------------------------
        # IMAGE
        # -------------------------------------------------

        elif (
            media_type == "image"
            and media_url
        ):

            log.info(
                f"Trying image: {media_url}"
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

    # -----------------------------------------------------
    # TEXT FALLBACK
    # -----------------------------------------------------

    if not published:

        log.info(
            "Media unavailable. "
            "Sending text post."
        )

        published = send_text(
            caption
        )

    # -----------------------------------------------------
    # HISTORY
    # -----------------------------------------------------

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
        f"FAILED TO PUBLISH: {title}"
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
        "LOCAL NEWS ENGINE v4"
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

        log.info(
            "FINISHED - Published: 0"
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

        if deadline_reached(start_time):

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


# =========================================================
# START
# =========================================================

if __name__ == "__main__":
    main()
