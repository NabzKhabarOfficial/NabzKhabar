import os
import re
import io
import time
import html
import hashlib
import difflib
from urllib.parse import urljoin, urlparse

import requests
import feedparser
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont


# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
AI_API_KEY = os.getenv("AI_API_KEY", "").strip()

CHANNEL = "@NabzKhabarOfficial"

# Current stable Gemini model
GEMINI_MODEL = "gemini-3.6-flash"

MAX_NEWS_PER_RUN = int(os.getenv("MAX_NEWS_PER_RUN", "4"))

SENT_FILE = "sent_news.txt"

FONT_BOLD = "Vazirmatn-Bold.ttf"
FONT_REGULAR = "Vazirmatn-Regular.ttf"

REQUEST_TIMEOUT = 20
ARTICLE_TIMEOUT = 15

TELEGRAM_CAPTION_LIMIT = 1024

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    )
}


# ============================================================
# RSS SOURCES
# ============================================================

RSS_FEEDS = [
    # General
    ("ایران", "https://www.yjc.ir/fa/rss/allnews"),
    ("ایران", "https://www.irna.ir/rss"),
    ("ایران", "https://www.isna.ir/rss"),
    ("ایران", "https://www.mehrnews.com/rss"),

    # Technology
    ("فناوری", "https://www.zoomit.ir/feed/"),
    ("فناوری", "https://digiato.com/feed"),

    # Sports
    ("ورزش", "https://www.varzesh3.com/rss"),
    ("ورزش", "https://www.isna.ir/rss?serviceid=5"),

    # Economy
    ("اقتصاد", "https://www.irna.ir/rss/economy"),
    ("اقتصاد", "https://www.isna.ir/rss/service/economy"),

    # World
    ("جهان", "https://www.irna.ir/rss/service/world"),
    ("جهان", "https://www.isna.ir/rss/service/world"),

    # Culture / society
    ("فرهنگ", "https://www.irna.ir/rss/service/culture"),
    ("جامعه", "https://www.isna.ir/rss/service/society"),
]


# ============================================================
# PERSIAN TEXT NORMALIZATION
# ============================================================

ARABIC_TO_PERSIAN = str.maketrans({
    "ي": "ی",
    "ى": "ی",
    "ك": "ک",
    "ۀ": "ه",
    "ة": "ه",
    "ؤ": "و",
    "إ": "ا",
    "أ": "ا",
    "ٱ": "ا",
})

PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
ENGLISH_DIGITS = "0123456789"

DIGIT_TRANS = str.maketrans(
    PERSIAN_DIGITS + ARABIC_DIGITS,
    ENGLISH_DIGITS * 2
)


def normalize_text(text):
    if not text:
        return ""

    text = html.unescape(str(text))
    text = BeautifulSoup(text, "html.parser").get_text(" ")

    text = text.translate(ARABIC_TO_PERSIAN)
    text = text.translate(DIGIT_TRANS)

    # Remove zero-width characters
    text = re.sub(r"[\u200c\u200d\u200e\u200f\ufeff]", " ", text)

    # Remove channel handles
    text = re.sub(r"@\w+", " ", text)

    # Normalize punctuation spacing
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_for_compare(text):
    text = normalize_text(text).lower()

    text = re.sub(r"[^\w\s\u0600-\u06ff]", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ============================================================
# CLEANING / DUPLICATE TEXT
# ============================================================

CLUTTER_PATTERNS = [
    r"کپی لینک",
    r"copy link",
    r"انتهای پیام",
    r"بیشتر بخوانید",
    r"ادامه مطلب",
    r"منبع\s*:",
    r"source\s*:",
    r"ارسال نظر",
    r"نظرات",
    r"اخبار مرتبط",
    r"مطالب مرتبط",
    r"تبلیغات",
    r"اشتراک گذاری",
    r"اشتراک‌گذاری",
]


def remove_clutter(text):
    if not text:
        return ""

    text = html.unescape(text)

    for pattern in CLUTTER_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.I)

    # Remove Telegram/channel handles
    text = re.sub(r"@\w+", " ", text)

    # Remove raw URLs
    text = re.sub(r"https?://\S+", " ", text)

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def split_sentences(text):
    if not text:
        return []

    text = text.replace("\r", "\n")

    paragraphs = re.split(r"\n{2,}", text)

    output = []

    for paragraph in paragraphs:
        paragraph = paragraph.strip()

        if not paragraph:
            continue

        # Split long sentence chains while keeping Persian punctuation
        pieces = re.split(r"(?<=[.!؟])\s+", paragraph)

        for piece in pieces:
            piece = piece.strip()

            if len(piece) < 8:
                continue

            output.append(piece)

    return output


