"""Free direct RSS sources for international news.

This module intentionally does not replace the v11 pipeline. It adds
established publisher RSS feeds and applies a focused global/breaking-news
priority layer so major international events can compete with the much
larger domestic candidate pool.
"""

import main


FOREIGN_RSS_FEEDS = [
    ("جهان", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("جهان", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("جهان", "https://rss.dw.com/rdf/rss-en-all"),
    ("جهان", "https://www.france24.com/en/rss"),
    ("جهان", "https://www.theguardian.com/world/rss"),
    ("جهان", "https://www.euronews.com/rss?level=theme&name=news"),
]


FOREIGN_DIRECT_HOSTS = {
    "bbc.com",
    "aljazeera.com",
    "dw.com",
    "france24.com",
    "theguardian.com",
    "euronews.com",
}


for feed in FOREIGN_RSS_FEEDS:
    if feed not in main.DIRECT_RSS_FEEDS:
        main.DIRECT_RSS_FEEDS.append(feed)


# Keep the existing v11 scoring intact, but make established foreign
# reporting competitive with the much larger domestic candidate pool.
_ORIGINAL_SOURCE_PRIORITY = main.source_priority


def _is_foreign_host(url):
    host = main.base_domain(
        main.get_hostname(url)
    )

    if not host:
        return False

    return any(
        host == domain or host.endswith("." + domain)
        for domain in FOREIGN_DIRECT_HOSTS
    )


def source_priority(url, is_google=False):
    score = _ORIGINAL_SOURCE_PRIORITY(
        url,
        is_google=is_google,
    )

    if not is_google and _is_foreign_host(url):
        score += 20

    return score


main.source_priority = source_priority


# Global breaking-news signals. These are deliberately conservative:
# they raise genuinely important events rather than forcing every foreign
# article into the top four.
BREAKING_KEYWORDS = [
    "breaking",
    "خبر فوری",
    "فوری",
    "urgent",
    "developing",
    "هشدار",
    "alert",
    "emergency",
    "انفجار",
    "حمله",
    "حمله موشکی",
    "موشک",
    "جنگ",
    "درگیری",
    "نبرد",
    "حمله هوایی",
    "حمله پهپادی",
    "حمله پهپاد",
    "حمله زمینی",
    "آتش بس",
    "آتش‌بس",
    "ترور",
    "کشته",
    "تلفات",
    "سقوط هواپیما",
]


GEOPOLITICAL_KEYWORDS = [
    "جنگ",
    "درگیری",
    "نبرد",
    "حمله",
    "موشک",
    "پهپاد",
    "ناتو",
    "تحریم",
    "هسته ای",
    "هسته‌ای",
    "مذاکرات",
    "آتش بس",
    "آتش‌بس",
    "کاخ سفید",
    "پنتاگون",
    "کرملین",
    "سازمان ملل",
    "اسرائیل",
    "ایران",
    "روسیه",
    "اوکراین",
    "غزه",
    "لبنان",
    "سوریه",
    "یمن",
    "تایوان",
    "چین",
]


MAJOR_WORLD_KEYWORDS = [
    "president",
    "prime minister",
    "presidential",
    "election",
    "sanctions",
    "nuclear",
    "ceasefire",
    "iran",
    "israel",
    "russia",
    "ukraine",
    "gaza",
    "lebanon",
    "syria",
    "yemen",
    "taiwan",
    "china",
    "امریکا",
    "آمریکا",
    "اروپا",
    "رئیس جمهور",
    "نخست وزیر",
    "انتخابات",
    "تحریم",
    "هسته ای",
    "هسته‌ای",
]


# These are publication-format/meta-news titles, not individual events.
# They must not occupy a news slot even when their publisher is trusted.
BULLETIN_KEYWORDS = [
    "latest news bulletin",
    "news bulletin",
    "midday bulletin",
    "morning bulletin",
    "evening bulletin",
    "daily bulletin",
    "news roundup",
    "news round-up",
    "daily brief",
    "morning brief",
    "evening brief",
    "midday brief",
    "top stories",
    "latest news roundup",
    "بولتن خبری",
    "بولتن نیمروز",
    "بولتن صبح",
    "بولتن عصر",
    "مرور اخبار",
    "مروری بر اخبار",
    "مهم ترین اخبار",
    "مهم‌ترین اخبار",
    "آخرین اخبار جهان",
]


def _is_bulletin_title(title):
    text = str(title or "").strip().lower()
    if not text:
        return False

    return any(keyword in text for keyword in BULLETIN_KEYWORDS)


def _keyword_hits(text, keywords):
    text = str(text or "").lower()
    return sum(1 for word in keywords if word.lower() in text)


_ORIGINAL_CALCULATE_IMPORTANCE = main.calculate_importance


def calculate_importance(candidate):
    score = _ORIGINAL_CALCULATE_IMPORTANCE(candidate)

    title = candidate.get("title", "")
    body = candidate.get("summary", "")
    text = f"{title} {body}"

    # Never let a bulletin/roundup consume one of the limited publication
    # slots. This is intentionally title-based so real event articles from
    # the same trusted publishers remain unaffected.
    if _is_bulletin_title(title):
        return -1000

    breaking_hits = _keyword_hits(
        text,
        BREAKING_KEYWORDS,
    )

    geopolitical_hits = _keyword_hits(
        text,
        GEOPOLITICAL_KEYWORDS,
    )

    major_world_hits = _keyword_hits(
        text,
        MAJOR_WORLD_KEYWORDS,
    )

    # Strong but capped event boost: breaking/conflict stories first,
    # followed by major geopolitical developments.
    if breaking_hits:
        score += min(breaking_hits, 2) * 14

    if geopolitical_hits:
        score += min(geopolitical_hits, 3) * 6

    if major_world_hits:
        score += min(major_world_hits, 2) * 3

    # Google News items are resolved to the original publisher when
    # possible. Give a trusted foreign publisher the same source advantage
    # even when discovery started through Google News.
    resolved = candidate.get("resolved_link", "")
    if _is_foreign_host(resolved):
        score += 12

    return score


main.calculate_importance = calculate_importance


print(
    f"Foreign direct RSS: enabled ({len(FOREIGN_RSS_FEEDS)} sources); "
    "foreign source boost: +20; breaking/global priority: enabled; "
    "bulletin filter: enabled"
)
