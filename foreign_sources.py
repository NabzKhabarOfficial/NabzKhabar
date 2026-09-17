"""Free direct RSS sources and focused international-news safeguards."""

import re
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
    "bbc.com", "aljazeera.com", "dw.com", "france24.com",
    "theguardian.com", "euronews.com",
}

for feed in FOREIGN_RSS_FEEDS:
    if feed not in main.DIRECT_RSS_FEEDS:
        main.DIRECT_RSS_FEEDS.append(feed)


# ------------------------------------------------------------
# Foreign source priority
# ------------------------------------------------------------
_ORIGINAL_SOURCE_PRIORITY = main.source_priority


def _is_foreign_host(url):
    host = main.base_domain(main.get_hostname(url))
    if not host:
        return False
    return any(host == d or host.endswith("." + d) for d in FOREIGN_DIRECT_HOSTS)


def source_priority(url, is_google=False):
    score = _ORIGINAL_SOURCE_PRIORITY(url, is_google=is_google)
    if not is_google and _is_foreign_host(url):
        score += 20
    return score

main.source_priority = source_priority


# ------------------------------------------------------------
# Global / breaking-news priority
# ------------------------------------------------------------
BREAKING_KEYWORDS = [
    "breaking", "خبر فوری", "فوری", "urgent", "developing", "هشدار",
    "alert", "emergency", "انفجار", "حمله", "حمله موشکی", "موشک",
    "جنگ", "درگیری", "نبرد", "حمله هوایی", "حمله پهپادی",
    "حمله پهپاد", "حمله زمینی", "آتش بس", "آتش‌بس", "ترور",
    "کشته", "تلفات", "سقوط هواپیما",
]

GEOPOLITICAL_KEYWORDS = [
    "جنگ", "درگیری", "نبرد", "حمله", "موشک", "پهپاد", "ناتو",
    "تحریم", "هسته ای", "هسته‌ای", "مذاکرات", "آتش بس", "آتش‌بس",
    "کاخ سفید", "پنتاگون", "کرملین", "سازمان ملل", "اسرائیل", "ایران",
    "روسیه", "اوکراین", "غزه", "لبنان", "سوریه", "یمن", "تایوان", "چین",
]

MAJOR_WORLD_KEYWORDS = [
    "president", "prime minister", "presidential", "election", "sanctions",
    "nuclear", "ceasefire", "iran", "israel", "russia", "ukraine",
    "gaza", "lebanon", "syria", "yemen", "taiwan", "china",
    "امریکا", "آمریکا", "اروپا", "رئیس جمهور", "نخست وزیر", "انتخابات",
    "تحریم", "هسته ای", "هسته‌ای",
]


# ------------------------------------------------------------
# Bulletin / roundup filter
# ------------------------------------------------------------
BULLETIN_KEYWORDS = [
    "latest news bulletin", "news bulletin", "midday bulletin",
    "morning bulletin", "evening bulletin", "daily bulletin",
    "news roundup", "news round-up", "daily brief", "morning brief",
    "evening brief", "midday brief", "top stories", "latest news roundup",
    "بولتن خبری", "بولتن نیمروز", "بولتن صبح", "بولتن عصر",
    "مرور اخبار", "مروری بر اخبار", "مهم ترین اخبار", "مهم‌ترین اخبار",
    "آخرین اخبار جهان",
]


def _is_bulletin_title(title):
    text = str(title or "").strip().lower()
    return bool(text) and any(k in text for k in BULLETIN_KEYWORDS)


def _keyword_hits(text, keywords):
    text = str(text or "").lower()
    return sum(1 for word in keywords if word.lower() in text)


_ORIGINAL_CALCULATE_IMPORTANCE = main.calculate_importance