def similarity(a, b):
    a = normalize_for_compare(a)
    b = normalize_for_compare(b)

    if not a or not b:
        return 0.0

    return difflib.SequenceMatcher(None, a, b).ratio()


def meaningful_words(text):
    text = normalize_for_compare(text)

    words = text.split()

    # Ignore very short/common tokens
    stop = {
        "از", "به", "در", "با", "برای", "که", "این", "آن",
        "یک", "و", "یا", "اما", "را", "شد", "شود", "کرد",
        "کرده", "است", "هست", "بود", "می", "های", "ها",
        "روی", "تا", "بر", "نیز", "هم"
    }

    return {
        w for w in words
        if len(w) >= 3 and w not in stop
    }


def word_overlap(a, b):
    wa = meaningful_words(a)
    wb = meaningful_words(b)

    if not wa or not wb:
        return 0.0

    return len(wa & wb) / max(1, min(len(wa), len(wb)))


def title_similarity(title1, title2):
    s1 = similarity(title1, title2)
    s2 = word_overlap(title1, title2)

    return max(s1, s2)


def content_similarity(text1, text2):
    s1 = similarity(text1, text2)
    s2 = word_overlap(text1, text2)

    return max(s1, s2)


def is_same_story(item1, item2):
    title1 = item1.get("title", "")
    title2 = item2.get("title", "")

    body1 = item1.get("body", "")
    body2 = item2.get("body", "")

    ts = title_similarity(title1, title2)

    # Very similar titles = same story
    if ts >= 0.76:
        return True

    if body1 and body2:
        cs = content_similarity(body1, body2)

        # Similar title + similar body
        if ts >= 0.55 and cs >= 0.32:
            return True

        # Extremely similar bodies
        if cs >= 0.58:
            return True

    return False


def remove_duplicate_sentences(text):
    """
    Removes exact and near-duplicate sentences.
    This is the important fix for:
    
    sentence
    sentence
    """

    if not text:
        return ""

    text = text.replace("\r", "\n")

    # First preserve paragraphs
    paragraphs = re.split(r"\n+", text)

    clean_paragraphs = []
    seen = []

    for paragraph in paragraphs:
        paragraph = normalize_text(paragraph)

        if not paragraph:
            continue

        sentences = split_sentences(paragraph)

        if not sentences:
            continue

        paragraph_sentences = []

        for sentence in sentences:
            duplicate = False

            for old in seen:
                score = similarity(sentence, old)

                if score >= 0.88:
                    duplicate = True
                    break

            if not duplicate:
                paragraph_sentences.append(sentence)
                seen.append(sentence)

        if paragraph_sentences:
            clean_paragraphs.append(" ".join(paragraph_sentences))

    return "\n\n".join(clean_paragraphs).strip()


def clean_article_text(text):
    if not text:
        return ""

    text = remove_clutter(text)

    # Remove accidental repeated lines
    text = remove_duplicate_sentences(text)

    # Final whitespace cleanup
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)

    return text.strip()


# ============================================================
# HEADLINE CLEANING
# ============================================================

FRAMING_REPLACEMENTS = [
    # Keep the bot neutral instead of importing source commentary.
    (r"اقدام خصمانه علیه", "اقدام جدید علیه"),
    (r"اقدام خصمانه", "اقدام جدید"),
    (r"بهانه(?:‌| )ای واهی", "دلیلی که مقام‌های آن کشور اعلام کرده‌اند"),
    (r"بهانه واهی", "دلیلی که مقام‌های آن کشور اعلام کرده‌اند"),
]


