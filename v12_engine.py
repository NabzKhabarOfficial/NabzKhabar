import re

import main


# ============================================================
# NABZ KHABAR v12 EXPERIMENT
# Source expansion + strict AI safety + cleaner selection.
# This module is intentionally isolated so main v11 can be restored
# by switching back to main without touching the stable core.
# ============================================================


# ---------- Source layer ----------
# Keep YJC and Digiato for Iranian/local coverage. Replace the older
# IRNA/ISNA/Mehr/Zoomit direct feeds with free public RSS feeds from
# established international publishers.
V12_DIRECT_RSS_FEEDS = [
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

main.DIRECT_RSS_FEEDS = V12_DIRECT_RSS_FEEDS

# Give the new direct publishers a first-class quality score.
for _host in (
    "bbc.com",
    "bbc.co.uk",
    "theguardian.com",
    "npr.org",
    "techcrunch.com",
    "arstechnica.com",
    "wired.com",
    "theverge.com",
):
    main.HIGH_QUALITY_HOSTS.add(_host)


# ---------- Roundup / digest safety ----------
_ORIGINAL_ROUNDUP = main.is_roundup_title


def _v12_roundup(title):
    title = re.sub(r"\s+", " ", str(title or "")).strip()
    if not title:
        return False

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
        r"today'?s\s+(?:top|latest)\s+stories",
        r"top\s+stories\s+(?:today|this\s+week)",
        r"weekly\s+(?:roundup|recap|review)",
        r"news\s+roundup",
        r"week\s+in\s+(?:review|news)",
    ]
    if any(re.search(p, title, re.I) for p in patterns):
        return True

    if re.search(r"\bاز\b.+\bتا\b", title):
        if re.search(r"(?:نامه|اخبار|واکنش|رویداد|حاشیه|اظهارات|گزارش|بازیگران|خوانندگان)", title, re.I):
            return True

    return False


def is_roundup_title(title):
    return bool(_ORIGINAL_ROUNDUP(title) or _v12_roundup(title))


main.is_roundup_title = is_roundup_title


# ---------- Fact-safety for AI rewriting ----------
_ORIGINAL_GEMINI = main.gemini_request


def _nums(text):
    text = main.normalize_digits(str(text or ""))
    return set(re.findall(r"\b\d+(?:[.,]\d+)?\b", text))


def _has_bad_meta(text):
    t = str(text or "")
    bad = (
        "http://", "https://", "www.", "به گزارش", "منبع:",
        "طبق گزارش ما", "به گفته منابع ما"
    )
    return any(x.lower() in t.lower() for x in bad)


def _sentence_count(text):
    return len([x for x in re.split(r"(?<=[.!؟؛])\s+", str(text or "").strip()) if x.strip()])


def _v12_gemini(title, article_text):
    result = _ORIGINAL_GEMINI(title, article_text)
    if not result:
        return None

    out_title = main.clean_title(result.get("title", ""))
    out_summary = main.clean_content(result.get("summary", ""))
    source = main.clean_content(article_text or title)

    # Never allow the model to introduce numbers that do not exist in the
    # supplied source. This catches many of the most damaging hallucinations.
    source_nums = _nums(source)
    out_nums = _nums(out_title + " " + out_summary)
    if not out_nums.issubset(source_nums):
        print("V12 AI GUARD: new numeric fact detected; using source-faithful fallback")
        return main.local_news_engine(title, source)

    # No links, source labels, or reporting boilerplate in the published text.
    if _has_bad_meta(out_title) or _has_bad_meta(out_summary):
        print("V12 AI GUARD: metadata/source boilerplate detected")
        return main.local_news_engine(title, source)

    # Keep the AI concise. If it escapes the requested format, use the safe
    # extractive engine rather than truncating a possibly broken sentence.
    if _sentence_count(out_summary) > 3 or len(out_summary) > 850:
        print("V12 AI GUARD: oversized summary")
        return main.local_news_engine(title, source)

    if not out_title or len(out_title) < 8:
        return main.local_news_engine(title, source)

    # If source and generated title are both Persian, require meaningful
    # lexical overlap. This prevents dramatic title drift such as changing
    # the actual team/person/event while still allowing harmless wording edits.
    source_is_persian = bool(re.search(r"[\u0600-\u06ff]", str(title)) and re.search(r"[\u0600-\u06ff]", str(article_text)))
    out_is_persian = bool(re.search(r"[\u0600-\u06ff]", out_title))

    if source_is_persian and out_is_persian:
        def toks(x):
            return {
                t for t in re.findall(r"[\u0600-\u06ffA-Za-z0-9]+", main.normalize_digits(str(x or "")).lower())
                if len(t) >= 3 and t not in main.STOPWORDS and t not in main.GENERIC_NEWS_WORDS
            }

        source_tokens = toks(title + " " + article_text[:3000])
        title_tokens = toks(out_title)
        overlap = len(source_tokens & title_tokens)
        if title_tokens and overlap < max(1, min(3, len(title_tokens) // 2)):
            print("V12 AI GUARD: title drift detected; keeping source headline")
            out_title = main.clean_title(title)

    return {
        "title": out_title,
        "summary": out_summary,
    }


main.gemini_request = _v12_gemini


print("NABZ KHABAR v12 EXPERIMENT ACTIVE")
print(f"V12 direct RSS sources: {len(V12_DIRECT_RSS_FEEDS)}")
print("V12 AI fact-safety guard: ON")
print("V12 roundup filter: ON")
