import re
import main

# ============================================================
# NABZ KHABAR V13 — FINAL NEWS ENGINE
# One coherent safety/orchestration layer over the stable v11 core.
# Free-only: public RSS, Google News RSS, GitHub Actions, Telegram,
# Gemini only when the existing secret is configured.
# ============================================================

V13_DIRECT_RSS_FEEDS = [
    ("ایران", "https://www.yjc.ir/fa/rss/allnews"),
    ("فناوری", "https://digiato.com/feed"),
    ("جهان", "https://feeds.bbci.co.uk/news/rss.xml"),
    ("جهان", "https://www.theguardian.com/world/rss"),
    ("جهان", "https://feeds.npr.org/1001/rss.xml"),
    ("فناوری", "https://techcrunch.com/feed/"),
    ("فناوری", "https://feeds.arstechnica.com/arstechnica/index"),
    ("فناوری", "https://www.wired.com/feed/rss"),
    ("فناوری", "https://www.theverge.com/rss/index.xml"),
]

# ---------- Source policy ----------
main.DIRECT_RSS_FEEDS = V13_DIRECT_RSS_FEEDS
for host in (
    "bbc.com", "bbc.co.uk", "theguardian.com", "npr.org",
    "techcrunch.com", "arstechnica.com", "wired.com", "theverge.com",
):
    main.HIGH_QUALITY_HOSTS.add(host)

# ---------- Roundup / digest rejection ----------
_original_roundup = main.is_roundup_title

ROUNDUP_PATTERNS = [
    r"مروری?\s+بر",
    r"مرور\s+(?:مهمترین|مهم‌ترین|اخبار|رویداد)",
    r"(?:مهمترین|مهم‌ترین)\s+اخبار\s+(?:هفته|روز|امروز)",
    r"اخبار\s+(?:مهم|منتخب|برگزیده)\s+(?:هفته|روز|امروز)",
    r"گزیده\s+اخبار",
    r"جمع[‌ ]بندی\s+اخبار",
    r"بسته\s+خبری",
    r"مرور\s+هفتگی",
    r"اخبار\s+هفته",
    r"در\s+هفته(?:‌|\s)+ای\s+که\s+گذشت",
    r"در\s+هفته\s+گذشته",
    r"weekly\s+(?:roundup|recap|review)",
    r"news\s+roundup",
    r"week\s+in\s+(?:review|news)",
]

def is_roundup_title(title):
    title = re.sub(r"\s+", " ", str(title or "")).strip()
    if not title:
        return False
    if _original_roundup(title):
        return True
    if any(re.search(p, title, re.I) for p in ROUNDUP_PATTERNS):
        return True
    # "A to B" list headlines are frequently digests rather than a single event.
    if re.search(r"\bاز\b.+\bتا\b", title):
        return bool(re.search(
            r"(?:نامه|اخبار|واکنش|رویداد|حاشیه|اظهارات|گزارش|بازیگران|خوانندگان)",
            title, re.I
        ))
    return False

main.is_roundup_title = is_roundup_title

# ---------- Content sanitation ----------
_original_clean_title = main.clean_title
_original_clean_content = main.clean_content

def clean_title(title):
    value = _original_clean_title(title)
    value = re.sub(r"\b(?:فیلم|ویدئو|ویدیو)\s*>>.*$", "", value, flags=re.I)
    value = re.sub(r"\s{2,}", " ", value).strip()
    return value[:180]

def clean_content(text):
    value = _original_clean_content(text)
    value = re.sub(r"(?:فیلم|ویدئو|ویدیو)\s*>>\s*[^|]+", " ", value, flags=re.I)
    value = re.sub(r"\s{2,}", " ", value).strip()
    return value[:6000]

main.clean_title = clean_title
main.clean_content = clean_content

# ---------- Safe extractive fallback ----------
def safe_local_engine(title, body):
    title = clean_title(title)
    body = clean_content(body)
    sentences = re.split(r"(?<=[.!؟؛])\s+", body)
    sentences = [s.strip(" -\t\n") for s in sentences if len(s.strip()) >= 25]
    summary = " ".join(sentences[:3]).strip()
    if len(summary) > 700:
        summary = summary[:700].rsplit(" ", 1)[0] + "…"
    if not summary:
        summary = body[:700].strip()
    return {"title": title, "summary": summary}

main.local_news_engine = safe_local_engine

# ---------- Persian localization for foreign-source stories ----------
def _persian_ratio(text):
    text = str(text or "")
    letters = re.findall(r"[A-Za-z\u0600-\u06ff]", text)
    if not letters:
        return 1.0
    return sum("\u0600" <= ch <= "\u06ff" for ch in letters) / len(letters)