def clean_headline(title):
    title = normalize_text(title)

    # Remove site prefixes
    title = re.sub(
        r"^(خبر فوری|فوری|اختصاصی|مهم)\s*[:：\-–]\s*",
        "",
        title,
        flags=re.I
    )

    # Remove duplicated title separators
    title = re.sub(r"\s*[\|\-–—]\s*[^|]{0,40}$", "", title)

    # Neutralize obvious editorial framing
    for pattern, replacement in FRAMING_REPLACEMENTS:
        title = re.sub(pattern, replacement, title, flags=re.I)

    title = re.sub(r"\s+", " ", title).strip()

    return title


# ============================================================
# CATEGORY
# ============================================================

def normalize_category(category):
    category = normalize_text(category).lower()

    mapping = {
        "فناوری": "فناوری",
        "tech": "فناوری",
        "technology": "فناوری",
        "ورزش": "ورزش",
        "sport": "ورزش",
        "sports": "ورزش",
        "اقتصاد": "اقتصاد",
        "economy": "اقتصاد",
        "جهان": "جهان",
        "world": "جهان",
        "ایران": "ایران",
        "iran": "ایران",
        "جامعه": "جامعه",
        "فرهنگ": "فرهنگ",
        "science": "علم و فناوری",
        "علم": "علم و فناوری",
    }

    return mapping.get(category, "عمومی")


# ============================================================
# SENT HISTORY
# ============================================================

def load_sent_news():
    if not os.path.exists(SENT_FILE):
        return set()

    try:
        with open(SENT_FILE, "r", encoding="utf-8") as f:
            return {
                line.strip()
                for line in f
                if line.strip()
            }
    except Exception:
        return set()


def save_sent_news(sent):
    # Keep history bounded
    values = list(sent)[-500:]

    with open(SENT_FILE, "w", encoding="utf-8") as f:
        for value in values:
            f.write(value + "\n")


def news_id(link, title):
    raw = f"{link}|{normalize_for_compare(title)}"

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


# ============================================================
# RSS
# ============================================================

def fetch_feed(category, url):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT
        )

        response.raise_for_status()

        parsed = feedparser.parse(response.content)

        return category, parsed.entries

    except Exception as e:
        print(f"RSS ERROR [{category}] {url}: {e}")
        return category, []


# ============================================================
# ARTICLE PAGE EXTRACTION
# ============================================================

ARTICLE_SELECTORS = [
    "article",
    "[itemprop='articleBody']",
    ".article-body",
    ".article__body",
    ".article-content",
    ".article-body-content",
    ".post-content",
    ".entry-content",
    ".news-content",
    ".news-body",
    ".content",
    "main",
]


def extract_article_text(url):
    if not url:
        return ""

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=ARTICLE_TIMEOUT
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.content,
            "html.parser"
        )

        # Remove obvious non-article elements
        for tag in soup([
            "script",
            "style",
            "noscript",
            "nav",
            "footer",
            "header",
            "aside",
            "form",
            "iframe",
            "svg",
            "button",
        ]):
            tag.decompose()

        best_text = ""

        for selector in ARTICLE_SELECTORS:
            element = soup.select_one(selector)

            if not element:
                continue

            text = element.get_text(
                "\n",
                strip=True
            )

            text = clean_article_text(text)

            if len(text) > len(best_text):
                best_text = text

        if not best_text:
            best_text = clean_article_text(
                soup.get_text("\n", strip=True)
            )

        # Remove common repeated lead/body structures
        best_text = remove_duplicate_sentences(best_text)

        # Don't let a massive webpage enter Gemini
        return best_text[:12000]

    except Exception as e:
        print(f"ARTICLE ERROR {url}: {e}")
        return ""


# ============================================================
# MEDIA EXTRACTION
# ============================================================

def absolute_url(base, value):
    if not value:
        return ""

    return urljoin(base, value.strip())


def is_direct_video(url):
    if not url:
        return False

    path = urlparse(url).path.lower()

    return path.endswith((
        ".mp4",
        ".mov",
        ".m4v",
        ".webm",
        ".avi"
    ))


