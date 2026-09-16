import os
import re
import json
import time
import html
import hashlib
import tempfile
from urllib.parse import urljoin, urlparse

import requests
import feedparser
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont


# ============================================================
# NABZ KHABAR BOT v7
# GEMINI + VIDEO + SMART FILTER + SHORT SUMMARY
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
AI_API_KEY = os.getenv("AI_API_KEY")

CHANNEL_ID = "@NabzKhabarOfficial"

GEMINI_MODEL = "gemini-3.5-flash-lite"

MAX_NEWS_PER_RUN = int(os.getenv("MAX_NEWS_PER_RUN", "4"))

REQUEST_TIMEOUT = 20
ARTICLE_TIMEOUT = 25
MAX_VIDEO_MB = 49

MAX_BODY_CHARS = 600
MAX_BODY_SENTENCES = 4

SENT_FILE = "sent_news.txt"

FONT_BOLD = "Vazirmatn-Bold.ttf"
FONT_REGULAR = "Vazirmatn-Regular.ttf"


# ============================================================
# RSS SOURCES
# ============================================================

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


# ============================================================
# ROUNDUP FILTER
# ============================================================

ROUNDUP_TITLE_PATTERNS = [
    r"مروری\s+بر\s+(?:مهمترین|مهم‌ترین|آخرین)\s+اخبار",
    r"مرور\s+(?:مهمترین|مهم‌ترین|آخرین)\s+اخبار",
    r"بسته\s+اخبار",
    r"بسته\s+خبری",
    r"اخبار\s+کوتاه",
    r"مهمترین\s+اخبار\s+(?:امروز|این\s+روز)",
    r"مهم‌ترین\s+اخبار\s+(?:امروز|این\s+روز)",
    r"گزیده\s+اخبار",
    r"مروری\s+بر\s+اخبار",
    r"مرور\s+اخبار",
    r"آخرین\s+اخبار\s+استان",
    r"اخبار\s+استان\s+.*در\s+یک\s+نگاه",
    r"در\s+یک\s+نگاه",
    r"آنچه\s+امروز\s+در\s+.*گذشت",
    r"مهمترین\s+رویدادهای\s+امروز",
    r"مهم‌ترین\s+رویدادهای\s+امروز",
]

ROUNDUP_BODY_PATTERNS = [
    r"بسته\s+اخبار\s+کوتاه",
    r"در\s+این\s+بسته\s+خبری",
    r"در\s+این\s+بسته",
    r"مجموعه\s+ای\s+از\s+رویدادها",
    r"مجموعه\s+ای\s+از\s+اخبار",
    r"مجموعه‌ای\s+از\s+رویدادها",
    r"مجموعه‌ای\s+از\s+اخبار",
    r"اخبار\s+کوتاه.*در\s+قالب",
    r"در\s+قالب\s+خبرهای\s+کوتاه",
    r"این\s+صفحه.*به\s*روز(?:رسانی|رسانی)",
    r"این\s+صفحه.*به‌روز\s*می\s*شود",
    r"این\s+صفحه.*به\s+روزرسانی",
    r"در\s+فواصل\s+زمانی\s+مشخص",
    r"مهمترین\s+رویدادها.*مرور",
    r"مهم‌ترین\s+رویدادها.*مرور",
]


# ============================================================
# HTTP SESSION
# ============================================================

SESSION = requests.Session()

SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 Chrome/126 Safari/537.36"
    )
})


# ============================================================
# BASIC HELPERS
# ============================================================