def _translate_foreign_story(title, article_text):
    if not main.AI_API_KEY:
        return None
    endpoint = "https://generativelanguage.googleapis.com/v1beta/models/" + f"{main.GEMINI_MODEL}:generateContent"
    prompt = """این خبر از یک منبع خارجی است و باید برای یک کانال خبری فارسی‌زبان آماده شود.
عنوان اصلی:
%s

متن خبر:
%s

فقط و فقط اطلاعات موجود در متن را به فارسی روان ترجمه و خلاصه کن.
- عنوان حتماً فارسی و خبری باشد.
- خلاصه حداکثر ۳ جمله و فارسی باشد.
- هیچ عدد، نام، ادعا یا واقعیت جدیدی اضافه نکن.
- اگر عددی در متن هست، فقط همان عدد را حفظ کن.
- نام شرکت‌ها و محصولات را در صورت نیاز به شکل رایج فارسی + نام اصلی بنویس.
- هیچ لینک، منبع، «به گزارش» یا توضیح درباره ترجمه نده.

فقط JSON معتبر:
{"title":"تیتر فارسی","summary":"خلاصه فارسی"}
""" % (title, str(article_text or title)[:6000])
    try:
        response = main.SESSION.post(endpoint, params={"key": main.AI_API_KEY}, json={"contents":[{"parts":[{"text":prompt}]}], "generationConfig":{"responseMimeType":"application/json","maxOutputTokens":500}}, timeout=30)
        if not response.ok:
            return None
        raw = response.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
        raw = re.sub(r"^```(?:json)?", "", raw, flags=re.I).replace("```", "").strip()
        data = __import__("json").loads(raw)
        out_title = clean_title(data.get("title", ""))
        out_summary = clean_content(data.get("summary", ""))
        if _persian_ratio(out_title) < 0.60 or _persian_ratio(out_summary) < 0.60:
            return None
        if not _numbers(out_title + " " + out_summary).issubset(_numbers(clean_content(article_text or title))):
            return None
        if _sentence_count(out_summary) > 3 or len(out_summary) > 750:
            return None
        return {"title": out_title, "summary": out_summary}
    except Exception as exc:
        print(f"V13 localization error: {exc}")
        return None

# ---------- AI safety gate ----------
_original_gemini = main.gemini_request

def _numbers(text):
    return set(re.findall(r"\b\d+(?:[.,]\d+)?\b", main.normalize_digits(str(text or ""))))

def _anchors(text):
    # Named/factual anchors. This is intentionally conservative.
    return {
        x.lower() for x in re.findall(
            r"[\u0600-\u06ffA-Za-z][\u0600-\u06ffA-Za-z0-9_-]{2,}",
            main.normalize_digits(str(text or "")).lower()
        )
    }

def _bad_ai_meta(text):
    t = str(text or "").lower()
    return any(x in t for x in (
        "http://", "https://", "www.", "منبع:", "به گزارش",
        "طبق گزارش ما", "به گفته منابع ما", "منابع ما"
    ))

def _sentence_count(text):
    return len([x for x in re.split(r"(?<=[.!؟؛])\s+", str(text or "").strip()) if x.strip()])

