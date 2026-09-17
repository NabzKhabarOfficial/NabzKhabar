import re

import main
import graphics_patch


# Keep v11 as the core. This wrapper cleans publisher-page UI noise,
# keeps the channel branding, and makes the AI-timeout fallback strictly
# extractive so it cannot invent facts when Gemini is unavailable.
_ORIGINAL_CLEAN_CONTENT = main.clean_content
_ORIGINAL_CLEAN_TITLE = main.clean_title
_ORIGINAL_SEND_MESSAGE = main.send_message
_ORIGINAL_SEND_PHOTO = main.send_photo
_ORIGINAL_SEND_VIDEO = main.send_video
_ORIGINAL_LOCAL_NEWS_ENGINE = main.local_news_engine
_ORIGINAL_IS_ROUNDUP_TITLE = main.is_roundup_title

SITE_CHROME_PATTERNS = [
    r"فیلم\s*>>\s*[^\s|]+",
    r"ویدئو\s*>>\s*[^\s|]+",
    r"ویدیو\s*>>\s*[^\s|]+",
    r"تعداد\s*بازدید\s*:\s*\d+",
    r"کد\s*ویدیو",
    r"دانلود\s*ویدیو",
    r"فیلم\s*اصلی",
    r"ویدئوی\s*اصلی",
    r"ویدیوی\s*اصلی",
    r"کیفیت\s*\d{2,4}",
    r"کد\s*خبر\s*:\s*[\d۰-۹]+",
    r"\b[\d۰-۹]+\s*بازدید\b",
    r"تاریخ\s*انتشار\s*:\s*[^|\n]+\|\s*[\d۰-۹]{4}/[\d۰-۹]{1,2}/[\d۰-۹]{1,2}",
    r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b",
]


def _strip_site_chrome(text):
    if not text:
        return ""

    text = str(text)

    for pattern in SITE_CHROME_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.I)

    text = re.sub(r"(?<=[\u0600-\u06ff])(?:فیلم|ویدئو|ویدیو)\s*>>", " ", text)
    text = re.sub(r"\s*[|｜]\s*", " ", text)
    text = re.sub(r"\s{2,}", " ", text)

    return text.strip()


def clean_content(text):
    return _strip_site_chrome(_ORIGINAL_CLEAN_CONTENT(text))[:6000]


def clean_title(title):
    cleaned = _ORIGINAL_CLEAN_TITLE(title)
    cleaned = _strip_site_chrome(cleaned)
    cleaned = re.sub(r"(?:فیلم|ویدئو|ویدیو)\s*$", "", cleaned, flags=re.I)
    return re.sub(r"\s{2,}", " ", cleaned).strip()[:180]


def _safe_extractive_local_engine(title, body):
    """Fallback used only when Gemini fails. Never invents facts."""
    title = clean_title(title)
    body = clean_content(body)

    # Remove publisher-style lead-ins and keep only source sentences.
    sentences = re.split(r"(?<=[.!؟])\s+|(?<=[\u06d4])\s+", body)
    sentences = [s.strip(" \t\n-") for s in sentences if len(s.strip()) >= 35]

    summary = " ".join(sentences[:3]).strip()
    if len(summary) > 850:
        summary = summary[:850].rsplit(" ", 1)[0] + "…"

    if not summary:
        summary = body[:850].strip()

    # Conservative headline: keep the factual lead, drop promotional
    # clauses after a semicolon/colon when the fallback has no AI fact check.
    factual_title = re.split(r"[؛;:]", title, maxsplit=1)[0].strip()
    if len(factual_title) >= 12:
        title = factual_title

    print("SAFE EXTRACTIVE FALLBACK: Gemini unavailable; source text only")
    return {
        "title": title,
        "summary": summary,
    }


def _channel_caption(caption):
    """Use the channel handle instead of the old hashtag."""
    if not caption:
        return caption
    return str(caption).replace("#نبض_خبر", "@NabzKhabarOfficial")


def _is_roundup_or_digest_title(title):
    """Reject weekly/digest/roundup headlines before they reach scoring."""
    title = re.sub(r"\s+", " ", str(title or "")).strip()
    if not title:
        return False

    # Generic recap/digest wording that should never become a standalone post.
    patterns = [
        r"مروری?\s+بر",
        r"مرور\s+(?:مهمترین|مهم‌ترین|اخبار|رویداد)",
        r"مهمترین\s+اخبار\s+(?:هفته|روز|امروز)",
        r"مهم‌ترین\s+اخبار\s+(?:هفته|روز|امروز)",
        r"اخبار\s+(?:مهم|منتخب|برگزیده)\s+(?:هفته|روز|امروز)",
        r"گزیده\s+اخبار",
        r"جمع[‌ ]بندی\s+اخبار",
        r"بسته\s+خبری",
        r"مرور\s+هفتگی",
        r"اخبار\s+هفته",
        r"در\s+هفته(?:‌|\s)+ای\s+که\s+گذشت",
        r"در\s+هفته\s+گذشته",
        r"این\s+هفته\s+(?:چه|مهم|اخبار)",
    ]

    if any(re.search(pattern, title, flags=re.I) for pattern in patterns):
        return True

    # Common roundup headline form: "از X تا Y" when it also contains
    # a multi-item marker such as نامه/اخبار/واکنش/رویداد.
    if re.search(r"\bاز\b.+\bتا\b", title):
        if re.search(
            r"(?:نامه|اخبار|واکنش|رویداد|حاشیه|اظهارات|گزارش|بازیگران|خوانندگان)",
            title,
            flags=re.I,
        ):
            return True

    return False


def is_roundup_title(title):
    return (
        _ORIGINAL_IS_ROUNDUP_TITLE(title)
        or _is_roundup_or_digest_title(title)
    )


def send_message(text):
    return _ORIGINAL_SEND_MESSAGE(_channel_caption(text))


def send_photo(path, caption):
    return _ORIGINAL_SEND_PHOTO(path, _channel_caption(caption))


def send_video(path, caption):
    return _ORIGINAL_SEND_VIDEO(path, _channel_caption(caption))


# Monkey-patch only the functions used by the unchanged v11 core.
main.clean_content = clean_content
main.clean_title = clean_title
main.is_roundup_title = is_roundup_title
main.local_news_engine = _safe_extractive_local_engine
main.send_message = send_message
main.send_photo = send_photo
main.send_video = send_video


if __name__ == "__main__":
    main.main()