def extract_media(entry, article_url):
    image_url = ""
    video_url = ""

    # RSS enclosures
    for enclosure in entry.get("enclosures", []):
        href = enclosure.get("href") or enclosure.get("url") or ""
        media_type = (
            enclosure.get("type") or ""
        ).lower()

        href = absolute_url(article_url, href)

        if "video" in media_type or is_direct_video(href):
            video_url = href
        elif "image" in media_type:
            image_url = href

    # media_content
    media_content = entry.get("media_content", [])

    for media in media_content:
        href = media.get("url", "")
        media_type = (
            media.get("type") or ""
        ).lower()

        href = absolute_url(article_url, href)

        if "video" in media_type or is_direct_video(href):
            video_url = video_url or href
        elif "image" in media_type:
            image_url = image_url or href

    # If RSS didn't contain media, inspect article
    if not image_url and not video_url:
        try:
            response = requests.get(
                article_url,
                headers=HEADERS,
                timeout=ARTICLE_TIMEOUT
            )

            soup = BeautifulSoup(
                response.content,
                "html.parser"
            )

            # Video tags
            for video in soup.find_all("video"):
                src = (
                    video.get("src")
                    or video.get("data-src")
                    or ""
                )

                src = absolute_url(article_url, src)

                if is_direct_video(src):
                    video_url = src
                    break

                source = video.find("source")

                if source:
                    src = (
                        source.get("src")
                        or source.get("data-src")
                        or ""
                    )

                    src = absolute_url(
                        article_url,
                        src
                    )

                    if is_direct_video(src):
                        video_url = src
                        break

            # Generic direct video links
            if not video_url:
                for link in soup.find_all("a", href=True):
                    href = absolute_url(
                        article_url,
                        link.get("href")
                    )

                    if is_direct_video(href):
                        video_url = href
                        break

            # OpenGraph video
            if not video_url:
                for prop in [
                    "og:video",
                    "og:video:url",
                    "og:video:secure_url",
                ]:
                    tag = soup.find(
                        "meta",
                        property=prop
                    )

                    if tag and tag.get("content"):
                        candidate = absolute_url(
                            article_url,
                            tag.get("content")
                        )

                        if is_direct_video(candidate):
                            video_url = candidate
                            break

            # OpenGraph image
            if not image_url:
                for prop in [
                    "og:image",
                    "twitter:image",
                ]:
                    tag = soup.find(
                        "meta",
                        property=prop
                    )

                    if tag and tag.get("content"):
                        image_url = absolute_url(
                            article_url,
                            tag.get("content")
                        )
                        break

        except Exception as e:
            print(f"MEDIA PAGE ERROR {article_url}: {e}")

    return {
        "image": image_url,
        "video": video_url,
    }


# ============================================================
# GEMINI
# ============================================================