def calculate_importance(candidate):
    score = _ORIGINAL_CALCULATE_IMPORTANCE(candidate)
    title = candidate.get("title", "")
    body = candidate.get("summary", "")
    text = f"{title} {body}"

    if _is_bulletin_title(title):
        return -1000

    score += min(_keyword_hits(text, BREAKING_KEYWORDS), 2) * 14
    score += min(_keyword_hits(text, GEOPOLITICAL_KEYWORDS), 3) * 6
    score += min(_keyword_hits(text, MAJOR_WORLD_KEYWORDS), 2) * 3

    if _is_foreign_host(candidate.get("resolved_link", "")):
        score += 12

    return score

main.calculate_importance = calculate_importance


# ------------------------------------------------------------
# Stronger cross-source story identity
# ------------------------------------------------------------
# The existing v11 semantic matcher is preserved first. This additional
# normalization fixes common Persian variants such as "ناو های" vs "ناوهای"
# and makes paraphrases from different publishers converge more reliably.
_ORIGINAL_SAME_STORY = main.same_story


def _canonical_story_tokens(title):
    text = str(title or "")
    text = text.replace("\u200c", "")
    text = text.replace("ي", "ی").replace("ك", "ک")
    text = text.replace("ۀ", "ه").replace("ة", "ه")
    text = text.lower()
    text = re.sub(r"\s+(ها|های)\b", r"\1", text)
    text = re.sub(r"[^\w\u0600-\u06ff]+", " ", text)
    tokens = set(text.split())
    stop = getattr(main, "STOPWORDS", set())
    generic = getattr(main, "GENERIC_NEWS_WORDS", set())
    return {x for x in tokens if len(x) >= 2 and x not in stop and x not in generic}


def same_story(a, b):
    if _ORIGINAL_SAME_STORY(a, b):
        return True

    A = _canonical_story_tokens(a.get("title", ""))
    B = _canonical_story_tokens(b.get("title", ""))

    if not A or not B:
        return False

    common = A & B
    if len(common) < 5:
        return False

    containment = len(common) / min(len(A), len(B))
    jaccard = len(common) / len(A | B)

    # Conservative threshold: catches near-identical/paraphrased reports,
    # while avoiding broad stories that merely share a country/topic.
    return containment >= 0.75 and jaccard >= 0.55

main.same_story = same_story


# ------------------------------------------------------------
# Persian-only publication guard for foreign articles
# ------------------------------------------------------------
_ORIGINAL_GEMINI_REQUEST = main.gemini_request


def _latin_count(text):
    return len(re.findall(r"[A-Za-z]", str(text or "")))


def _persian_count(text):
    return len(re.findall(r"[\u0600-\u06ff]", str(text or "")))


def _is_english_heavy(text):
    latin = _latin_count(text)
    persian = _persian_count(text)
    return latin >= 10 and persian < max(4, int(latin * 0.15))


def gemini_request(title, article_text):
    result = _ORIGINAL_GEMINI_REQUEST(title, article_text)

    if not result:
        return result

    result_title = result.get("title", "")
    result_summary = result.get("summary", "")

    if not (_is_english_heavy(result_title) or _is_english_heavy(result_summary)):
        return result

    # One free retry with an explicit Persian-only instruction embedded in
    # the model input. This fixes foreign RSS items whose first generation
    # accidentally copied the English source wording.
    retry_title = (
        "فقط فارسی بنویس. هیچ کلمه یا جمله انگلیسی در خروجی ننویس. "
        "این خبر را دقیق و حرفه‌ای به فارسی ترجمه و خلاصه کن.\n"
        + str(title or "")
    )

    retry = _ORIGINAL_GEMINI_REQUEST(retry_title, article_text)

    if not retry:
        return result

    retry_title_text = retry.get("title", "")
    retry_summary_text = retry.get("summary", "")

    if _is_english_heavy(retry_title_text) or _is_english_heavy(retry_summary_text):
        print("SKIPPED ENGLISH OUTPUT: Gemini could not produce Persian text")
        return None

    return retry

main.gemini_request = gemini_request


print(
    f"Foreign direct RSS: enabled ({len(FOREIGN_RSS_FEEDS)} sources); "
    "foreign source boost: +20; breaking/global priority: enabled; "
    "bulletin filter: enabled; stronger semantic dedup: enabled; "
    "Persian-only foreign output: enabled"
)