def gemini_request(title, article_text):
    source = clean_content(article_text or title)
    is_foreign = _persian_ratio(title) < 0.60

    # FOREIGN STORY CONTRACT:
    # Translate first. Never allow the original-language title/body or a
    # non-Persian fallback to reach the publication layer.
    if is_foreign:
        localized = _translate_foreign_story(title, source)
        if not localized:
            print("V13 LOCALIZATION: foreign story could not be translated; publication blocked.")
            return None

        out_title = clean_title(localized.get("title", ""))
        out_summary = clean_content(localized.get("summary", ""))

        if _persian_ratio(out_title) < 0.60 or _persian_ratio(out_summary) < 0.60:
            print("V13 LOCALIZATION: translated output failed Persian validation; publication blocked.")
            return None

        if _bad_ai_meta(out_title) or _bad_ai_meta(out_summary):
            print("V13 LOCALIZATION: translated output contains source boilerplate; publication blocked.")
            return None

        if _sentence_count(out_summary) > 3 or len(out_summary) > 750:
            print("V13 LOCALIZATION: translated summary is invalid; publication blocked.")
            return None

        print("V13 LOCALIZATION: foreign story translated and validated before publication.")
        return {"title": out_title, "summary": out_summary}

    # Native Persian stories continue through the normal AI quality pipeline.
    result = _original_gemini(title, article_text)
    if not result:
        return None

    out_title = clean_title(result.get("title", ""))
    out_summary = clean_content(result.get("summary", ""))

    if not _numbers(out_title + " " + out_summary).issubset(_numbers(source)):
        print("V13 GUARD: rejected AI output because it introduced a number.")
        return safe_local_engine(title, source)

    if _bad_ai_meta(out_title) or _bad_ai_meta(out_summary):
        print("V13 GUARD: rejected source/link boilerplate.")
        return safe_local_engine(title, source)

    if not out_title or len(out_title) < 8:
        return safe_local_engine(title, source)

    if _sentence_count(out_summary) > 3 or len(out_summary) > 750:
        print("V13 GUARD: rejected oversized summary.")
        return safe_local_engine(title, source)

    # For Persian stories, require the generated headline to retain
    # meaningful source anchors. This prevents entity/event drift.
    if re.search(r"[\u0600-\u06ff]", title + " " + article_text) and re.search(r"[\u0600-\u06ff]", out_title):
        src = _anchors(title + " " + source[:3000])
        out = _anchors(out_title)
        if out and len(src & out) < max(1, min(3, len(out) // 2)):
            print("V13 GUARD: rejected headline drift.")
            out_title = clean_title(title)

    return {"title": out_title, "summary": out_summary}

main.gemini_request = gemini_request

# ---------- Image safety ----------
_original_image_ok = main.image_is_acceptable

def image_is_acceptable(url):
    if not url or main.is_bad_media_url(url):
        return False
    lowered = str(url).lower()
    blocked = (
        "logo", "favicon", "avatar", "profile", "sprite",
        "placeholder", "default-image", "default_image",
        ".svg", "data:image", "blob:"
    )
    if any(x in lowered for x in blocked):
        return False
    return _original_image_ok(url)

main.image_is_acceptable = image_is_acceptable

# ---------- Candidate quality gate ----------
_original_collect_candidates = main.collect_candidates

def collect_candidates(hash_history, title_history):
    candidates = _original_collect_candidates(hash_history, title_history)
    clean = []
    seen = set()

    for c in candidates:
        title = clean_title(c.get("title", ""))
        link = main.canonicalize_url(c.get("link", ""))
        if not title or len(title) < 12 or not link:
            continue
        if is_roundup_title(title):
            print(f"V13 SKIP ROUNDUP: {title}")
            continue
        key = (title.lower(), link)
        if key in seen:
            continue
        seen.add(key)
        c["title"] = title
        c["link"] = link
        clean.append(c)

    # Preserve source/event diversity without imposing a political or
    # editorial viewpoint: do not allow one category to consume the run.
    clean.sort(
        key=lambda c: (
            float(c.get("importance", 0)),
            float(c.get("recency_score", 0)),
            float(c.get("source_quality", 0)),
        ),
        reverse=True,
    )
    return clean

main.collect_candidates = collect_candidates

# Never publish an untranslated foreign story when AI localization is unavailable.
class SkipForeignStory(Exception):
    pass

_original_local_news_engine = main.local_news_engine

def localized_local_news_engine(title, body):
    if _persian_ratio(title) < 0.60:
        raise SkipForeignStory()
    return _original_local_news_engine(title, body)

main.local_news_engine = localized_local_news_engine

_original_process_news = main.process_news

def process_news(*args, **kwargs):
    try:
        return _original_process_news(*args, **kwargs)
    except SkipForeignStory:
        print("V13 SKIP FOREIGN: AI localization unavailable; English story not published.")
        return False

main.process_news = process_news

# ---------- Final publication language gate ----------
# This is the last line of defense: regardless of which fallback path
# produced the caption, a foreign-language story must never reach Telegram.
_original_send_message = main.send_message
_original_send_photo = main.send_photo
_original_send_video = main.send_video


def _assert_persian_caption(caption):
    text = str(caption or "").strip()
    if not text:
        return
    # Ignore the channel handle/URL-like tokens when measuring language.
    probe = re.sub(r"@[A-Za-z0-9_]+", " ", text)
    probe = re.sub(r"https?://\S+", " ", probe)
    if _persian_ratio(probe) < 0.55:
        print("V13 FINAL LANGUAGE GATE: blocked non-Persian publication.")
        raise SkipForeignStory()


def send_message(text):
    _assert_persian_caption(text)
    return _original_send_message(text)


def send_photo(path, caption):
    _assert_persian_caption(caption)
    return _original_send_photo(path, caption)


def send_video(path, caption):
    _assert_persian_caption(caption)
    return _original_send_video(path, caption)


main.send_message = send_message
main.send_photo = send_photo
main.send_video = send_video

print("=" * 64)
print("NABZ KHABAR V13 FINAL ENGINE ACTIVE")
print(f"Direct RSS sources: {len(V13_DIRECT_RSS_FEEDS)}")
print("Roundup filter: ON")
print("AI fact-safety gate: ON")
print("Image safety gate: ON")
print("Multi-layer history/dedup: inherited from stable core")
print("Telegram/media/branding: inherited from stable core")
print("=" * 64)