def gemini_generate(title, body, category):
    if not AI_API_KEY:
        print("Gemini skipped: AI_API_KEY missing")
        return ""

    prompt = f"""
تو ویراستار حرفه‌ای کانال خبری «نبض خبر» هستی.

خبر زیر را برای انتشار در تلگرام بازنویسی کن.

دسته:
{category}

عنوان اولیه:
{title}

متن خبر:
{body}

قوانین بسیار مهم:

1. فقط اطلاعات موجود در متن را استفاده کن.
2. هیچ واقعیت جدیدی اختراع نکن.
3. متن را فارسی روان و حرفه‌ای بنویس.
4. لحن خبری، دقیق و بی‌طرف باشد.
5. عنوان را کوتاه، جذاب و factual کن.
6. اگر عنوان یا متن دارای قضاوت، تبلیغ، توهین یا عبارت احساسی از طرف منبع است،
   آن را تا حد ممکن به بیان خنثی و خبری تبدیل کن.
7. یک جمله یا پاراگراف را هرگز دوبار تکرار نکن.
8. اگر خلاصه خبر و متن اصلی یک مطلب را تکرار می‌کنند، فقط یک بار آن را نگه دار.
9. خروجی باید برای خواندن مستقیم در تلگرام مناسب باشد.
10. لینک، URL، نام سایت، نام منبع، @username و هشتگ تولید نکن.
11. از عبارت‌هایی مثل «منبع»، «ادامه مطلب»، «کپی لینک» استفاده نکن.
12. متن را در 2 تا 4 پاراگراف کوتاه تنظیم کن.
13. عنوان را فقط در خط اول با این فرمت بده:

TITLE: عنوان خبر

بعد از آن:

BODY:
متن خبر

هیچ متن دیگری خارج از TITLE و BODY ننویس.
"""

    url = (
        "https://generativelanguage.googleapis.com/"
        "v1beta/models/"
        f"{GEMINI_MODEL}:generateContent"
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
        response = requests.post(
            url,
            params={"key": AI_API_KEY},
            json=payload,
            headers={
                "Content-Type": "application/json"
            },
            timeout=45
        )

        if response.status_code != 200:
            print(
                "Gemini error",
                response.status_code,
                response.text[:500]
            )
            return ""

        data = response.json()

        candidates = data.get(
            "candidates",
            []
        )

        if not candidates:
            return ""

        parts = (
            candidates[0]
            .get("content", {})
            .get("parts", [])
        )

        text = ""

        for part in parts:
            text += part.get("text", "")

        return clean_ai_output(text)

    except Exception as e:
        print(f"Gemini exception: {e}")
        return ""


def clean_ai_output(text):
    if not text:
        return ""

    text = text.strip()

    # Remove markdown fences
    text = re.sub(
        r"```(?:text|markdown)?",
        "",
        text,
        flags=re.I
    )

    text = text.replace("```", "")

    # Extract TITLE/BODY
    title_match = re.search(
        r"TITLE\s*:\s*(.+?)(?:\n|$)",
        text,
        flags=re.I
    )

    body_match = re.search(
        r"BODY\s*:\s*(.*)",
        text,
        flags=re.I | re.S
    )

    if title_match and body_match:
        title = clean_headline(
            title_match.group(1)
        )

        body = clean_article_text(
            body_match.group(1)
        )

        body = remove_duplicate_sentences(body)

        if title and body:
            return (
                f"TITLE: {title}\n"
                f"BODY: {body}"
            )

    # Fallback if AI didn't follow exact structure
    return remove_duplicate_sentences(
        normalize_text(text)
    )


# ============================================================
# FALLBACK EDITOR
# ============================================================

def make_fallback_body(title, body):
    """
    Used when Gemini is unavailable.
    Important: the bot must still produce a clean post.
    """

    body = clean_article_text(body)

    if not body:
        return ""

    sentences = split_sentences(body)

    if not sentences:
        return body[:1800]

    clean = []

    for sentence in sentences:
        if len(sentence) < 10:
            continue

        if any(
            similarity(sentence, old) >= 0.88
            for old in clean
        ):
            continue

        clean.append(sentence)

    # Keep a reasonable Telegram length
    result = " ".join(clean)

    return result[:5000].strip()


def parse_ai_result(ai_text, original_title, original_body):
    if not ai_text:
        return (
            clean_headline(original_title),
            make_fallback_body(
                original_title,
                original_body
            )
        )

    title_match = re.search(
        r"TITLE\s*:\s*(.+?)(?:\n|$)",
        ai_text,
        flags=re.I
    )

    body_match = re.search(
        r"BODY\s*:\s*(.*)",
        ai_text,
        flags=re.I | re.S
    )

    if title_match:
        title = clean_headline(
            title_match.group(1)
        )
    else:
        title = clean_headline(
            original_title
        )

    if body_match:
        body = body_match.group(1)
    else:
        body = ai_text

    body = clean_article_text(body)

    # Critical final duplicate protection
    body = remove_duplicate_sentences(body)

    if not body:
        body = make_fallback_body(
            original_title,
            original_body
        )

    return title, body


# ============================================================
# CAPTION
# ============================================================

def make_caption(title, body):
    title = clean_headline(title)

    body = clean_article_text(body)
    body = remove_duplicate_sentences(body)

    # Remove accidental hashtags/handles from body
    body = re.sub(
        r"#[\w\u0600-\u06ff_]+",
        "",
        body
    )

    body = re.sub(
        r"@\w+",
        "",
        body
    )

    body = re.sub(
        r"https?://\S+",
        "",
        body
    )

    body = re.sub(
        r"\n{3,}",
        "\n\n",
        body
    ).strip()

    # Fixed professional format
    caption = (
        f"📰 <b>{html.escape(title)}</b>\n\n"
        f"{html.escape(body)}\n\n"
        f"#نبض_خبر"
    )

    # Telegram media caption limit
    if len(caption) <= TELEGRAM_CAPTION_LIMIT:
        return caption

    # Intelligent truncation
    suffix = "\n\n#نبض_خبر"

    allowed = (
        TELEGRAM_CAPTION_LIMIT
        - len(
            f"📰 <b>{html.escape(title)}</b>\n\n"
            + suffix
        )
        - 10
    )

    short_body = body[:allowed].strip()

    # Don't cut in the middle of a word
    if " " in short_body:
        short_body = short_body.rsplit(" ", 1)[0]

    return (
        f"📰 <b>{html.escape(title)}</b>\n\n"
        f"{html.escape(short_body)}…"
        f"{suffix}"
    )


# ============================================================
# WATERMARK
# ============================================================

def get_font(path, size):
    try:
        return ImageFont.truetype(
            path,
            size
        )
    except Exception:
        return ImageFont.load_default()


def add_watermark(image_bytes):
    try:
        image = Image.open(
            io.BytesIO(image_bytes)
        ).convert("RGBA")

        width, height = image.size

        overlay = Image.new(
            "RGBA",
            image.size,
            (0, 0, 0, 0)
        )

        draw = ImageDraw.Draw(
            overlay
        )

        font_size = max(
            22,
            int(width * 0.035)
        )

        font = get_font(
            FONT_BOLD,
            font_size
        )

        text = "نبض خبر | NABZ"

        bbox = draw.textbbox(
            (0, 0),
            text,
            font=font
        )

        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        margin = max(
            15,
            int(width * 0.02)
        )

        x = width - text_w - margin
        y = height - text_h - margin

        padding = 10

        draw.rounded_rectangle(
            [
                x - padding,
                y - padding,
                x + text_w + padding,
                y + text_h + padding,
            ],
            radius=10,
            fill=(0, 0, 0, 150)
        )

        draw.text(
            (x, y),
            text,
            font=font,
            fill=(255, 255, 255, 235)
        )

        result = Image.alpha_composite(
            image,
            overlay
        )

        output = io.BytesIO()

        # Telegram-friendly format
        result.convert("RGB").save(
            output,
            format="JPEG",
            quality=92,
            optimize=True
        )

        output.seek(0)

        return output

    except Exception as e:
        print(f"WATERMARK ERROR: {e}")
        return io.BytesIO(image_bytes)


# ============================================================
# MEDIA DOWNLOAD
# ============================================================

def download_bytes(url, timeout=30):
    if not url:
        return None

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=timeout
        )

        response.raise_for_status()

        return response.content

    except Exception as e:
        print(f"DOWNLOAD ERROR {url}: {e}")
        return None


