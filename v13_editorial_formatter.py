"""NABZ V13 — final Telegram editorial formatter.

Turns already-generated title/summary into a short, mobile-first news post.
This layer is deterministic: it does not invent facts and never calls a paid
service. It removes page chrome/bylines and refuses visibly incomplete text.
"""

import re

CHANNEL_URL = "https://t.me/NabzKhabarOfficial"

BYLINE_PREFIXES = (
    "مینا عظیمی", "کیمیا قلی پور", "کیمیا قلی‌پور", "مرتضی قانع",
    "به گزارش خبرنگار", "به گزارش خبرنگار مهر", "به گزارش خبرنگار ایسنا",
    "به گزارش خبرنگار ایرنا", "به گزارش خبرنگار باشگاه خبرنگاران جوان",
)

CHROME_PATTERNS = (
    r"منبع\s*تصویر\s*[,：:]?.*?(?=عنوان|منتشر شده|به روز|به‌روز|$)",
    r"عنوان\s*[:：]?\s*",
    r"منتشر\s*شده\s+[^،.]{0,120}(?:،|\.)?",
    r"به\s*روز\s*رسانی\s+[^،.]{0,120}(?:،|\.)?",
    r"بست\s+به\s+روز\s+[^،.]{0,120}(?:،|\.)?",
    r"منبع\s*تصویر\s*[,：:]?.*$",
)


def _clean(value):
    value = str(value or "")
    value = value.replace("\u200c", " ").replace("\u200f", " ")
    value = re.sub(r"https?://\S+|www\.\S+", " ", value, flags=re.I)
    for pattern in CHROME_PATTERNS:
        value = re.sub(pattern, " ", value, flags=re.I)
    for prefix in BYLINE_PREFIXES:
        value = re.sub(r"^\s*" + re.escape(prefix) + r"\s*[-–—:،]?\s*", "", value, flags=re.I)
    value = re.sub(r"\s+#?[A-Za-z0-9_]+\s*$", "", value)
    value = re.sub(r"\s{2,}", " ", value).strip()
    return value


def _sentences(text):
    text = _clean(text)
    if not text:
        return []
    parts = re.split(r"(?<=[.!؟؛])\s+", text)
    return [p.strip(" -–—") for p in parts if p.strip(" -–—")]


def _is_incomplete(text):
    value = str(text or "").strip()
    if not value:
        return True
    if value.endswith(("…", "...", "….", "،", ":", "؛", "و", "اما", "که", "در", "برای")):
        return True
    # Obvious webpage truncation markers.
    if re.search(r"(?:ادامه دارد|ادامه…|در سطوح)$", value, flags=re.I):
        return True
    return False


def format_title(title):
    value = _clean(title)
    value = re.sub(r"^📰\s*", "", value)
    value = re.sub(r"\s*\+\s*(?:فیلم|ویدئو|ویدیو|عکس|تصاویر)\s*$", "", value, flags=re.I)
    return value[:180].strip(" -–—")


def format_body(body, max_sentences=4, max_chars=850):
    sentences = _sentences(body)
    if not sentences:
        return ""

    selected = []
    for sentence in sentences:
        if _is_incomplete(sentence):
            continue
        candidate = " ".join(selected + [sentence])
        if len(candidate) > max_chars:
            break
        selected.append(sentence)
        if len(selected) >= max_sentences:
            break

    result = " ".join(selected).strip()
    if not result or _is_incomplete(result):
        return ""
    return result


def build_caption(title, body):
    title = format_title(title)
    body = format_body(body)
    if not title or not body:
        return ""
    return "\n\n".join([
        f"📰 {title}",
        body,
        "#نبض_خبر",
        f"🔗 کانال نبض خبر: {CHANNEL_URL}",
    ])


def install(core):
    original_build_caption = core.build_caption

    def editorial_caption(title, body):
        value = build_caption(title, body)
        if value:
            return value
        # Never manufacture a news post from incomplete content. Returning the
        # existing formatter output keeps non-news auxiliary posts compatible.
        return original_build_caption(title, body)

    core.build_caption = editorial_caption
    print("V13 EDITORIAL FORMATTER ACTIVE: mobile-first final news formatting enabled.")
