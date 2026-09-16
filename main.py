import os
import re
import html
import time
import hashlib
import logging
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

# جلوگیری از گیر کردن کل اجرا
RUN_DEADLINE_SECONDS = 180

# تعداد خبرهایی که از هر RSS بررسی می‌کنیم
MAX_ENTRIES_PER_FEED = 8

# زمان اتصال / دریافت
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

    ("ورزش", "https://www.varzesh3.com/rss"),
    ("ورزش", "https://www.isna.ir/rss?serviceid=5"),

    ("اقتصاد", "https://www.irna.ir/rss/economy"),
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

    text = BeautifulSoup(str(text), "html.parser").get_text(" ", strip=True)

    text = html.unescape(text)

    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"www\.\S+", "", text)

    text = re.sub(r"@\w+", "", text)

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_title(title):
    title = clean_text(title).lower()

    title = title.replace("ي", "ی")
    title = title.replace("ك", "ک")
    title = title.replace("ۀ", "ه")
    title = title.replace("ة", "ه")

    title = re.sub(r"[^\w\u0600-\u06ff ]", " ", title)
    title = re.sub(r"\s+", " ", title)

    return title.strip()


def make_news_id(title, link):
    base = normalize_title(title) + "|" + (link or "")
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


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
        # فقط آخرین 300 مورد را نگه می‌داریم
        items = list(history)[-300:]

        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            for item in items:
                f.write(item + "\n")
    except Exception as e:
        log.info(f"History save error: {e}")


def deadline_reached(start_time):
    return time.monotonic() - start_time >= RUN_DEADLINE_SECONDS


# =========================================================
# RSS FETCH
# =========================================================

def fetch_feed(source):
    category, url = source

    try:
        response = SESSION.get(
            url,
            timeout=RSS_TIMEOUT
        )

        response.raise_for_status()

        parsed = feedparser.parse(response.content)

        entries = parsed.entries[:MAX_ENTRIES_PER_FEED]

        log.info(
            f"RSS OK: {category} | {len(entries)} | {url}"
        )

        return category, entries

    except Exception as e:
        log.info(
            f"RSS FAILED: {category} | {url} | {e}"
        )
        return category, []