# ============================================================
# TELEGRAM
# ============================================================

def telegram_request(method, files=None, data=None):
    url = (
        f"https://api.telegram.org/bot"
        f"{BOT_TOKEN}/{method}"
    )

    try:
        response = requests.post(
            url,
            data=data,
            files=files,
            timeout=45
        )

        if not response.ok:
            print(
                f"Telegram {method} ERROR:",
                response.status_code,
                response.text[:500]
            )

            return None

        return response.json()

    except Exception as e:
        print(
            f"Telegram {method} EXCEPTION:",
            e
        )

        return None


def send_photo(image_bytes, caption):
    files = {
        "photo": (
            "nabz.jpg",
            image_bytes,
            "image/jpeg"
        )
    }

    data = {
        "chat_id": CHANNEL,
        "caption": caption,
        "parse_mode": "HTML",
    }

    return telegram_request(
        "sendPhoto",
        files=files,
        data=data
    )


def send_video(video_bytes, caption):
    files = {
        "video": (
            "nabz.mp4",
            video_bytes,
            "video/mp4"
        )
    }

    data = {
        "chat_id": CHANNEL,
        "caption": caption,
        "parse_mode": "HTML",
        "supports_streaming": "true",
    }

    return telegram_request(
        "sendVideo",
        files=files,
        data=data
    )


def send_text(caption):
    data = {
        "chat_id": CHANNEL,
        "text": caption,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }

    return telegram_request(
        "sendMessage",
        data=data
    )


# ============================================================
# CANDIDATES
# ============================================================

def get_entry_summary(entry):
    summary = (
        entry.get("summary")
        or entry.get("description")
        or ""
    )

    return clean_article_text(summary)