def normalize_space(text):
    if not text:
        return ""

    text = html.unescape(str(text))
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def clean_content(text):
    if not text:
        return ""

    text = html.unescape(str(text))

    text = re.sub(
        r"<script.*?</script>",
        " ",
        text,
        flags=re.I | re.S
    )

    text = re.sub(
        r"<style.*?</style>",
        " ",
        text,
        flags=re.I | re.S
    )

    soup = BeautifulSoup(text, "html.parser")

    for tag in soup.find_all([
        "script",
        "style",
        "noscript",
        "iframe",
        "svg",
        "form",
        "nav",
        "footer",
        "header"
    ]):
        tag.decompose()

    text = soup.get_text(" ", strip=True)

    # Remove common source/reporting phrases
    patterns = [
        r"به گزارش خبرنگار [^،؛:]+[،؛:]?",
        r"به گزارش [^،؛:]+[،؛:]?",
        r"به نقل از [^،؛:]+[،؛:]?",
        r"گزارش خبرنگار [^،؛:]+[،؛:]?",
        r"خبرنگار [^،؛:]+[،؛:]?",
    ]

    for pattern in patterns:
        text = re.sub(
            pattern,
            " ",
            text,
            flags=re.IGNORECASE
        )

    # Remove media markers
    text = re.sub(
        r"\b(?:فیلم|ویدئو|ویدیو|تصویر|عکس)\s*[:|]\s*",
        " ",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def absolute_url(url, base_url):
    if not url:
        return ""

    url = html.unescape(
        str(url).strip()
    )

    if url.startswith("//"):
        return "https:" + url

    if url.startswith("/"):
        return urljoin(
            base_url,
            url
        )

    return url


def make_id(title, link):
    raw = (
        normalize_space(title).lower()
        + "|"
        + normalize_space(link).lower()
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


# ============================================================
# SENT HISTORY
# ============================================================

def load_history():
    if not os.path.exists(SENT_FILE):
        return set()

    try:
        with open(
            SENT_FILE,
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
        with open(
            SENT_FILE,
            "w",
            encoding="utf-8"
        ) as f:
            for item in sorted(history):
                f.write(item + "\n")
    except Exception as e:
        print("History save error:", e)


# ============================================================
# ROUNDUP DETECTION
# ============================================================

def is_roundup_news(title, body=""):
    title = normalize_space(title)
    body = normalize_space(body)

    for pattern in ROUNDUP_TITLE_PATTERNS:
        if re.search(
            pattern,
            title,
            flags=re.IGNORECASE
        ):
            return True

    for pattern in ROUNDUP_BODY_PATTERNS:
        if re.search(
            pattern,
            body,
            flags=re.IGNORECASE
        ):
            return True

    return False


# ============================================================
# SENTENCE PROCESSING
# ============================================================

def split_sentences(text):
    text = normalize_space(text)

    if not text:
        return []

    parts = re.split(
        r"(?<=[.!؟])\s+|(?<=[؛])\s+",
        text
    )

    result = []

    for part in parts:
        part = normalize_space(part)

        if len(part) < 15:
            continue

        result.append(part)

    return result


def sentence_score(sentence):
    score = 0

    # Sentences containing numbers often carry important facts
    if re.search(r"\d", sentence):
        score += 3

    # Important news indicators
    keywords = [
        "اعلام",
        "تصمیم",
        "تصویب",
        "آغاز",
        "توقف",
        "افزایش",
        "کاهش",
        "کشته",
        "زخمی",
        "بازداشت",
        "حمله",
        "انفجار",
        "قیمت",
        "درصد",
        "میلیون",
        "میلیارد",
        "هزار",
        "استان",
        "کشور",
        "رئیس",
        "وزیر",
        "مدیر",
        "تیم",
        "قهرمان",
        "برنده",
    ]

    for word in keywords:
        if word in sentence:
            score += 1

    # Avoid extremely long administrative sentences
    if len(sentence) > 260:
        score -= 2

    return score


# ============================================================
# HARD SHORT SUMMARY
# ============================================================

def enforce_short_summary(text, max_chars=MAX_BODY_CHARS):
    if not text:
        return ""

    text = clean_content(text)

    if not text:
        return ""

    sentences = split_sentences(text)

    if not sentences:
        return text[:max_chars].rstrip() + "…"

    # Remove duplicate sentences
    unique = []

    for sentence in sentences:
        key = re.sub(
            r"\W+",
            "",
            sentence.lower()
        )

        duplicate = False

        for old in unique:
            old_key = re.sub(
                r"\W+",
                "",
                old.lower()
            )

            if (
                key == old_key
                or (
                    len(key) > 40
                    and (
                        key in old_key
                        or old_key in key
                    )
                )
            ):
                duplicate = True
                break

        if not duplicate:
            unique.append(sentence)

    sentences = unique

    # First sentence is always the lead
    selected = [sentences[0]]

    remaining = sentences[1:]

    remaining.sort(
        key=sentence_score,
        reverse=True
    )

    for sentence in remaining:

        if len(selected) >= MAX_BODY_SENTENCES:
            break

        candidate = " ".join(
            selected + [sentence]
        )

        if len(candidate) <= max_chars:
            selected.append(sentence)

    result = " ".join(selected).strip()

    # Final safety
    if len(result) > max_chars:

        result = result[:max_chars]

        cut_positions = [
            result.rfind("۔"),
            result.rfind("."),
            result.rfind("؟"),
            result.rfind("!"),
            result.rfind("؛"),
            result.rfind(" ")
        ]

        cut = max(cut_positions)

        if cut >= int(max_chars * 0.55):
            result = result[:cut].strip()

        else:
            result = result.rstrip()

        result = result.rstrip(
            "،؛:.- "
        ) + "…"

    return result


# ============================================================
# TITLE CLEANING
# ============================================================

def clean_title(title):
    title = clean_content(title)

    title = re.sub(
        r"^(?:فیلم|ویدئو|ویدیو|عکس|تصویر)\s*[\|:\-]\s*",
        "",
        title,
        flags=re.I
    )

    title = re.sub(
        r"^(?:مشهد|تهران|تبریز|شیراز|کرج|قم|اصفهان)\s*[-–—]\s*",
        "",
        title
    )

    title = normalize_space(title)

    return title


# ============================================================
# GEMINI
# ============================================================

def gemini_request(title, article_text):
    if not AI_API_KEY:
        return None

    article_text = clean_content(article_text)

    if not article_text:
        return None

    prompt = f"""
تو ویراستار حرفه‌ای یک کانال خبری تلگرامی هستی.

خبر زیر را برای انتشار در کانال «نبض خبر» آماده کن.

قوانین بسیار مهم:

- خلاصه واقعی بنویس، نه بازنویسی کامل مقاله.
- حداکثر 4 جمله.
- مجموع متن خلاصه حداکثر 550 کاراکتر باشد.
- متن حداکثر 2 پاراگراف کوتاه باشد.
- فقط 2 تا 4 نکته مهم خبر را نگه دار.
- جزئیات فرعی، اداری، تشریفاتی و تکراری را حذف کن.
- اگر تعداد زیادی آمار وجود دارد، فقط مهم‌ترین آمارها را نگه دار.
- اطلاعات مهم مانند تعداد، قیمت، درصد، زمان، نتیجه یا تصمیم اصلی را در صورت اهمیت حفظ کن.
- هیچ اطلاعات جدیدی اضافه نکن.
- نام خبرگزاری و منبع را حذف کن.
- لینک را حذف کن.
- عبارت‌هایی مثل «به گزارش خبرنگار»، «به نقل از»، «این مقام افزود» و مشابه آن را حذف کن.
- لحن طبیعی، حرفه‌ای، خبری و روان باشد.
- از تکرار یک مفهوم خودداری کن.
- اگر خبر کوتاه است، آن را بی‌دلیل طولانی نکن.
- اگر خبر درباره یک رویداد مشخص است، روی همان رویداد تمرکز کن.
- خروجی فقط JSON معتبر باشد.

فرمت دقیق:

{{
  "title": "عنوان کوتاه و خبری",
  "body": "خلاصه بسیار کوتاه خبر"
}}

عنوان اصلی:
{title}

متن خبر:
{article_text[:12000]}
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
        response = SESSION.post(
            url,
            params={
                "key": AI_API_KEY
            },
            json=payload,
            timeout=35
        )

        if response.status_code != 200:
            print(
                "Gemini error:",
                response.status_code,
                response.text[:500]
            )
            return None

        data = response.json()

        text = (
            data
            .get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )

        if not text:
            return None

        text = text.strip()

        # Remove markdown fences
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
        ).strip()

        # Extract JSON object if Gemini added extra text
        match = re.search(
            r"\{.*\}",
            text,
            flags=re.S
        )

        if match:
            text = match.group(0)

        result = json.loads(text)

        result_title = clean_title(
            result.get("title", "")
        )

        result_body = enforce_short_summary(
            result.get("body", ""),
            MAX_BODY_CHARS
        )

        if is_roundup_news(
            result_title,
            result_body
        ):
            return {
                "roundup": True
            }

        if not result_title:
            result_title = clean_title(title)

        if not result_body:
            return None

        return {
            "title": result_title,
            "body": result_body
        }

    except Exception as e:
        print(
            "Gemini exception:",
            str(e)[:500]
        )
        return None


# ============================================================
# LOCAL FALLBACK
# ============================================================

def local_news_engine(title, article_text):
    title = clean_title(title)

    body = clean_content(article_text)

    if is_roundup_news(title, body):
        return {
            "roundup": True
        }

    body = enforce_short_summary(
        body,
        MAX_BODY_CHARS
    )

    if not body:
        return None

    return {
        "title": title,
        "body": body
    }


# ============================================================
# ARTICLE EXTRACTION
# ============================================================

def extract_article(url):
    if not url:
        return ""

    try:
        response = SESSION.get(
            url,
            timeout=ARTICLE_TIMEOUT
        )

        if response.status_code != 200:
            return ""

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        for tag in soup.find_all([
            "script",
            "style",
            "noscript",
            "iframe",
            "nav",
            "footer",
            "header",
            "form"
        ]):
            tag.decompose()

        candidates = []

        selectors = [
            "article",
            "[itemprop='articleBody']",
            ".article-body",
            ".article-content",
            ".news-content",
            ".content",
            ".story",
            ".story-body",
            ".post-content",
            "main"
        ]

        for selector in selectors:
            try:
                nodes = soup.select(selector)

                for node in nodes:
                    text = node.get_text(
                        " ",
                        strip=True
                    )

                    if len(text) > 200:
                        candidates.append(text)
            except Exception:
                pass

        if candidates:
            candidates.sort(
                key=len,
                reverse=True
            )

            return clean_content(
                candidates[0]
            )

        paragraphs = []

        for p in soup.find_all("p"):
            text = normalize_space(
                p.get_text(" ", strip=True)
            )

            if len(text) >= 40:
                paragraphs.append(text)

        return clean_content(
            " ".join(paragraphs)
        )

    except Exception as e:
        print(
            "Article extraction error:",
            str(e)[:300]
        )
        return ""


# ============================================================
# MEDIA EXTRACTION
# ============================================================

def find_image_url(entry, article_url):
    possible = []

    if entry.get("media_content"):
        for item in entry.media_content:
            if item.get("url"):
                possible.append(
                    absolute_url(
                        item.get("url"),
                        article_url
                    )
                )

    if entry.get("media_thumbnail"):
        for item in entry.media_thumbnail:
            if item.get("url"):
                possible.append(
                    absolute_url(
                        item.get("url"),
                        article_url
                    )
                )

    for enclosure in entry.get("enclosures", []):
        url = enclosure.get("href") or enclosure.get("url")

        if url:
            mime = str(
                enclosure.get("type", "")
            ).lower()

            if (
                "image" in mime
                or not mime
            ):
                possible.append(
                    absolute_url(
                        url,
                        article_url
                    )
                )

    for link in entry.get("links", []):
        href = link.get("href", "")
        mime = str(
            link.get("type", "")
        ).lower()

        if (
            "image" in mime
            and href
        ):
            possible.append(
                absolute_url(
                    href,
                    article_url
                )
            )

    try:
        response = SESSION.get(
            article_url,
            timeout=ARTICLE_TIMEOUT
        )

        if response.status_code == 200:
            soup = BeautifulSoup(
                response.text,
                "html.parser"
            )

            meta_names = [
                ("property", "og:image"),
                ("name", "twitter:image"),
                ("property", "twitter:image")
            ]

            for attr, value in meta_names:
                tag = soup.find(
                    "meta",
                    attrs={attr: value}
                )

                if tag and tag.get("content"):
                    possible.append(
                        absolute_url(
                            tag["content"],
                            article_url
                        )
                    )

    except Exception:
        pass

    for url in possible:
        if url:
            return url

    return ""


def find_video_url(entry, article_url):
    possible = []

    # RSS media content
    for item in entry.get("media_content", []):
        url = item.get("url") or item.get("href")
        mime = str(
            item.get("type", "")
        ).lower()

        if url:
            if (
                "video" in mime
                or re.search(
                    r"\.(mp4|webm|mov)(?:\?|$)",
                    url,
                    re.I
                )
            ):
                possible.append(
                    absolute_url(
                        url,
                        article_url
                    )
                )

    # RSS enclosures
    for enclosure in entry.get("enclosures", []):
        url = (
            enclosure.get("href")
            or enclosure.get("url")
        )

        mime = str(
            enclosure.get("type", "")
        ).lower()

        if url and (
            "video" in mime
            or re.search(
                r"\.(mp4|webm|mov)(?:\?|$)",
                url,
                re.I
            )
        ):
            possible.append(
                absolute_url(
                    url,
                    article_url
                )
            )

    # Article HTML
    try:
        response = SESSION.get(
            article_url,
            timeout=ARTICLE_TIMEOUT
        )

        if response.status_code == 200:

            soup = BeautifulSoup(
                response.text,
                "html.parser"
            )

            meta_values = [
                "og:video",
                "og:video:url",
                "og:video:secure_url",
                "twitter:player:stream"
            ]

            for value in meta_values:
                tag = soup.find(
                    "meta",
                    attrs={
                        "property": value
                    }
                )

                if not tag:
                    tag = soup.find(
                        "meta",
                        attrs={
                            "name": value
                        }
                    )

                if tag and tag.get("content"):
                    possible.append(
                        absolute_url(
                            tag["content"],
                            article_url
                        )
                    )

            # video/source tags
            for source in soup.find_all(
                ["video", "source"]
            ):
                for attr in [
                    "src",
                    "data-src",
                    "data-video",
                    "data-url"
                ]:
                    value = source.get(attr)

                    if value:
                        possible.append(
                            absolute_url(
                                value,
                                article_url
                            )
                        )

            # JSON-LD
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

                        for key in [
                            "contentUrl",
                            "embedUrl"
                        ]:
                            value = obj.get(key)

                            if value:
                                possible.append(
                                    absolute_url(
                                        value,
                                        article_url
                                    )
                                )

                except Exception:
                    pass

    except Exception as e:
        print(
            "Video scan error:",
            str(e)[:300]
        )

    # Clean and prioritize direct video files
    cleaned = []

    for url in possible:
        if not url:
            continue

        if url not in cleaned:
            cleaned.append(url)

    direct = [
        url for url in cleaned
        if re.search(
            r"\.(mp4|webm|mov)(?:\?|$)",
            url,
            re.I
        )
    ]

    if direct:
        return direct[0]

    if cleaned:
        return cleaned[0]

    return ""


# ============================================================
# DOWNLOAD MEDIA
# ============================================================

def download_file(url, suffix):
    if not url:
        return None

    try:
        response = SESSION.get(
            url,
            stream=True,
            timeout=40,
            allow_redirects=True
        )

        if response.status_code != 200:
            print(
                "Media HTTP error:",
                response.status_code
            )
            return None

        content_type = str(
            response.headers.get(
                "Content-Type",
                ""
            )
        ).lower()

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

                if (
                    suffix == ".mp4"
                    and size_mb > MAX_VIDEO_MB
                ):
                    print(
                        "Video too large:",
                        round(size_mb, 1),
                        "MB"
                    )
                    return None

            except Exception:
                pass

        fd, path = tempfile.mkstemp(
            suffix=suffix
        )

        os.close(fd)

        total = 0
        max_bytes = (
            MAX_VIDEO_MB
            * 1024
            * 1024
            if suffix == ".mp4"
            else 15
            * 1024
            * 1024
        )

        with open(
            path,
            "wb"
        ) as f:

            for chunk in response.iter_content(
                chunk_size=1024 * 256
            ):
                if not chunk:
                    continue

                total += len(chunk)

                if total > max_bytes:
                    print(
                        "Downloaded media too large"
                    )

                    try:
                        os.remove(path)
                    except Exception:
                        pass

                    return None

                f.write(chunk)

        if total < 100:
            try:
                os.remove(path)
            except Exception:
                pass

            return None

        print(
            "Downloaded:",
            round(
                total / 1024 / 1024,
                2
            ),
            "MB"
        )

        return path

    except Exception as e:
        print(
            "Download error:",
            str(e)[:300]
        )
        return None


# ============================================================
# WATERMARK
# ============================================================

def add_watermark(image_path):
    try:
        image = Image.open(
            image_path
        ).convert("RGB")

        calculated_size = int(
            image.width * 0.022
        )

        font_size = max(
            18,
            min(
                calculated_size,
                42
            )
        )

        try:
            font = ImageFont.truetype(
                FONT_BOLD,
                font_size
            )
        except Exception:
            font = ImageFont.load_default()

        text = "نبض خبر"

        margin = max(
            10,
            int(image.width * 0.018)
        )

        draw = ImageDraw.Draw(
            image
        )

        bbox = draw.textbbox(
            (0, 0),
            text,
            font=font
        )

        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        x = (
            image.width
            - text_width
            - margin
        )

        y = (
            image.height
            - text_height
            - margin
        )

        # subtle shadow
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

        image.save(
            image_path,
            "JPEG",
            quality=92,
            optimize=True
        )

        return image_path

    except Exception as e:
        print(
            "Watermark error:",
            str(e)[:300]
        )
        return image_path


# ============================================================
# TELEGRAM
# ============================================================

def telegram_url(method):
    return (
        f"https://api.telegram.org/bot"
        f"{BOT_TOKEN}/{method}"
    )


def telegram_post(method, files=None, data=None):
    try:
        response = requests.post(
            telegram_url(method),
            files=files,
            data=data,
            timeout=60
        )

        if response.status_code != 200:
            print(
                "Telegram HTTP error:",
                response.status_code,
                response.text[:500]
            )
            return False

        result = response.json()

        if not result.get("ok"):
            print(
                "Telegram API error:",
                result
            )
            return False

        return True

    except Exception as e:
        print(
            "Telegram exception:",
            str(e)[:500]
        )
        return False


def make_caption(title, body):
    title = clean_title(title)
    body = enforce_short_summary(
        body,
        MAX_BODY_CHARS
    )

    caption = (
        f"📰 <b>{html.escape(title)}</b>\n\n"
        f"{html.escape(body)}\n\n"
        f"#نبض_خبر"
    )

    # Telegram caption limit safety
    if len(caption) > 1024:

        available = (
            1024
            - len(
                f"📰 <b>{html.escape(title)}</b>\n\n"
                f"\n\n#نبض_خبر"
            )
        )

        if available < 100:
            available = 100

        body = body[:available]

        cut = body.rfind(" ")

        if cut > 100:
            body = body[:cut]

        body = body.rstrip(
            "،؛:.- "
        ) + "…"

        caption = (
            f"📰 <b>{html.escape(title)}</b>\n\n"
            f"{html.escape(body)}\n\n"
            f"#نبض_خبر"
        )

    return caption


def send_video(path, title, body):
    caption = make_caption(
        title,
        body
    )

    try:
        with open(
            path,
            "rb"
        ) as video:

            return telegram_post(
                "sendVideo",
                files={
                    "video": video
                },
                data={
                    "chat_id": CHANNEL_ID,
                    "caption": caption,
                    "parse_mode": "HTML",
                    "supports_streaming": "true"
                }
            )

    finally:
        try:
            os.remove(path)
        except Exception:
            pass


def send_photo(path, title, body):
    caption = make_caption(
        title,
        body
    )

    try:
        with open(
            path,
            "rb"
        ) as photo:

            return telegram_post(
                "sendPhoto",
                files={
                    "photo": photo
                },
                data={
                    "chat_id": CHANNEL_ID,
                    "caption": caption,
                    "parse_mode": "HTML"
                }
            )

    finally:
        try:
            os.remove(path)
        except Exception:
            pass


def send_text(title, body):
    caption = make_caption(
        title,
        body
    )

    return telegram_post(
        "sendMessage",
        data={
            "chat_id": CHANNEL_ID,
            "text": caption,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true"
        }
    )


# ============================================================
# RSS COLLECTION
# ============================================================

def collect_candidates(history):
    candidates = []
    seen = set()

    for category, rss_url in RSS_FEEDS:

        try:
            response = SESSION.get(
                rss_url,
                timeout=REQUEST_TIMEOUT
            )

            if response.status_code != 200:
                print(
                    "RSS ERROR:",
                    category,
                    response.status_code,
                    rss_url
                )
                continue

            feed = feedparser.parse(
                response.content
            )

            entries = feed.entries[:8]

            print(
                "RSS OK:",
                category,
                "|",
                len(entries),
                "|",
                rss_url
            )

            for entry in entries:

                title = clean_title(
                    entry.get(
                        "title",
                        ""
                    )
                )

                link = (
                    entry.get("link")
                    or entry.get("id")
                    or ""
                )

                link = absolute_url(
                    link,
                    rss_url
                )

                if not title or not link:
                    continue

                if is_roundup_news(
                    title
                ):
                    print(
                        "SKIPPED ROUNDUP:",
                        title
                    )
                    continue

                item_id = make_id(
                    title,
                    link
                )

                if item_id in history:
                    continue

                if item_id in seen:
                    continue

                seen.add(item_id)

                published = (
                    entry.get(
                        "published",
                        ""
                    )
                    or entry.get(
                        "updated",
                        ""
                    )
                )

                candidates.append({
                    "id": item_id,
                    "category": category,
                    "title": title,
                    "link": link,
                    "published": published,
                    "entry": entry
                })

        except Exception as e:
            print(
                "RSS exception:",
                rss_url,
                str(e)[:300]
            )

    # Newest first when RSS dates are parseable,
    # otherwise preserve feed order.
    candidates.sort(
        key=lambda x: x.get(
            "published",
            ""
        ),
        reverse=True
    )

    return candidates


# ============================================================
# PROCESS NEWS
# ============================================================

def process_news(item):
    original_title = item["title"]
    article_url = item["link"]
    entry = item["entry"]

    print(
        "Processing:",
        original_title
    )

    # First try RSS summary
    rss_body = ""

    for field in [
        "summary",
        "description",
        "content"
    ]:
        value = entry.get(
            field,
            ""
        )

        if isinstance(value, list):
            value = " ".join(
                str(x.get("value", ""))
                for x in value
                if isinstance(x, dict)
            )

        if value:
            rss_body += " " + str(value)

    rss_body = clean_content(
        rss_body
    )

    # Extract full article
    article_text = extract_article(
        article_url
    )

    if len(article_text) < len(rss_body):
        source_text = rss_body
    else:
        source_text = article_text

    if not source_text:
        source_text = rss_body

    if is_roundup_news(
        original_title,
        source_text
    ):
        print(
            "SKIPPED ROUNDUP:",
            original_title
        )
        return False

    # AI summary
    result = gemini_request(
        original_title,
        source_text
    )

    if result and result.get("roundup"):
        print(
            "SKIPPED ROUNDUP BY AI:",
            original_title
        )
        return False

    if not result:
        print(
            "Using local news engine."
        )

        result = local_news_engine(
            original_title,
            source_text
        )

    if not result:
        print(
            "Could not create summary."
        )
        return False

    if result.get("roundup"):
        print(
            "SKIPPED ROUNDUP:",
            original_title
        )
        return False

    title = clean_title(
        result.get(
            "title",
            original_title
        )
    )

    body = enforce_short_summary(
        result.get(
            "body",
            ""
        ),
        MAX_BODY_CHARS
    )

    if not title or not body:
        return False

    if is_roundup_news(
        title,
        body
    ):
        print(
            "SKIPPED FINAL ROUNDUP:",
            title
        )
        return False

    # ========================================================
    # VIDEO FIRST
    # ========================================================

    video_url = find_video_url(
        entry,
        article_url
    )

    if video_url:
        print(
            "Downloading video:",
            video_url
        )

        extension = ".mp4"

        if re.search(
            r"\.webm(?:\?|$)",
            video_url,
            re.I
        ):
            extension = ".webm"

        elif re.search(
            r"\.mov(?:\?|$)",
            video_url,
            re.I
        ):
            extension = ".mov"

        video_path = download_file(
            video_url,
            extension
        )

        if video_path:

            # Telegram generally accepts these directly.
            if send_video(
                video_path,
                title,
                body
            ):
                print(
                    "VIDEO PUBLISHED"
                )
                print(
                    "PUBLISHED:",
                    title
                )
                return True

            print(
                "Video send failed."
            )

    # ========================================================
    # IMAGE FALLBACK
    # ========================================================

    image_url = find_image_url(
        entry,
        article_url
    )

    if image_url:
        print(
            "Downloading image:",
            image_url
        )

        image_path = download_file(
            image_url,
            ".jpg"
        )

        if image_path:

            image_path = add_watermark(
                image_path
            )

            if send_photo(
                image_path,
                title,
                body
            ):
                print(
                    "PHOTO PUBLISHED"
                )
                print(
                    "PUBLISHED:",
                    title
                )
                return True

            print(
                "Photo send failed."
            )

    # ========================================================
    # TEXT FALLBACK
    # ========================================================

    if send_text(
        title,
        body
    ):
        print(
            "TEXT PUBLISHED"
        )
        print(
            "PUBLISHED:",
            title
        )
        return True

    return False


# ============================================================
# MAIN
# ============================================================

def main():

    start_time = time.time()

    print(
        "===================================="
    )
    print(
        "NABZ KHABAR BOT v7"
    )
    print(
        "GEMINI + VIDEO + SMART FILTER + SHORT SUMMARY"
    )
    print(
        "===================================="
    )

    if not BOT_TOKEN:
        print(
            "ERROR: BOT_TOKEN is missing."
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

    print(
        "Candidates found:",
        len(candidates)
    )

    published_count = 0

    for item in candidates:

        if published_count >= MAX_NEWS_PER_RUN:
            break

        try:

            success = process_news(
                item
            )

            if success:

                history.add(
                    item["id"]
                )

                save_history(
                    history
                )

                published_count += 1

                # Small delay to reduce API pressure
                time.sleep(2)

        except Exception as e:

            print(
                "PROCESS ERROR:",
                str(e)[:500]
            )

    runtime = (
        time.time()
        - start_time
    )

    print(
        "FINISHED - Published:",
        published_count
    )

    print(
        "Runtime:",
        round(runtime, 1),
        "s"
    )


if __name__ == "__main__":
    main()