def collect_candidates(history, start_time):
    candidates = []
    seen_ids = set()

    log.info("Collecting RSS feeds...")

    # موازی‌سازی RSSها
    with ThreadPoolExecutor(max_workers=8) as executor:

        futures = [
            executor.submit(fetch_feed, source)
            for source in RSS_FEEDS
        ]

        for future in as_completed(futures):

            if deadline_reached(start_time):
                log.info("Deadline reached while collecting feeds.")
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

                news_id = make_news_id(title, link)

                if news_id in history:
                    continue

                if news_id in seen_ids:
                    continue

                seen_ids.add(news_id)

                summary = clean_text(
                    entry.get("summary")
                    or entry.get("description")
                    or entry.get("content", [{}])[0].get("value", "")
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

    log.info(f"Candidates found: {len(candidates)}")

    return candidates


# =========================================================
# ARTICLE FETCH
# =========================================================

def extract_media_from_soup(soup):
    # og:image
    og_image = soup.find(
        "meta",
        property="og:image"
    )

    if og_image and og_image.get("content"):
        return {
            "type": "image",
            "url": og_image["content"].strip()
        }

    # twitter:image
    twitter_image = soup.find(
        "meta",
        attrs={"name": "twitter:image"}
    )

    if twitter_image and twitter_image.get("content"):
        return {
            "type": "image",
            "url": twitter_image["content"].strip()
        }

    # video
    og_video = soup.find(
        "meta",
        property="og:video"
    )

    if og_video and og_video.get("content"):
        return {
            "type": "video",
            "url": og_video["content"].strip()
        }

    # video tags
    video = soup.find("video")

    if video:
        source = video.find("source")

        if source and source.get("src"):
            return {
                "type": "video",
                "url": source["src"]
            }

        if video.get("src"):
            return {
                "type": "video",
                "url": video["src"]
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

        # حذف موارد غیرمحتوایی
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

        media = extract_media_from_soup(soup)

        # تلاش برای پیدا کردن محتوای اصلی
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
            containers.extend(
                soup.select(selector)
            )

        best_text = ""

        for container in containers:
            text = clean_text(
                container.get_text(" ", strip=True)
            )

            if len(text) > len(best_text):
                best_text = text

        if len(best_text) < 300:
            paragraphs = soup.find_all("p")

            texts = [
                clean_text(p.get_text(" ", strip=True))
                for p in paragraphs
            ]

            texts = [
                x for x in texts
                if len(x) > 30
            ]

            best_text = " ".join(texts)

        return {
            "text": best_text[:12000],
            "media": media
        }

    except Exception as e:
        log.info(f"Article fetch failed: {url} | {e}")

        return {
            "text": "",
            "media": None
        }


# =========================================================
# RSS MEDIA
# =========================================================

def extract_rss_media(entry):
    # media_content
    media_content = entry.get("media_content")

    if media_content:
        for media in media_content:

            url = media.get("url")

            if not url:
                continue

            mime = media.get("type", "")

            if "video" in mime:
                return {
                    "type": "video",
                    "url": url
                }

            return {
                "type": "image",
                "url": url
            }

    # enclosure
    enclosures = entry.get("enclosures")

    if enclosures:
        for enclosure in enclosures:

            url = enclosure.get("href") or enclosure.get("url")

            if not url:
                continue

            mime = enclosure.get("type", "")

            if "video" in mime:
                return {
                    "type": "video",
                    "url": url
                }

            return {
                "type": "image",
                "url": url
            }

    return None


# =========================================================
# GEMINI
# =========================================================

gemini_disabled = False


def generate_news_text(title, text, category):
    global gemini_disabled

    if not AI_API_KEY:
        return None

    if gemini_disabled:
        return None

    if not text:
        text = title

    prompt = f"""
تو ویراستار حرفه‌ای یک کانال خبری فارسی هستی.

خبر زیر را برای انتشار در کانال «نبض خبر» بازنویسی کن.

دسته‌بندی:
{category}

عنوان اولیه:
{title}

متن:
{text}

قوانین بسیار مهم:

1. واقعیت جدیدی اضافه نکن.
2. اگر اطلاعات کافی نیست، حدس نزن.
3. متن کاملاً فارسی و روان باشد.
4. لحن حرفه‌ای و خبری باشد.
5. از عبارت‌های تبلیغاتی یا احساسی استفاده نکن.
6. متن را خلاصه اما کامل بنویس.
7. عنوان را در صورت نیاز حرفه‌ای‌تر کن.
8. جمله‌های تکراری را حذف کن.
9. منبع، نام سایت، لینک، آیدی کانال و هشتگ تولید نکن.
10. هیچ @username در خروجی ننویس.
11. فقط در این قالب خروجی بده:

TITLE:
عنوان

BODY:
متن خبر در 2 تا 4 پاراگراف کوتاه
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
                f"Gemini error {response.status_code}: "
                f"{response.text[:500]}"
            )

            # اگر مدل/کلید مشکل داشت، در همین اجرا
            # دیگر برای هر خبر دوباره صبر نکن
            if response.status_code in (400, 401, 403, 404):
                gemini_disabled = True

            return None

        data = response.json()

        candidates = data.get("candidates", [])

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

        return output if output else None

    except Exception as e:
        log.info(f"Gemini exception: {e}")
        return None


# =========================================================
# TEXT CLEANING
# =========================================================

def remove_duplicate_sentences(text):
    if not text:
        return ""

    text = text.replace("\r", "\n")

    # حذف خطوط تکراری
    lines = [
        clean_text(line)
        for line in text.split("\n")
        if clean_text(line)
    ]

    result = []
    seen = set()

    for line in lines:
        key = normalize_title(line)

        if not key:
            continue

        if key in seen:
            continue

        seen.add(key)
        result.append(line)

    text = "\n\n".join(result)

    # اگر یک جمله دقیقاً دوبار پشت سر هم آمده باشد
    sentences = re.split(
        r"(?<=[.!؟])\s+",
        text
    )

    cleaned = []
    seen_sentences = set()

    for sentence in sentences:

        sentence = sentence.strip()

        if not sentence:
            continue

        key = normalize_title(sentence)

        if key in seen_sentences:
            continue

        seen_sentences.add(key)
        cleaned.append(sentence)

    return " ".join(cleaned)


def parse_ai_output(output, fallback_title):
    if not output:
        return fallback_title, ""

    output = output.replace("**", "")

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
        body = clean_text(
            body_match.group(1)
        )
    else:
        body = clean_text(output)

    body = remove_duplicate_sentences(body)

    # حذف چیزهایی که نباید وارد کانال شوند
    body = re.sub(
        r"https?://\S+",
        "",
        body
    )

    body = re.sub(
        r"@\w+",
        "",
        body
    )

    body = re.sub(
        r"#\S+",
        "",
        body
    )

    body = re.sub(
        r"\s+",
        " ",
        body
    ).strip()

    return title, body


def fallback_news_text(title, summary, article_text):
    source_text = article_text or summary or ""

    source_text = clean_text(source_text)

    if not source_text:
        return title, ""

    # اگر عنوان داخل متن دوباره آمده بود حذفش می‌کنیم
    normalized_title = normalize_title(title)

    sentences = re.split(
        r"(?<=[.!؟])\s+",
        source_text
    )

    result = []

    for sentence in sentences:

        sentence = sentence.strip()

        if not sentence:
            continue

        normalized = normalize_title(sentence)

        if normalized == normalized_title:
            continue

        result.append(sentence)

    body = " ".join(result)

    body = remove_duplicate_sentences(body)

    # طول مناسب برای تلگرام
    if len(body) > 2200:
        body = body[:2200]

        last_space = body.rfind(" ")

        if last_space > 1500:
            body = body[:last_space]

        body += "…"

    return title, body


# =========================================================
# IMAGE
# =========================================================

def download_image(url):
    try:
        response = SESSION.get(
            url,
            timeout=ARTICLE_TIMEOUT,
            headers={
                "User-Agent": SESSION.headers["User-Agent"]
            }
        )

        response.raise_for_status()

        content_type = response.headers.get(
            "Content-Type",
            ""
        )

        if "image" not in content_type:
            return None

        image = Image.open(
            BytesIO(response.content)
        ).convert("RGB")

        # اندازه منطقی
        image.thumbnail((1600, 1600))

        return image

    except Exception as e:
        log.info(f"Image download failed: {e}")
        return None


def add_watermark(image):
    try:
        draw = ImageDraw.Draw(image)

        try:
            font = ImageFont.truetype(
                FONT_BOLD,
                max(24, image.width // 35)
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

        x = image.width - tw - margin
        y = image.height - th - margin

        # سایه
        draw.text(
            (x + 2, y + 2),
            text,
            font=font,
            fill=(0, 0, 0)
        )

        draw.text(
            (x, y),
            text,
            font=font,
            fill=(255, 255, 255)
        )

        return image

    except Exception as e:
        log.info(f"Watermark error: {e}")
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
            f"Telegram photo error: {response.text[:500]}"
        )

    except Exception as e:
        log.info(f"Telegram photo exception: {e}")

    return False


def send_video(video_url, caption):
    try:
        response = SESSION.get(
            video_url,
            timeout=ARTICLE_TIMEOUT,
            stream=True
        )

        response.raise_for_status()

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
            f"Telegram video error: {result.text[:500]}"
        )

    except Exception as e:
        log.info(f"Video error: {e}")

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
            f"Telegram text error: {response.text[:500]}"
        )

    except Exception as e:
        log.info(f"Telegram text exception: {e}")

    return False


# =========================================================
# CAPTION
# =========================================================

def make_caption(title, body):
    title = clean_text(title)
    body = clean_text(body)

    if not body:
        body = "جزئیات این خبر در حال تکمیل است."

    caption = (
        f"📰 <b>{html.escape(title)}</b>\n\n"
        f"{html.escape(body)}\n\n"
        f"#نبض_خبر"
    )

    # محدودیت کپشن تلگرام
    if len(caption) > 1024:

        max_body = 1024 - len(
            f"📰 <b>{html.escape(title)}</b>\n\n"
            f"\n\n#نبض_خبر"
        ) - 10

        if max_body < 100:
            max_body = 100

        body = body[:max_body].rstrip()

        caption = (
            f"📰 <b>{html.escape(title)}</b>\n\n"
            f"{html.escape(body)}…\n\n"
            f"#نبض_خبر"
        )

    return caption


# =========================================================
# PROCESS ONE NEWS
# =========================================================

def process_news(news, history, start_time):

    if deadline_reached(start_time):
        return False

    title = news["title"]
    category = news["category"]

    log.info(
        f"Processing: {title}"
    )

    # -----------------------------------------
    # Media موجود در RSS
    # -----------------------------------------

    media = extract_rss_media(
        news["entry"]
    )

    article_text = news["summary"]

    # -----------------------------------------
    # فقط برای خبرهایی که قرار است واقعاً
    # منتشر شوند، صفحه اصلی را باز می‌کنیم.
    # -----------------------------------------

    if not media or len(article_text) < 500:

        data = extract_article_data(
            news["link"]
        )

        if data.get("text"):
            article_text = data["text"]

        if not media:
            media = data.get("media")

    news["article_text"] = article_text
    news["media"] = media

    # -----------------------------------------
    # AI
    # -----------------------------------------

    ai_output = generate_news_text(
        title,
        article_text,
        category
    )

    if ai_output:

        final_title, final_body = parse_ai_output(
            ai_output,
            title
        )

    else:

        final_title, final_body = fallback_news_text(
            title,
            news["summary"],
            article_text
        )

    if not final_title:
        final_title = title

    caption = make_caption(
        final_title,
        final_body
    )

    # -----------------------------------------
    # انتشار
    # -----------------------------------------

    published = False

    if media:

        media_type = media.get("type")
        media_url = media.get("url")

        if media_type == "video" and media_url:

            log.info(
                f"Trying video: {media_url}"
            )

            published = send_video(
                media_url,
                caption
            )

        elif media_type == "image" and media_url:

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

    # اگر مدیا نشد، متن
    if not published:

        log.info("Falling back to text post.")

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
    log.info("====================================")
    log.info("NABZ KHABAR BOT STARTED")
    log.info("====================================")

    if not BOT_TOKEN:
        log.info("ERROR: BOT_TOKEN is missing.")
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
        log.info("FINISHED - Published: 0")
        return

    # -----------------------------------------
    # از بین کاندیداها فقط تعداد محدودی را
    # برای پردازش کامل انتخاب می‌کنیم.
    # -----------------------------------------

    # اول خبرهای جدیدتر RSS
    candidates = candidates[:20]

    published_count = 0

    for news in candidates:

        if published_count >= MAX_NEWS_PER_RUN:
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

        # فاصله بسیار کوتاه بین پست‌ها
        time.sleep(1)

    elapsed = time.monotonic() - start_time

    log.info("")
    log.info("====================================")
    log.info(
        f"FINISHED - Published: {published_count}"
    )
    log.info(
        f"Runtime: {elapsed:.1f}s"
    )
    log.info("====================================")


if __name__ == "__main__":
    main()