def collect_candidates(sent):
    candidates = []

    seen_ids = set()

    for category, feed_url in RSS_FEEDS:

        category, entries = fetch_feed(
            category,
            feed_url
        )

        print(
            f"Feed {category}: "
            f"{len(entries)} entries"
        )

        for entry in entries:

            title = normalize_text(
                entry.get("title", "")
            )

            link = (
                entry.get("link")
                or ""
            ).strip()

            if not title or not link:
                continue

            nid = news_id(
                link,
                title
            )

            # Already sent
            if nid in sent:
                continue

            # Duplicate inside current run
            if nid in seen_ids:
                continue

            # Article text
            rss_body = get_entry_summary(
                entry
            )

            article_body = extract_article_text(
                link
            )

            # Prefer actual article when meaningful
            if (
                len(article_body)
                >= max(250, len(rss_body) * 1.15)
            ):
                body = article_body
            else:
                body = rss_body

            body = clean_article_text(body)

            if len(body) < 40:
                body = clean_article_text(
                    article_body or rss_body
                )

            if len(body) < 40:
                continue

            candidate = {
                "id": nid,
                "title": clean_headline(title),
                "body": body,
                "link": link,
                "category": normalize_category(
                    category
                ),
            }

            # Compare with candidates already collected
            duplicate = False

            for previous in candidates:
                if is_same_story(
                    candidate,
                    previous
                ):
                    duplicate = True
                    break

            if duplicate:
                continue

            media = extract_media(
                entry,
                link
            )

            candidate["image"] = media["image"]
            candidate["video"] = media["video"]

            # We want visual news
            if not candidate["image"] and not candidate["video"]:
                continue

            candidates.append(candidate)
            seen_ids.add(nid)

    print(
        f"Candidates found: {len(candidates)}"
    )

    return candidates


# ============================================================
# PUBLISH ONE NEWS
# ============================================================

def publish_news(item):
    title = item["title"]
    body = item["body"]
    category = item["category"]

    print(
        f"Preparing: {title}"
    )

    # AI rewriting
    ai_result = gemini_generate(
        title,
        body,
        category
    )

    final_title, final_body = parse_ai_result(
        ai_result,
        title,
        body
    )

    # Final safety cleaning
    final_title = clean_headline(
        final_title
    )

    final_body = clean_article_text(
        final_body
    )

    final_body = remove_duplicate_sentences(
        final_body
    )

    caption = make_caption(
        final_title,
        final_body
    )

    # --------------------------------------------------------
    # VIDEO FIRST
    # --------------------------------------------------------

    if item.get("video"):
        print(
            f"Downloading video: "
            f"{item['video']}"
        )

        video = download_bytes(
            item["video"],
            timeout=45
        )

        if video:
            result = send_video(
                video,
                caption
            )

            if result and result.get("ok"):
                print(
                    f"VIDEO PUBLISHED: "
                    f"{final_title}"
                )

                return True

    # --------------------------------------------------------
    # IMAGE
    # --------------------------------------------------------

    if item.get("image"):
        print(
            f"Downloading image: "
            f"{item['image']}"
        )

        image = download_bytes(
            item["image"],
            timeout=30
        )

        if image:
            watermarked = add_watermark(
                image
            )

            result = send_photo(
                watermarked,
                caption
            )

            if result and result.get("ok"):
                print(
                    f"PHOTO PUBLISHED: "
                    f"{final_title}"
                )

                return True

    # --------------------------------------------------------
    # TEXT FALLBACK
    # --------------------------------------------------------

    print(
        "No usable media. "
        "Sending text fallback."
    )

    result = send_text(
        caption
    )

    if result and result.get("ok"):
        print(
            f"TEXT PUBLISHED: "
            f"{final_title}"
        )

        return True

    return False


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 60)
    print("NABZ KHABAR BOT STARTED")
    print("=" * 60)

    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN is missing.")
        return

    sent = load_sent_news()

    print(
        f"History entries: {len(sent)}"
    )

    candidates = collect_candidates(
        sent
    )

    published = 0

    for item in candidates:

        if published >= MAX_NEWS_PER_RUN:
            break

        # Extra protection against same story
        if item["id"] in sent:
            continue

        success = publish_news(
            item
        )

        if success:
            sent.add(
                item["id"]
            )

            save_sent_news(
                sent
            )

            published += 1

            # Small delay prevents burst
            time.sleep(2)

    print("=" * 60)
    print(
        f"FINISHED - Published: {published}"
    )
    print("=" * 60)


if __name__ == "__main__":
    main()
