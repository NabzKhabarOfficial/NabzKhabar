import re

import main
import graphics_patch


# Keep v11 as the core. This wrapper only cleans publisher-page UI noise,
# supplies the headline to the local graphics layer, and applies the
# channel footer requested for published news captions.
_ORIGINAL_CLEAN_CONTENT = main.clean_content
_ORIGINAL_CLEAN_TITLE = main.clean_title
_ORIGINAL_PROCESS_NEWS = main.process_news
_ORIGINAL_BUILD_CAPTION = main.build_caption

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


def build_caption(title, body):
    caption = _ORIGINAL_BUILD_CAPTION(title, body)
    return caption.replace("#نبض_خبر", "@NabzKhabarOfficial")


def process_news(candidate, hash_history, title_history):
    main.CURRENT_GRAPHICS_TITLE = candidate.get("title", "")
    try:
        return _ORIGINAL_PROCESS_NEWS(candidate, hash_history, title_history)
    finally:
        main.CURRENT_GRAPHICS_TITLE = ""


main.clean_content = clean_content
main.clean_title = clean_title
main.build_caption = build_caption
main.process_news = process_news


if __name__ == "__main__":
    main.main()
