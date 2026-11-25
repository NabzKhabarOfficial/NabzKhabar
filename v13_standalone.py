import os
import re
import io
import json
import time
import hashlib
import subprocess
from datetime import datetime, timezone, timedelta
from urllib.parse import (
    urlparse,
    quote_plus,
    urljoin,
    parse_qsl,
    urlencode,
    urlunparse,
)

import requests
from atomic_state import save_text as _atomic_save_text

import feedparser
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
from v13_text_core import (  # noqa: F401 - re-exported for the install() stack
    GENERIC_NEWS_WORDS,
    HIGH_QUALITY_HOSTS,
    IMPORTANT_KEYWORDS,
    IMPORTANT_NEWS_RESCUE_MAX_AGE_MINUTES,
    IMPORTANT_RESCUE_PATTERNS,
    MEDIUM_QUALITY_HOSTS,
    ROUNDUP_PATTERNS,
    SOURCE_PHRASES,
    STOPWORDS,
    TRACKING_PARAMETERS,
    VERY_IMPORTANT_KEYWORDS,
    _has_global_high_impact,
    _high_confidence_event_duplicate,
    _is_telemetry_or_tracking_url,
    _persian_ratio,
    base_domain,
    calculate_importance,
    calculate_keyword_importance,
    calculate_recency_score,
    canonicalize_url,
    clean_content,
    clean_title,
    clean_url,
    enforce_short_summary,
    get_hostname,
    history_contains_story,
    is_bad_media_url,
    is_fresh,
    is_google_host,
    is_hls_url,
    is_important_news_rescue_candidate,
    is_roundup_title,
    is_social_host,
    looks_like_video_url,
    media_consistent_text,
    normalize_digits,
    normalize_space,
    numeric_anchors,
    parse_entry_time,
    publisher_quality,
    record_semantic_history,
    same_story,
    sentence_score,
    source_priority,
    split_sentences,
    story_similarity,
    story_tokens,
    strip_unbacked_media_labels,
    title_similarity,
    title_tokens,
)

from PIL import Image, ImageDraw, ImageFont


# ============================================================
# NABZ KHABAR BOT v11
# STRONG SEMANTIC DEDUPLICATION
# GOOGLE NEWS DISCOVERY
# GEMINI + VIDEO + PHOTO + TEXT + WATERMARK
# ============================================================

print("=" * 64)
print("NABZ KHABAR BOT v11")
print("STRONG DUPLICATE PROTECTION + FRESH NEWS")
print("GEMINI + GOOGLE NEWS + VIDEO + PHOTO")
print("WATERMARK + SOURCE QUALITY")
print("=" * 64)


# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
AI_API_KEY = os.getenv("AI_API_KEY", "").strip()

CHANNEL_ID = "@NabzKhabarOfficial"

# Free-tier, high-volume model. Override with GEMINI_MODEL if needed.
# Google currently lists Gemini 3.1 Flash-Lite as free-of-charge on the
# standard Gemini API tier. Free tier is quota-limited, not literally unlimited.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

REQUEST_TIMEOUT = 12
ARTICLE_TIMEOUT = 8

MAX_VIDEO_MB = 49
MAX_IMAGE_MB = 12

# The normal publication freshness contract is 30 minutes. Critical-news
# rescue temporarily expands feed collection to 6 hours in the dedicated
# freshness-rescue layer; routine stories never use that wider window.
FEED_COLLECTION_WINDOW_MINUTES = 30

# Important stories may be older than the normal feed window when RSS delivery is delayed.
# Rescue only high-impact events; routine foreign-local stories remain blocked.
IMPORTANT_NEWS_RESCUE_MAX_AGE_MINUTES = 360

# Normal publication freshness is 30 minutes. Do not silently widen this
# value: delayed high-impact stories are handled only by v13_freshness_rescue.
MAX_NEWS_AGE_HOURS = 0.5

# Semantic duplicate protection window.
SEMANTIC_HISTORY_DAYS = 7

HISTORY_FILE = "sent_news.txt"
MAX_HASH_HISTORY = 5000

WATERMARK_TEXT = "نبض خبر | NABZ"

MAX_OUTPUT_IMAGE_WIDTH = 1600
MAX_OUTPUT_IMAGE_HEIGHT = 1600


# ============================================================
# VALIDATION
# ============================================================

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")

print(f"Gemini enabled: {bool(AI_API_KEY)}")
print(f"Gemini model: {GEMINI_MODEL}")
print(f"Freshness window: {MAX_NEWS_AGE_HOURS}h")
print(f"Important-news rescue window: {IMPORTANT_NEWS_RESCUE_MAX_AGE_MINUTES}m")
print(f"Feed discovery window: {FEED_COLLECTION_WINDOW_MINUTES}m")
print(f"Semantic history: {SEMANTIC_HISTORY_DAYS} days")


# ============================================================
# TEXT HELPERS
# ============================================================

GOOGLE_NEWS_BASE = "https://news.google.com/rss"
GOOGLE_HL = "fa"
GOOGLE_GL = "IR"
GOOGLE_CEID = "IR:fa"


def google_news_search_url(query):
    query = normalize_space(query)

    return (
        f"{GOOGLE_NEWS_BASE}/search?"
        f"q={quote_plus(query)}"
        f"&hl={GOOGLE_HL}"
        f"&gl={GOOGLE_GL}"
        f"&ceid={GOOGLE_CEID}"
        f"&when={FEED_COLLECTION_WINDOW_MINUTES}m"
    )


# ============================================================
# DIRECT RSS
# ============================================================

DIRECT_RSS_FEEDS = [
    # Iranian direct RSS: keep exactly two sources to reduce polling and
    # duplicate candidates while preserving broad domestic coverage.
    ("ایران", "https://www.yjc.ir/fa/rss/allnews"),
    ("ایران", "https://www.irna.ir/rss"),

    # International / specialist RSS sources remain available below.
    ("هوش مصنوعی", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("هوش مصنوعی", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ("فناوری", "https://feeds.arstechnica.com/arstechnica/technology-lab"),
    ("هوش مصنوعی", "https://www.technologyreview.com/topic/artificial-intelligence/feed/"),
    ("هوش مصنوعی", "https://venturebeat.com/category/ai/feed/"),
    ("هوش مصنوعی", "https://blogs.nvidia.com/feed/"),
    ("ورزش", "https://feeds.bbci.co.uk/sport/rss.xml"),
    ("ورزش", "https://www.espn.com/espn/rss/news"),
    ("جهان", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("فناوری", "https://www.engadget.com/rss.xml"),
]


# ============================================================
# GOOGLE NEWS DISCOVERY
# ============================================================

GOOGLE_NEWS_FEEDS = [
    # Core Iranian / breaking coverage
    ("ایران", google_news_search_url("ایران")),
    ("خبر فوری", google_news_search_url('"خبر فوری" ایران')),
    ("خبر مهم", google_news_search_url('"خبر مهم" ایران')),
    ("حوادث", google_news_search_url("حادثه انفجار تصادف سقوط آتش سوزی ایران")),
    ("اقتصاد", google_news_search_url("اقتصاد ایران")),
    ("بازار", google_news_search_url("دلار طلا سکه بورس ایران")),
    ("جنگ و بحران", google_news_search_url("جنگ بحران درگیری حمله آتش بس")),
    ("جهان", google_news_search_url("مهمترین اخبار جهان بین الملل")),
    ("ایران و جهان", google_news_search_url("ایران آمریکا اروپا روسیه چین اسرائیل")),
    ("جامعه", google_news_search_url("جامعه اجتماعی ایران")),
    ("سلامت", google_news_search_url("سلامت پزشکی بیمارستان دارو")),
    ("علم", google_news_search_url("علم دانش پژوهش فضا پزشکی")),
    ("فرهنگ", google_news_search_url("فرهنگ هنر ادبیات")),
    ("سینما", google_news_search_url("سینما فیلم سریال تلویزیون")),
    ("فیلم و سریال", google_news_search_url("site:variety.com film OR series OR television OR streaming")),

    # AI / technology: intentionally split so one broad query does not
    # become the bottleneck for the entire technology category.
    ("هوش مصنوعی", google_news_search_url("هوش مصنوعی AI")),
    ("هوش مصنوعی", google_news_search_url("OpenAI ChatGPT")),
    ("هوش مصنوعی", google_news_search_url("Google Gemini DeepMind")),
    ("هوش مصنوعی", google_news_search_url("Anthropic Claude")),
    ("هوش مصنوعی", google_news_search_url("NVIDIA AI GPU")),
    ("هوش مصنوعی", google_news_search_url("مدل زبانی LLM هوش مصنوعی مولد")),
    ("رباتیک", google_news_search_url("رباتیک ربات انسان نما robotics")),
    ("فناوری", google_news_search_url("فناوری تکنولوژی")),
    ("فناوری", google_news_search_url("Microsoft Apple Google Meta Amazon")),
    ("فناوری", google_news_search_url("تراشه پردازنده نیمه رسانا semiconductor chip")),
    ("فناوری", google_news_search_url("امنیت سایبری هک حمله سایبری")),
    ("موبایل", google_news_search_url("موبایل گوشی iPhone Samsung Pixel")),
    ("اینترنت", google_news_search_url("اینترنت شبکه ارتباطات 5G")),

    # World / geopolitics: separate regional queries increase coverage
    # while the semantic deduplicator collapses reports about one event.
    ("جهان", google_news_search_url("آمریکا کاخ سفید کنگره ترامپ")),
    ("جهان", google_news_search_url("اروپا اتحادیه اروپا بریتانیا فرانسه آلمان")),
    ("جهان", google_news_search_url("روسیه اوکراین جنگ")),
    ("جهان", google_news_search_url("خاورمیانه اسرائیل فلسطین لبنان غزه")),
    ("جهان", google_news_search_url("ایران آمریکا مذاکرات تحریم")),
    ("جهان", google_news_search_url("چین تایوان آسیا ژاپن کره جنوبی")),
    ("جهان", google_news_search_url("هند پاکستان افغانستان")),
    ("جهان", google_news_search_url("آفریقا آمریکای لاتین جهان")),

    # Economy / energy / markets
    ("اقتصاد", google_news_search_url("تورم نرخ بهره اقتصاد جهانی")),
    ("اقتصاد", google_news_search_url("بانک مرکزی فدرال رزرو ECB")),
    ("نفت و انرژی", google_news_search_url("نفت گاز انرژی اوپک")),
    ("بورس", google_news_search_url("بورس سهام بازارهای مالی")),
    ("کریپتو", google_news_search_url("بیت کوین ارز دیجیتال کریپتو")),
    ("اقتصاد", google_news_search_url("خودرو بازار خودرو قیمت خودرو ایران")),

    # Sports: split by major sports rather than one overloaded query.
    ("ورزش", google_news_search_url("ورزش فوتبال ایران")),
    ("ورزش", google_news_search_url("لیگ قهرمانان فوتبال اروپا")),
    ("ورزش", google_news_search_url("Premier League football")),
    ("ورزش", google_news_search_url("NBA basketball")),
    ("ورزش", google_news_search_url("تنیس Wimbledon ATP WTA")),
    ("ورزش", google_news_search_url("فرمول یک Formula 1 F1")),
    ("ورزش", google_news_search_url("UFC MMA")),
]


# ============================================================
# IMPORTANCE
# ============================================================
# Keep only the explicitly allowed Iranian publishers. Google News may
# surface many other .ir outlets, so this check must run AFTER Google
# redirect resolution and must use all candidate URL fields.
IRANIAN_ALLOWED_HOSTS = {"yjc.ir", "irna.ir"}

IRANIAN_BLOCKED_DOMAINS = {
    "isna.ir", "mehrnews.com", "tasnimnews.com", "farsnews.ir",
    "snn.ir", "tabnak.ir", "khabaronline.ir", "tejaratnews.com",
    "donya-e-eqtesad.com", "ecoiran.com", "zoomit.ir", "varzesh3.com",
    "khabarfoori.com", "asriran.com", "aftabnews.ir", "jamaran.news",
    "entekhab.ir", "fararu.com", "khabarban.com", "rokna.net",
}


def _candidate_hosts(candidate):
    hosts = set()
    for key in ("resolved_link", "source_url", "link"):
        value = str(candidate.get(key, "") or "").strip()
        host = base_domain(get_hostname(value))
        if host:
            hosts.add(host)
    return hosts


def _is_iranian_blocked_source(candidate):
    """Return True only for disallowed Iranian publishers."""
    for host in _candidate_hosts(candidate):
        if host in IRANIAN_ALLOWED_HOSTS:
            continue
        if host.endswith(".ir"):
            return True
        if any(
            host == domain or host.endswith("." + domain)
            for domain in IRANIAN_BLOCKED_DOMAINS
        ):
            return True
    return False


def _is_iran_source(candidate):
    return any(
        host in IRANIAN_ALLOWED_HOSTS
        for host in _candidate_hosts(candidate)
    )


# ============================================================
# HTTP
# ============================================================

SESSION = requests.Session()

SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "fa,en;q=0.8",
})


# ============================================================
# ROUNDUP FILTER
# ============================================================

def load_history():

    hash_history = set()
    title_history = []

    if not os.path.exists(
        HISTORY_FILE
    ):
        return (
            hash_history,
            title_history
        )

    try:

        with open(
            HISTORY_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            for raw in f.read().splitlines():

                line = raw.strip()

                if not line:
                    continue

                # New format:
                # TITLE|timestamp|title
                if line.startswith(
                    "TITLE|"
                ):

                    parts = line.split(
                        "|",
                        2
                    )

                    if len(parts) == 3:

                        try:
                            timestamp = int(
                                parts[1]
                            )
                        except Exception:
                            timestamp = 0

                        title = clean_title(
                            parts[2]
                        )

                        if title:
                            title_history.append(
                                (
                                    timestamp,
                                    title
                                )
                            )

                    continue

                if re.fullmatch(r"[0-9a-fA-F]{32,64}", line):
                    hash_history.add(line.lower())
                else:
                    print("History load warning: ignored malformed history entry", flush=True)

    except Exception as e:

        print(
            f"History load error: {e}"
        )

    return (
        hash_history,
        title_history
    )


def save_history(
    hash_history,
    title_history
):

    try:

        cutoff = int(
            (
                datetime.now(
                    timezone.utc
                )
                - timedelta(
                    days=SEMANTIC_HISTORY_DAYS
                )
            ).timestamp()
        )

        recent_titles = []

        for timestamp, title in title_history:

            if timestamp >= cutoff:

                cleaned = clean_title(
                    title
                )

                if cleaned:
                    recent_titles.append(
                        (
                            timestamp,
                            cleaned
                        )
                    )

        # Deduplicate semantic records.
        seen_titles = set()
        cleaned_titles = []

        for timestamp, title in sorted(
            recent_titles,
            key=lambda x: x[0]
        ):

            key = normalize_space(
                title
            ).lower()

            if not key:
                continue

            if key in seen_titles:
                continue

            seen_titles.add(
                key
            )

            cleaned_titles.append(
                (
                    timestamp,
                    title
                )
            )

        # Hash-only legacy entries have no timestamps; retain a generous bounded
        # window while timestamped title records use the semantic age cutoff.
        bounded_hashes = sorted(hash_history)[-MAX_HASH_HISTORY:]
        lines = list(bounded_hashes)
        lines.extend(f"TITLE|{timestamp}|{title}" for timestamp, title in cleaned_titles)
        _atomic_save_text(HISTORY_FILE, "\n".join(lines) + ("\n" if lines else ""))

    except Exception as e:

        print(
            f"History save error: {e}"
        )


def make_history_key(
    title,
    link
):

    canonical_link = canonicalize_url(
        link
    )

    value = (
        normalize_space(title)
        + "|"
        + canonical_link
    )

    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


# ============================================================
# TITLE / STORY NORMALIZATION
# ============================================================
# GOOGLE NEWS RESOLUTION
# ============================================================

GOOGLE_RESOLVE_TIMEOUT = 6
GOOGLE_RESOLVE_WORKERS = 20
# Resolve a wider slice of Google discovery candidates so global breaking
# stories are not lost before their publisher URL is resolved.
GOOGLE_RESOLVE_MAX_CANDIDATES = 180


def _is_telemetry_or_tracking_url(url):
    """Reject analytics/tracking endpoints during Google News resolution."""
    try:
        host = base_domain(get_hostname(url))
        path = urlparse(url).path.lower()
    except Exception:
        return False
    blocked_hosts = (
        "google-analytics.com", "analytics.google.com", "googletagmanager.com",
        "doubleclick.net", "googlesyndication.com", "googleadservices.com",
        "facebook.net", "connect.facebook.net", "pixel.facebook.com",
        "segment.io", "segment.com", "hotjar.com", "clarity.ms",
    )
    blocked_paths = (
        "/analytics.js", "/gtag/js", "/gtm.js", "/pixel", "/collect",
        "/beacon", "/tracking", "/track", "/events", "/analytics",
    )
    return (
        host in blocked_hosts
        or any(host.endswith("." + x) for x in blocked_hosts)
        or any(token in path for token in blocked_paths)
    )


def resolve_google_news_url(
    url
):

    if not url:
        return ""

    if not is_google_host(
        url
    ):
        return canonicalize_url(
            url
        )

    try:

        response = SESSION.get(
            url,
            timeout=GOOGLE_RESOLVE_TIMEOUT,
            allow_redirects=True,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "Referer": "https://news.google.com/",
            },
        )

        final_url = canonicalize_url(response.url)

        # Normal HTTP redirects are preferred.
        if (
            final_url
            and not is_google_host(final_url)
            and not is_social_host(final_url)
            and not _is_telemetry_or_tracking_url(final_url)
        ):
            return final_url

        # Google News sometimes leaves the request on a Google host and
        # embeds the publisher URL in the returned HTML instead of issuing a
        # normal redirect. Recover canonical/OG/external links before giving
        # up, while explicitly rejecting Google/social destinations.
        html = response.text or ""
        soup = BeautifulSoup(html, "html.parser")

        embedded = []
        for selector in (
            "link[rel='canonical']",
            "meta[property='og:url']",
            "meta[name='twitter:url']",
        ):
            for node in soup.select(selector):
                value = node.get("href") or node.get("content") or ""
                if value:
                    embedded.append(urljoin(response.url, value))

        for anchor in soup.select("a[href]"):
            embedded.append(urljoin(response.url, anchor.get("href", "")))

        for candidate in embedded:
            candidate = canonicalize_url(candidate)
            if (
                candidate
                and not is_google_host(candidate)
                and not is_social_host(candidate)
                and not _is_telemetry_or_tracking_url(candidate)
                and get_hostname(candidate)
                and not candidate.startswith("javascript:")
            ):
                return candidate

        # Last-resort extraction for pages where BeautifulSoup does not see
        # a usable anchor/canonical element.
        for match in re.findall(
            r'https?://[^\s"\'<>\\]+',
            html,
            flags=re.I,
        ):
            candidate = canonicalize_url(match.rstrip(").,;"))
            if (
                candidate
                and not is_google_host(candidate)
                and not is_social_host(candidate)
                and not _is_telemetry_or_tracking_url(candidate)
                and get_hostname(candidate)
            ):
                return candidate

    except Exception as e:

        print(
            f"Google URL resolve failed: {e}"
        )

    return ""


# ============================================================
# ARTICLE
# ============================================================

def fetch_article(
    url
):

    if not url:
        return ""

    try:

        response = SESSION.get(
            url,
            timeout=ARTICLE_TIMEOUT,
            allow_redirects=True
        )

        if response.status_code != 200:
            return ""

        content_type = response.headers.get(
            "content-type",
            ""
        ).lower()

        if "text/html" not in content_type:
            return ""

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        for tag in soup([
            "script",
            "style",
            "noscript",
            "svg",
            "nav",
            "footer",
            "header",
            "aside",
            "form"
        ]):
            tag.decompose()

        candidates = []

        selectors = [
            "article",
            "[itemprop='articleBody']",
            ".article-body",
            ".article__body",
            ".news-body",
            ".news-content",
            ".content",
            "main"
        ]

        for selector in selectors:

            for node in soup.select(
                selector
            ):

                text = normalize_space(
                    node.get_text(
                        " ",
                        strip=True
                    )
                )

                if len(text) > 150:

                    candidates.append(
                        text
                    )

        if not candidates:

            paragraphs = []

            for p in soup.find_all("p"):

                text = normalize_space(
                    p.get_text(
                        " ",
                        strip=True
                    )
                )

                if len(text) >= 40:

                    paragraphs.append(
                        text
                    )

            if paragraphs:

                candidates.append(
                    " ".join(
                        paragraphs
                    )
                )

        if not candidates:
            return ""

        cleaned_candidates = []
        for candidate in candidates:
            cleaned = clean_content(candidate)
            if len(cleaned) < 150:
                continue

            # Prefer article-like candidates and penalize obvious webpage
            # chrome. A larger but polluted container must not win merely
            # because it contains navigation and membership text.
            boilerplate_hits = sum(
                1 for phrase in (
                    "عضویت در دیجیاتو",
                    "کپی لینک",
                    "در دیجیاتو ثبت نام کنید",
                    "دیجیاتو را در گوگل بیشتر ببینید",
                    "عضویت در خبرنامه",
                    "مطالب مرتبط",
                )
                if phrase in cleaned
            )
            score = len(cleaned) - (boilerplate_hits * 500)
            cleaned_candidates.append((score, cleaned))

        if not cleaned_candidates:
            return ""

        _, text = max(
            cleaned_candidates,
            key=lambda item: item[0]
        )

        return text[:6000]

    except Exception as e:

        print(
            f"Article fetch error: {e}"
        )

        return ""


# ============================================================
# IMAGE
# ============================================================

def absolute_url(
    url,
    base
):

    if not url:
        return ""

    try:

        return urljoin(
            base,
            url
        )

    except Exception:

        return url


def image_is_acceptable(
    url
):

    if not url:
        return False

    if is_bad_media_url(
        url
    ):
        return False

    lower = url.lower()

    bad_words = [
        "logo",
        "icon",
        "avatar",
        "favicon",
        "placeholder",
        "default",
        "sprite",
        "google-news",
        "google_news",
        "blank.gif"
    ]

    for word in bad_words:

        if word in lower:
            return False

    return True


def extract_image_from_html(
    html,
    page_url
):

    if not html:
        return ""

    try:

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        meta_names = [
            ("property", "og:image"),
            ("property", "og:image:url"),
            ("property", "og:image:secure_url"),
            ("name", "twitter:image"),
            ("name", "twitter:image:src"),
        ]

        for attr, value in meta_names:

            tag = soup.find(
                "meta",
                attrs={
                    attr: value
                }
            )

            if tag:

                url = tag.get(
                    "content",
                    ""
                ).strip()

                url = absolute_url(
                    url,
                    page_url
                )

                if image_is_acceptable(
                    url
                ):
                    return url

        article_nodes = soup.select(
            "article img, "
            "main img, "
            "[itemprop='articleBody'] img"
        )

        best = ""

        for img in article_nodes:

            src = (
                img.get(
                    "data-src"
                )
                or img.get(
                    "data-original"
                )
                or img.get(
                    "data-lazy-src"
                )
                or img.get(
                    "src"
                )
                or ""
            )

            src = absolute_url(
                src,
                page_url
            )

            if not image_is_acceptable(
                src
            ):
                continue

            width = 0
            height = 0

            try:
                width = int(
                    img.get(
                        "width",
                        0
                    )
                )
            except Exception:
                pass

            try:
                height = int(
                    img.get(
                        "height",
                        0
                    )
                )
            except Exception:
                pass

            if (
                width >= 500
                or height >= 300
            ):
                return src

            if not best:
                best = src

        return best

    except Exception:
        return ""


def extract_image_from_article(
    url
):

    if not url:
        return ""

    try:

        response = SESSION.get(
            url,
            timeout=ARTICLE_TIMEOUT,
            allow_redirects=True
        )

        if response.status_code != 200:
            return ""

        content_type = response.headers.get(
            "content-type",
            ""
        ).lower()

        if "text/html" not in content_type:
            return ""

        return extract_image_from_html(
            response.text,
            response.url
        )

    except Exception as e:

        print(
            f"Image extraction error: {e}"
        )

        return ""


# ============================================================
# VIDEO
# ============================================================

def extract_video_from_html(
    html,
    page_url
):

    if not html:
        return ""

    try:

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        meta_values = [
            ("property", "og:video"),
            ("property", "og:video:url"),
            ("property", "og:video:secure_url"),
            ("name", "twitter:player:stream"),
        ]

        for attr, value in meta_values:

            tag = soup.find(
                "meta",
                attrs={
                    attr: value
                }
            )

            if tag:

                url = tag.get(
                    "content",
                    ""
                ).strip()

                url = absolute_url(
                    url,
                    page_url
                )

                if (
                    looks_like_video_url(
                        url
                    )
                    and not is_bad_media_url(
                        url
                    )
                ):
                    return url

        for source in soup.select(
            "video source, video"
        ):

            url = (
                source.get(
                    "src"
                )
                or source.get(
                    "data-src"
                )
                or ""
            )

            url = absolute_url(
                url,
                page_url
            )

            if (
                looks_like_video_url(
                    url
                )
                and not is_bad_media_url(
                    url
                )
            ):
                return url
        for script in soup.find_all(
            "script",
            attrs={
                "type": "application/ld+json"
            }
        ):

            try:

                data = json.loads(
                    script.string
                    or script.get_text()
                )

                objects = data

                if isinstance(
                    data,
                    dict
                ):
                    objects = [data]

                if not isinstance(
                    objects,
                    list
                ):
                    continue

                for obj in objects:

                    if not isinstance(
                        obj,
                        dict
                    ):
                        continue

                    for key in [
                        "contentUrl",
                        "embedUrl"
                    ]:

                        url = obj.get(
                            key
                        )

                        if not url:
                            continue

                        url = absolute_url(
                            url,
                            page_url
                        )

                        if (
                            looks_like_video_url(
                                url
                            )
                            and not is_bad_media_url(
                                url
                            )
                        ):
                            return url

            except Exception:
                continue

    except Exception:
        pass

    return ""


def extract_video_from_article(
    url
):

    if not url:
        return ""

    try:

        response = SESSION.get(
            url,
            timeout=ARTICLE_TIMEOUT,
            allow_redirects=True
        )

        if response.status_code != 200:
            return ""

        return extract_video_from_html(
            response.text,
            response.url
        )

    except Exception as e:

        print(
            f"Video extraction error: {e}"
        )

        return ""


# ============================================================
# DOWNLOAD
# ============================================================

def download_file(
    url,
    filename,
    max_mb
):

    if not url:
        return ""

    # CDN/media connections can close early (IncompleteRead). Retry the
    # complete download instead of dropping an otherwise valid story.
    max_attempts = 3

    for attempt in range(1, max_attempts + 1):

        try:

            response = SESSION.get(
                url,
                timeout=(10, ARTICLE_TIMEOUT),
                stream=True,
                allow_redirects=True,
                headers={
                    "Cache-Control": "no-cache",
                    "Accept-Encoding": "identity",
                },
            )

            if response.status_code != 200:
                print(
                    f"Media download HTTP {response.status_code} "
                    f"(attempt {attempt}/{max_attempts})"
                )
                response.close()
                if attempt < max_attempts:
                    time.sleep(attempt)
                    continue
                return ""

            content_length = response.headers.get(
                "content-length"
            )

            if content_length:

                try:

                    size_mb = int(
                        content_length
                    ) / (
                        1024 * 1024
                    )

                    if size_mb > max_mb:

                        print(
                            f"File too large: "
                            f"{size_mb:.1f} MB"
                        )

                        response.close()
                        return ""

                except Exception:
                    pass

            total = 0

            with open(
                filename,
                "wb"
            ) as f:

                for chunk in response.iter_content(
                    chunk_size=64 * 1024
                ):

                    if not chunk:
                        continue

                    total += len(
                        chunk
                    )

                    if (
                        total
                        > max_mb
                        * 1024
                        * 1024
                    ):

                        print(
                            f"Download exceeded "
                            f"{max_mb} MB"
                        )

                        return ""

                    f.write(
                        chunk
                    )

            response.close()

            if total == 0:
                raise IOError(
                    "media download returned zero bytes"
                )

            print(
                f"Media download OK: "
                f"{total / (1024 * 1024):.2f} MB "
                f"(attempt {attempt})"
            )

            return filename

        except Exception as e:

            print(
                f"Download error "
                f"(attempt {attempt}/{max_attempts}): {e}"
            )

            try:
                if os.path.exists(filename):
                    os.remove(filename)
            except Exception:
                pass

            if attempt < max_attempts:
                time.sleep(attempt)
                continue

    print("Media download failed after 3 attempts.")
    return ""


# ============================================================
# WATERMARK
# ============================================================

def find_font(
    size,
    bold=True
):

    if bold:

        candidates = [
            "Vazirmatn-Bold.ttf",
            "./Vazirmatn-Bold.ttf",
        ]

    else:

        candidates = [
            "Vazirmatn-Regular.ttf",
            "./Vazirmatn-Regular.ttf",
        ]

    for path in candidates:

        if os.path.exists(
            path
        ):

            try:

                return ImageFont.truetype(
                    path,
                    size
                )

            except Exception:
                pass

    return ImageFont.load_default()


def resize_for_telegram(
    image
):

    width, height = image.size

    ratio = min(
        MAX_OUTPUT_IMAGE_WIDTH / width,
        MAX_OUTPUT_IMAGE_HEIGHT / height,
        1.0
    )

    if ratio >= 1:
        return image

    new_width = max(
        1,
        int(width * ratio)
    )

    new_height = max(
        1,
        int(height * ratio)
    )

    return image.resize(
        (
            new_width,
            new_height
        ),
        Image.Resampling.LANCZOS
    )


def add_watermark(
    input_path,
    output_path
):
    """
    Add a small, fixed-size watermark safely inside the image.
    Uses Pillow's bottom-right anchor so font bbox offsets cannot
    push the watermark outside the image.
    """
    try:
        image = Image.open(input_path).convert("RGBA")
        image = resize_for_telegram(image)
        width, height = image.size

        # Intentionally small: branding without covering the photo.
        if width >= 1400:
            font_size = 11
        elif width >= 1000:
            font_size = 10
        elif width >= 700:
            font_size = 10
        else:
            font_size = 9

        font = find_font(font_size, bold=True)
        draw = ImageDraw.Draw(image, "RGBA")

        margin = max(8, int(min(width, height) * 0.012))
        pad_x = 4
        pad_y = 2

        bbox = draw.textbbox(
            (0, 0),
            WATERMARK_TEXT,
            font=font,
            anchor="rb",
        )
        text_width = max(1, bbox[2] - bbox[0])
        text_height = max(1, bbox[3] - bbox[1])

        text_x = width - margin
        text_y = height - margin

        rect = [
            max(0, text_x - text_width - pad_x),
            max(0, text_y - text_height - pad_y),
            min(width - 1, text_x + pad_x),
            min(height - 1, text_y + pad_y),
        ]

        draw.rounded_rectangle(
            rect,
            radius=4,
            fill=(0, 0, 0, 28),
        )

        draw.text(
            (text_x + 1, text_y + 1),
            WATERMARK_TEXT,
            font=font,
            anchor="rb",
            fill=(0, 0, 0, 45),
        )

        draw.text(
            (text_x, text_y),
            WATERMARK_TEXT,
            font=font,
            anchor="rb",
            fill=(255, 255, 255, 185),
        )

        image.convert("RGB").save(
            output_path,
            "JPEG",
            quality=90,
            optimize=True,
        )
        return output_path

    except Exception as e:
        print(f"Watermark error: {e}")
        return input_path


# ============================================================
# TELEGRAM
# ============================================================

def telegram_api(
    method
):

    return (
        f"https://api.telegram.org/bot"
        f"{BOT_TOKEN}/{method}"
    )


def send_message(
    text
):

    try:

        response = SESSION.post(
            telegram_api(
                "sendMessage"
            ),
            data={
                "chat_id": CHANNEL_ID,
                "text": text,
                "disable_web_page_preview": True,
            },
            timeout=REQUEST_TIMEOUT
        )

        if response.ok:
            return True

        print(
            f"sendMessage failed: "
            f"{response.status_code} "
            f"{response.text[:500]}"
        )

    except Exception as e:

        # Telegram may have accepted the request before the client timed out.
        # Never treat an ambiguous transport error as a safe reason to retry
        # through another publication path.
        print(
            f"sendMessage ambiguous transport error: {e}"
        )

        return None

    return False


def send_photo(
    path,
    caption
):

    try:

        with open(
            path,
            "rb"
        ) as photo:

            response = SESSION.post(
                telegram_api(
                    "sendPhoto"
                ),
                data={
                    "chat_id": CHANNEL_ID,
                    "caption": caption,
                },
                files={
                    "photo": photo
                },
                timeout=REQUEST_TIMEOUT
            )

        if response.ok:

            print(
                "PHOTO PUBLISHED"
            )

            return True

        print(
            f"sendPhoto failed: "
            f"{response.status_code} "
            f"{response.text[:500]}"
        )

    except Exception as e:

        # A timeout can happen after Telegram has already accepted sendPhoto.
        # Returning False here would incorrectly trigger a text fallback and
        # can create the exact photo+text duplicate we are trying to prevent.
        print(
            f"sendPhoto ambiguous transport error: {e}"
        )

        return None

    return False


def get_video_duration(path):
    """Return accurate duration in whole seconds using ffprobe."""
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=15,
        )
        value = float((probe.stdout or "").strip())
        if value > 0:
            return max(1, int(round(value)))
    except Exception as e:
        print(f"Video duration probe failed: {e}")
    return 0


def send_video(path, caption):
    try:
        duration = get_video_duration(path)
        width = 0
        height = 0
        try:
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", path],
                capture_output=True, text=True, timeout=15,
            )
            dims = (probe.stdout or "").strip().split("x")
            if len(dims) == 2:
                width, height = int(dims[0]), int(dims[1])
        except Exception as e:
            print(f"Video dimensions probe failed: {e}")

        with open(path, "rb") as video:
            data = {
                "chat_id": CHANNEL_ID,
                "caption": caption,
                "supports_streaming": "true",
            }
            if duration:
                data["duration"] = str(duration)
            if width and height:
                data["width"] = str(width)
                data["height"] = str(height)

            response = SESSION.post(
                telegram_api("sendVideo"),
                data=data,
                files={"video": video},
                timeout=120,
            )

        if response.ok:
            print(f"VIDEO PUBLISHED | duration={duration}s | size={os.path.getsize(path)}")
            return True

        print(f"sendVideo failed: {response.status_code} {response.text[:500]}")
    except Exception as e:
        # The server may have accepted the video before the client timed out.
        # Do not fall back to photo/text after an ambiguous transport result.
        print(f"sendVideo ambiguous transport error: {e}")
        return None
    return False


# ============================================================
# CAPTION
# ============================================================

def _sanitize_caption_text(text):
    """Final caption safety: remove source/link boilerplate before Telegram."""
    value = str(text or "")
    value = re.sub(r"https?://\\S+", " ", value, flags=re.I)
    value = re.sub(r"www\\.\\S+", " ", value, flags=re.I)
    value = re.sub(
        r"(?:📡\\s*)?(?:منبع|منبع خبر|منبع اصلی)\\s*[:：-]?\\s*[^\\n]+",
        " ",
        value,
        flags=re.I,
    )
    value = re.sub(r"\\b(?:باشگاه خبرنگاران جوان|yjc\\.ir)\\b", " ", value, flags=re.I)
    value = re.sub(r"\\s{2,}", " ", value).strip()
    return value


def build_caption(
    title,
    body
):
    """Single canonical V13 news caption formatter."""
    title = _sanitize_caption_text(clean_title(title))
    body = _sanitize_caption_text(enforce_short_summary(body))

    parts = [f"📰 {title}"]
    if body:
        parts.append(body)
    parts.append("#نبض_خبر")
    parts.append("🔗 کانال نبض خبر: https://t.me/NabzKhabarOfficial")
    return "\n\n".join(parts)


# ============================================================
# GEMINI
# ============================================================

def gemini_request(
    title,
    article_text
):

    if not AI_API_KEY:
        return None

    if not article_text:
        article_text = title

    endpoint = (
        "https://generativelanguage.googleapis.com/"
        "v1beta/models/"
        f"{GEMINI_MODEL}:generateContent"
    )

    prompt = f"""
تو ویراستار ارشد یک کانال خبری فارسی هستی.

عنوان خبر:
{title}

متن خبر:
{article_text[:6000]}

وظیفه:
1. یک تیتر خبری کوتاه، دقیق و طبیعی فارسی بنویس.
2. متن را بدون اضافه کردن هیچ واقعیت جدیدی در حداکثر 3 جمله خلاصه کن.
3. نام رسانه، نام خبرگزاری، لینک، عبارت «به گزارش»، عبارت‌های تبلیغاتی و منبع را حذف کن.
4. اگر متن ناقص است، چیزی را حدس نزن.
5. لحن کاملاً خبری، خنثی و حرفه‌ای باشد.
6. از اغراق، کلیک‌بیت و نظر شخصی خودداری کن.
7. اگر عنوان اصلی مناسب است، آن را بی‌دلیل تغییر نده.
8. فقط اطلاعات موجود در متن را استفاده کن.

فقط JSON معتبر برگردان:

{{
  "title": "تیتر نهایی",
  "summary": "خلاصه نهایی"
}}
"""

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "maxOutputTokens": 500,
        }
    }

    try:

        response = SESSION.post(
            endpoint,
            params={
                "key": AI_API_KEY
            },
            json=payload,
            timeout=30
        )

        if not response.ok:

            print(
                f"Gemini error: "
                f"{response.status_code} "
                f"{response.text[:600]}"
            )

            return None

        data = response.json()

        text = (
            data.get(
                "candidates",
                [{}]
            )[0]
            .get(
                "content",
                {}
            )
            .get(
                "parts",
                [{}]
            )[0]
            .get(
                "text",
                ""
            )
        )

        if not text:
            return None

        text = text.strip()

        if text.startswith(
            "```"
        ):

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
            )

            text = text.strip()

        result = json.loads(
            text
        )

        final_title = clean_title(
            result.get(
                "title",
                ""
            )
        )

        final_summary = enforce_short_summary(
            result.get(
                "summary",
                ""
            )
        )

        if not final_title:

            final_title = clean_title(
                title
            )

        return {
            "title": final_title,
            "summary": final_summary
        }

    except Exception as e:

        print(
            f"Gemini exception: {e}"
        )

    return None


# ============================================================
# LOCAL FALLBACK
# ============================================================

def local_news_engine(
    title,
    body
):

    title = clean_title(
        title
    )

    body = clean_content(
        body
    )

    return {
        "title": title,
        "summary": enforce_short_summary(
            body
        )
    }


# ============================================================
# RSS COLLECTION# ============================================================

def collect_feed(
    category,
    url,
    is_google=False
):

    candidates = []

    try:

        response = None
        for attempt in range(3):
            try:
                response = SESSION.get(
                    url,
                    timeout=REQUEST_TIMEOUT
                )
                if response.status_code not in (429, 500, 502, 503, 504):
                    break
                wait_seconds = 1.5 * (2 ** attempt)
                print(
                    f"V13 RSS RETRY: {category} | HTTP {response.status_code} | "
                    f"attempt={attempt + 1}/3 | wait={wait_seconds:.1f}s"
                )
                if attempt < 2:
                    time.sleep(wait_seconds)
            except requests.RequestException as exc:
                print(
                    f"V13 RSS RETRY: {category} | {type(exc).__name__} | "
                    f"attempt={attempt + 1}/3"
                )
                if attempt < 2:
                    time.sleep(1.5 * (2 ** attempt))
        if response is None:
            raise RuntimeError("RSS request returned no response")
        response.raise_for_status()

        feed = feedparser.parse(
            response.content
        )

        print(
            f"RSS OK: {category} | "
            f"{len(feed.entries)} | "
            f"{url}"
        )

        for entry in feed.entries[:20]:

            # Strict freshness gate: only entries with a reliable publication
            # timestamp from the source are allowed into processing. This keeps
            # stale RSS items from consuming network/AI/media resources.
            published_at = parse_entry_time(
                entry
            )

            if not published_at:
                print(
                    f"SKIPPED NO TIMESTAMP: "
                    f"{entry.get('title', '')}"
                )
                continue

            age_seconds = (
                datetime.now(timezone.utc) - published_at
            ).total_seconds()

            if age_seconds < 0:
                # Small clock skew is tolerated, but clearly future-dated
                # entries are not allowed to bypass the freshness gate.
                if age_seconds < -300:
                    print(
                        f"SKIPPED INVALID FUTURE TIMESTAMP: "
                        f"{entry.get('title', '')}"
                    )
                    continue
                age_seconds = 0

            if age_seconds > (FEED_COLLECTION_WINDOW_MINUTES * 60):
                raw_entry_title = normalize_space(entry.get("title", ""))
                rescue_limit = IMPORTANT_NEWS_RESCUE_MAX_AGE_MINUTES * 60

                if (
                    age_seconds <= rescue_limit
                    and is_important_news_rescue_candidate(raw_entry_title)
                ):
                    print(
                        "V13 IMPORTANT NEWS RESCUE: "
                        f"{raw_entry_title} | age={int(age_seconds // 60)}m"
                    )
                else:
                    print(
                        f"SKIPPED OUTSIDE {FEED_COLLECTION_WINDOW_MINUTES}M WINDOW: "
                        f"{raw_entry_title}"
                    )
                    continue

            raw_title = normalize_space(
                entry.get(
                    "title",
                    ""
                )
            )

            raw_link = clean_url(
                entry.get(
                    "link",
                    ""
                )
            )

            if not raw_title or not raw_link:
                continue

            title = clean_title(
                raw_title
            )

            if not title:
                continue

            if is_roundup_title(
                title
            ):

                print(
                    f"SKIPPED ROUNDUP: "
                    f"{title}"
                )

                continue


            summary = clean_content(
                entry.get(
                    "summary",
                    ""
                )
                or entry.get(
                    "description",
                    ""
                )
            )

            image_url = ""

            # RSS media.
            media_content = entry.get(
                "media_content",
                []
            )

            for media in media_content:

                if not isinstance(
                    media,
                    dict
                ):
                    continue

                media_url = clean_url(
                    media.get(
                        "url",
                        ""
                    )
                )

                if (
                    image_is_acceptable(
                        media_url
                    )
                    and not looks_like_video_url(
                        media_url
                    )
                ):

                    image_url = media_url
                    break

            # RSS enclosure.
            if not image_url:

                enclosures = entry.get(
                    "enclosures",
                    []
                )

                for enclosure in enclosures:

                    media_url = clean_url(
                        enclosure.get(
                            "href",
                            ""
                        )
                        or enclosure.get(
                            "url",
                            ""
                        )
                    )

                    media_type = enclosure.get(
                        "type",
                        ""
                    ).lower()

                    if (
                        "image" in media_type
                        and image_is_acceptable(
                            media_url
                        )
                    ):

                        image_url = media_url
                        break

            source_name = ""
            source_url = ""

            source = entry.get(
                "source"
            )

            if isinstance(
                source,
                dict
            ):

                source_name = normalize_space(
                    source.get(
                        "title",
                        ""
                    )
                )

                source_url = clean_url(
                    source.get(
                        "href",
                        ""
                    )
                )

            candidate = {
                "category": category,
                "title": title,
                "summary": summary,
                "link": canonicalize_url(
                    raw_link
                ),
                "published_at": published_at,
                "image_url": image_url,
                "video_url": "",
                "is_google": is_google,
                "resolved_link": "",
                "source_name": source_name,
                "source_url": source_url,
                "article_text": "",
                "importance": 0,
                "cluster_size": 1,
            }

            candidates.append(
                candidate
            )

    except Exception as e:

        print(
            f"RSS ERROR: {category} | "
            f"{url} | {e}"
        )

    return candidates


# ============================================================
# CLUSTERING
# ============================================================

def choose_cluster_representative(
    cluster
):

    if not cluster:
        return None

    def score(item):

        value = 0

        value += publisher_quality(
            item.get(
                "link",
                ""
            )
        )

        # Direct publishers beat Google discovery.
        if item.get(
            "is_google"
        ):
            value -= 25

        if item.get(
            "resolved_link"
        ):
            value += 8

        if item.get(
            "article_text"
        ):
            value += 5

        if item.get(
            "image_url"
        ):
            value += 3

        if item.get(
            "video_url"
        ):
            value += 4

        value += item.get(
            "importance",
            0
        )

        return value

    return max(
        cluster,
        key=score
    )


def cluster_candidates(
    candidates
):

    clusters = []

    ordered = sorted(
        candidates,
        key=lambda x: (
            publisher_quality(
                x.get(
                    "link",
                    ""
                )
            ),
            x.get(
                "published_at"
            )
            or datetime.min.replace(
                tzinfo=timezone.utc
            )
        ),
        reverse=True
    )

    for candidate in ordered:

        placed = False

        for cluster in clusters:

            for existing in cluster:

                if same_story(
                    candidate,
                    existing
                ):

                    cluster.append(
                        candidate
                    )

                    placed = True
                    break

            if placed:
                break

        if not placed:

            clusters.append(
                [candidate]
            )

    result = []

    for cluster in clusters:

        representative = choose_cluster_representative(
            cluster
        )

        if not representative:
            continue

        representative["cluster_size"] = len(
            cluster
        )

        # Transfer useful metadata.
        for item in cluster:

            if (
                not representative.get(
                    "summary"
                )
                and item.get(
                    "summary"
                )
            ):

                representative["summary"] = item[
                    "summary"
                ]

            if (
                not representative.get(
                    "image_url"
                )
                and item.get(
                    "image_url"
                )
                and not is_google_host(
                    item.get(
                        "image_url",
                        ""
                    )
                )
            ):

                representative["image_url"] = item[
                    "image_url"
                ]

        result.append(
            representative
        )

    return result


# ============================================================
# COLLECT ALL
# ============================================================

def collect_candidates(
    hash_history,
    title_history
):

    all_candidates = []

    # --------------------------------------------------------
    # Direct publishers
    # --------------------------------------------------------

    def collect_one_direct(feed):

        category, url = feed

        return collect_feed(
            category,
            url,
            is_google=False
        )

    # Fetch independent feeds concurrently so adding sources does not
    # make total network wait time grow linearly with source count.
    with ThreadPoolExecutor(max_workers=8) as executor:

        for items in executor.map(
            collect_one_direct,
            DIRECT_RSS_FEEDS
        ):
            all_candidates.extend(items)

    # --------------------------------------------------------
    # Google discovery
    # --------------------------------------------------------

    def collect_one_google(feed):

        category, url = feed

        return collect_feed(
            category,
            url,
            is_google=True
        )

    # More Google queries are now used for breadth, so keep discovery
    # parallelized to avoid making network wait grow with query count.
    with ThreadPoolExecutor(max_workers=6) as executor:

        for items in executor.map(
            collect_one_google,
            GOOGLE_NEWS_FEEDS
        ):
            all_candidates.extend(items)

    print(
        f"Raw candidates found: "
        f"{len(all_candidates)}"
    )

    # --------------------------------------------------------
    # Exact duplicate removal
    # --------------------------------------------------------

    unique = {}

    for item in all_candidates:

        key = (
            normalize_space(
                item.get(
                    "title",
                    ""
                )
            ).lower()
            + "|"
            + canonicalize_url(
                item.get(
                    "link",
                    ""
                )
            ).lower()
        )

        if key not in unique:
            unique[key] = item

    all_candidates = list(
        unique.values()
    )

    # --------------------------------------------------------
    # HARD HISTORY FILTER BEFORE SCORING
    #
    # This is one of the most important v11 changes.
    # Old/recent stories are removed BEFORE top priority.
    # --------------------------------------------------------

    filtered = []

    history_skipped = 0

    for item in all_candidates:

        title = item.get(
            "title",
            ""
        )

        link = item.get(
            "link",
            ""
        )

        old_hash = make_history_key(
            title,
            link
        )

        if old_hash in hash_history:

            history_skipped += 1

            print(
                f"PRE-SKIPPED OLD HASH: "
                f"{title}"
            )

            continue

        if history_contains_story(
            title,
            title_history
        ):

            history_skipped += 1

            print(
                f"PRE-SKIPPED SEMANTIC: "
                f"{title}"
            )

            continue

        filtered.append(
            item
        )

    print(
        f"Removed by history before scoring: "
        f"{history_skipped}"
    )

    all_candidates = filtered

    if not all_candidates:
        return []

    # --------------------------------------------------------
    # Initial importance.
    # --------------------------------------------------------

    for item in all_candidates:

        item["importance"] = calculate_importance(
            item
        )

    # --------------------------------------------------------
    # Initial clustering.
    # --------------------------------------------------------

    clustered = cluster_candidates(
        all_candidates
    )

    print(
        f"After story clustering: "
        f"{len(clustered)}"
    )

    # --------------------------------------------------------
    # Google resolution.
    #
    # IMPORTANT:
    # source_url is NOT treated as article URL anymore.
    # --------------------------------------------------------

    clustered.sort(
        key=lambda x: (
            x.get(
                "importance",
                0
            ),
            x.get(
                "published_at"
            )
            or datetime.min.replace(
                tzinfo=timezone.utc
            )
        ),
        reverse=True
    )

    resolved_count = 0
    removed_google = 0

    # Google News redirect resolution used to run serially. With many
    # discovery queries, a handful of slow Google redirects could consume
    # most of the 10-minute workflow interval. Resolve them concurrently
    # with a short hard timeout so one bad redirect cannot stall the run.
    google_items = [
        item for item in clustered[:GOOGLE_RESOLVE_MAX_CANDIDATES]
        if item.get("is_google")
    ]

    def resolve_one_google(item):
        link = item.get("link", "")
        return item, resolve_google_news_url(link)

    with ThreadPoolExecutor(max_workers=GOOGLE_RESOLVE_WORKERS) as executor:
        for item, resolved in executor.map(
            resolve_one_google,
            google_items
        ):
            if resolved:
                item["resolved_link"] = resolved

                if (
                    not is_social_host(resolved)
                    and not is_google_host(resolved)
                ):
                    item["link"] = resolved
                    resolved_count += 1

            # DO NOT use source_url as an article URL.
            # Google source_url is often just publisher homepage.
            if not item.get("resolved_link"):
                item["_unresolved_google"] = True

    print(
        f"Google articles resolved: "
        f"{resolved_count}"
    )

    # --------------------------------------------------------
    # Remove unresolved Google candidates.
    #
    # Direct publisher RSS remains the fallback.
    # --------------------------------------------------------

    cleaned = []

    for item in clustered:

        # Re-check the actual resolved publisher after Google News URL
        # resolution. This closes the loophole where source_url is only
        # metadata and the real article belongs to an Iranian publisher.
        if _is_iranian_blocked_source(item):
            print(
                f"SKIPPED IRANIAN PUBLISHER: "
                f"{item.get('title', '')}"
            )
            continue

        if (
            item.get(
                "is_google"
            )
            and not item.get(
                "resolved_link"
            )
        ):
            # A failed Google redirect must not erase a genuinely breaking
            # story. Keep only clearly high-impact headlines with a useful
            # RSS summary; ordinary unresolved Google items are still dropped.
            google_title = normalize_space(item.get("title", "")).lower()
            google_summary = normalize_space(item.get("summary", ""))
            high_priority_google = _has_global_high_impact(
                google_title + " " + google_summary
            )
            if high_priority_google and len(google_summary) >= 120:
                item["_unresolved_google_high_impact"] = True
                print(
                    f"KEEP UNRESOLVED HIGH-IMPACT GOOGLE: "
                    f"{item.get('title', '')}"
                )
                cleaned.append(item)
                continue

            removed_google += 1

            print(
                f"SKIPPED UNRESOLVED GOOGLE: "
                f"{item.get('title', '')}"
            )

            continue

        cleaned.append(
            item
        )

    clustered = cleaned

    print(
        f"Unresolved Google removed: "
        f"{removed_google}"
    )

    # --------------------------------------------------------
    # Recalculate final quality.
    # --------------------------------------------------------

    for item in clustered:

        item["importance"] = calculate_importance(
            item
        )

    # --------------------------------------------------------
    # Cluster again after Google resolution.
    # --------------------------------------------------------

    clustered = cluster_candidates(
        clustered
    )

    # --------------------------------------------------------
    # Final importance.
    # --------------------------------------------------------

    for item in clustered:

        item["importance"] = calculate_importance(
            item
        )

    # --------------------------------------------------------
    # FINAL HISTORY FILTER AGAIN
    #
    # Protects against clusters/reps changing titles.
    # --------------------------------------------------------

    final_candidates = []

    for item in clustered:
        title = item.get(
            "title",
            ""
        )

        link = item.get(
            "link",
            ""
        )

        if history_contains_story(
            title,
            title_history
        ):
            continue

        if make_history_key(
            title,
            link
        ) in hash_history:
            continue

        final_candidates.append(
            item
        )

    clustered = final_candidates

    # --------------------------------------------------------
    # Final sort.
    # --------------------------------------------------------

    clustered.sort(
        key=lambda x: (
            x.get(
                "importance",
                0
            ),
            x.get(
                "published_at"
            )
            or datetime.min.replace(
                tzinfo=timezone.utc
            )
        ),
        reverse=True
    )

    print(
        f"Candidates found: "
        f"{len(clustered)}"
    )

    print(
        "\nTOP PRIORITY NEWS:"
    )

    for item in clustered[:15]:

        print(
            f"[{item.get('importance', 0)}] "
            f"{item.get('category', '')} - "
            f"{item.get('title', '')}"
        )

    return clustered


# ============================================================
# CATEGORY
# ============================================================

def category_family(
    category
):

    category = normalize_space(
        category
    )

    mapping = {
        "خبر فوری": "ایران",
        "حوادث": "حوادث",
        "ایران": "ایران",
        "جهان": "جهان",
        "اقتصاد": "اقتصاد",
        "دلار": "بازار",
        "ارز": "بازار",
        "طلا": "بازار",
        "سکه": "بازار",
        "بورس": "بازار",
        "نفت": "انرژی",
        "هوش مصنوعی": "فناوری",
        "فناوری": "فناوری",
        "موبایل": "فناوری",
        "خودرو": "خودرو",
        "ورزش": "ورزش",
        "سلامت": "سلامت",
        "علم": "علم",
        "فرهنگ": "فرهنگ",
        "جامعه": "جامعه",
        "کریپتو": "بازار",
    }

    return mapping.get(
        category,
        category
    )


def family_count(
    candidate,
    selected
):

    family = category_family(
        candidate.get(
            "category",
            ""
        )
    )

    count = 0

    for item in selected:

        if category_family(
            item.get(
                "category",
                ""
            )
        ) == family:

            count += 1

    return count


def diversity_penalty(
    candidate,
    selected
):

    count = family_count(
        candidate,
        selected
    )

    if count <= 0:
        return 0

    if count == 1:
        return 4

    if count == 2:
        return 10

    return 18


# ============================================================
# PROCESS NEWS
# ============================================================

def process_news(
    candidate,
    hash_history,
    title_history
):

    original_title = candidate.get(
        "title",
        ""
    )

    link = canonicalize_url(
        candidate.get(
            "link",
            ""
        )
    )

    candidate["link"] = link

    print(
        f"\nProcessing: "
        f"{original_title}"
    )

    # --------------------------------------------------------
    # Exact hash.
    # --------------------------------------------------------

    history_key = make_history_key(
        original_title,
        link
    )

    if history_key in hash_history:

        print(
            "SKIPPED: old hash history"
        )

        return False

    # --------------------------------------------------------
    # Semantic history.
    # --------------------------------------------------------

    if history_contains_story(
        original_title,
        title_history
    ):

        print(
            "SKIPPED: semantic history"
        )

        return False

    # --------------------------------------------------------
    # Article URL.
    # --------------------------------------------------------

    article_url = (
        candidate.get(
            "resolved_link"
        )
        or candidate.get(
            "link"
        )
    )

    if (
        is_google_host(
            article_url
        )
        or is_social_host(
            article_url
        )
    ):
        article_url = ""

    # --------------------------------------------------------
    # Article text.
    # --------------------------------------------------------

    article_text = ""

    if article_url:

        article_text = fetch_article(
            article_url
        )

    candidate["article_text"] = article_text

    if article_text:

        print(
            f"Article text: "
            f"{len(article_text)} chars"
        )

    # --------------------------------------------------------
    # Image.
    # --------------------------------------------------------

    image_url = ""

    rss_image = candidate.get(
        "image_url",
        ""
    )

    if image_is_acceptable(
        rss_image
    ):
        image_url = rss_image

    if candidate.get(
        "is_google"
    ):

        image_url = ""

        if article_url:

            publisher_image = extract_image_from_article(
                article_url
            )

            if publisher_image:
                image_url = publisher_image

    else:

        if article_url:

            article_image = extract_image_from_article(
                article_url
            )

            if article_image:
                image_url = article_image

    if not image_is_acceptable(
        image_url
    ):
        image_url = ""

    # --------------------------------------------------------
    # Video.
    # --------------------------------------------------------

    video_url = ""

    if article_url:

        video_url = extract_video_from_article(
            article_url
        )

    if not video_url:

        rss_video = candidate.get(
            "video_url",
            ""
        )

        if looks_like_video_url(
            rss_video
        ):
            video_url = rss_video

    if (
        is_hls_url(
            video_url
        )
        or is_bad_media_url(
            video_url
        )
    ):

        if video_url:

            print(
                f"Video skipped: "
                f"{video_url}"
            )

        video_url = ""

    # --------------------------------------------------------
    # Gemini.
    # --------------------------------------------------------

    source_text = (
        article_text
        or candidate.get(
            "summary",
            ""
        )
        or original_title
    )

    ai_result = None

    # Always enter the V13 router. It owns the free fallback chain
    try:
        ai_result = gemini_request(
            original_title,
            source_text
        )
    except Exception as exc:
        print(f"V13 AI ROUTER ERROR: {exc}", flush=True)
        ai_result = None

    if ai_result:

        final_title = ai_result.get(
            "title",
            ""
        )

        final_summary = ai_result.get(
            "summary",
            ""
        )

        print(
            f"Gemini title: "
            f"{final_title}"
        )

    else:

        # AI is optional for already-Persian publisher content. If the free
        # AI pool is temporarily exhausted/cooling down, never lose a valid
        # Iranian/Persian news event just because rewriting failed. Use only
        # the publisher's existing Persian text; for foreign content, AI is
        # mandatory because we must not publish untranslated English.
        if _persian_ratio(original_title) >= 0.60:
            candidate["publication_status"] = "ai_unavailable_persian_fallback"
            print("V13 AI FALLBACK: AI providers unavailable; using publisher Persian text (no AI output).")
            print("V13 AI FALLBACK: status=SOURCE_PERSIAN_FALLBACK")
            final_title = clean_title(original_title)

            source_clean = clean_content(source_text)
            if _persian_ratio(source_clean) >= 0.55:
                final_summary = enforce_short_summary(source_clean)
            else:
                final_summary = ""
        else:
            print("V13 AI FALLBACK: foreign story blocked because no translation model is available.")
            candidate["publication_status"] = "ai_unavailable_foreign"
            return False

    # --------------------------------------------------------
    # Final cleaning.
    # --------------------------------------------------------

    final_title = clean_title(
        final_title
    )

    final_title = media_consistent_text(
        final_title,
        has_video=bool(video_url)
    )

    final_summary = enforce_short_summary(
        final_summary
    )

    final_summary = media_consistent_text(
        final_summary,
        has_video=bool(video_url)
    )

    if not final_title:

        final_title = clean_title(
            original_title
        )

    # --------------------------------------------------------
    # Final semantic protection.
    # --------------------------------------------------------

    if history_contains_story(
        final_title,
        title_history
    ):

        print(
            "SKIPPED DUPLICATE: final Gemini title "
            "matches recent history"
        )
        candidate["publication_status"] = "skipped_duplicate"
        return False

    # --------------------------------------------------------
    # Also check original vs final.
    # If Gemini accidentally creates a title extremely
    # close to another selected story, block it later too.
    # --------------------------------------------------------

    caption = build_caption(
        final_title,
        final_summary
    )

    # ========================================================
    # VIDEO FIRST
    # ========================================================

    if video_url:

        print(
            f"Downloading video: "
            f"{video_url}"
        )

        video_path = (
            "nabz_video_"
            + hashlib.md5(
                video_url.encode()
            ).hexdigest()
            + ".mp4"
        )

        downloaded = download_file(
            video_url,
            video_path,
            MAX_VIDEO_MB
        )

        if downloaded:

            success = send_video(
                downloaded,
                caption
            )

            if success is None:
                candidate["publication_status"] = "publication_ambiguous"
                print(
                    "V13 PUBLICATION AMBIGUOUS: sendVideo transport timed out; "
                    "stopping fallback to prevent duplicate publication."
                )
                try:
                    os.remove(downloaded)
                except Exception:
                    pass
                return False

            try:
                os.remove(
                    downloaded
                )
            except Exception:
                pass

            if success:

                # Store BOTH original and final title.
                hash_history.add(
                    history_key
                )

                record_semantic_history(
                    original_title,
                    title_history
                )

                record_semantic_history(
                    final_title,
                    title_history
                )

                save_history(
                    hash_history,
                    title_history
                )

                print(
                    f"PUBLISHED: "
                    f"{final_title}"
                )

                return True

        # Video is optional media, not a publication requirement.
        # If a selected story is important but its video is too large,
        # unavailable, or rejected by Telegram, continue through the normal
        # photo -> text fallback so the news event itself is never silently lost.
        final_title = media_consistent_text(final_title, has_video=False)
        final_summary = media_consistent_text(final_summary, has_video=False)
        caption = build_caption(final_title, final_summary)

        print(
            "VIDEO FALLBACK: video unavailable/failed; "
            "media claim removed; continuing with photo/text fallback."
        )

    # ========================================================
    # PHOTO
    # ========================================================

    if image_url:

        print(
            f"Downloading image: "
            f"{image_url}"
        )

        image_raw = (
            "nabz_image_"
            + hashlib.md5(
                image_url.encode()
            ).hexdigest()
            + ".jpg"
        )

        downloaded = download_file(
            image_url,
            image_raw,
            MAX_IMAGE_MB
        )

        if downloaded:

            try:

                img = Image.open(
                    downloaded
                )

                img.verify()

                watermarked = (
                    "nabz_watermark_"
                    + hashlib.md5(
                        image_url.encode()
                    ).hexdigest()
                    + ".jpg"
                )

                # add_watermark() may intentionally return the original
                # image when the watermark is unsafe/too large. Always use
                # the returned path so we never try to upload a file that
                # was not created.
                branded_path = add_watermark(
                    downloaded,
                    watermarked
                )

                success = send_photo(
                    branded_path,
                    caption
                )

                if success is None:
                    candidate["publication_status"] = "publication_ambiguous"
                    print(
                        "V13 PUBLICATION AMBIGUOUS: sendPhoto transport timed out; "
                        "stopping text fallback to prevent photo+text duplicate."
                    )
                    try:
                        os.remove(downloaded)
                    except Exception:
                        pass
                    if watermarked != downloaded:
                        try:
                            os.remove(watermarked)
                        except Exception:
                            pass
                    return False

                try:
                    os.remove(
                        downloaded
                    )
                except Exception:
                    pass

                try:

                    if (
                        watermarked
                        != downloaded
                    ):
                        os.remove(
                            watermarked
                        )

                except Exception:
                    pass

                if success:

                    hash_history.add(
                        history_key
                    )

                    record_semantic_history(
                        original_title,
                        title_history
                    )

                    record_semantic_history(
                        final_title,
                        title_history
                    )

                    save_history(
                        hash_history,
                        title_history
                    )

                    print(
                        f"PUBLISHED: "
                        f"{final_title}"
                    )

                    return True

            except Exception as e:

                print(
                    f"Image processing error: "
                    f"{e}"
                )

                try:
                    os.remove(
                        downloaded
                    )
                except Exception:
                    pass

    # ========================================================
    # TEXT FALLBACK
    # ========================================================
    # Media is preferred, but missing/broken article media must never
    # silently discard an otherwise valid news story. Video stories remain
    # protected above and are not converted to a misleading text post.

    success = send_message(
        caption
    )

    if success is None:
        candidate["publication_status"] = "publication_ambiguous"
        print(
            "V13 PUBLICATION AMBIGUOUS: sendMessage transport error; "
            "no retry will be attempted."
        )
        return False

    if success:

        hash_history.add(
            history_key
        )

        record_semantic_history(
            original_title,
            title_history
        )

        record_semantic_history(
            final_title,
            title_history
        )

        save_history(
            hash_history,
            title_history
        )

        print(
            f"PUBLISHED TEXT: "
            f"{final_title}"
        )

        return True

    print(
        "FAILED TO PUBLISH"
    )

    return False


# ============================================================
# MAIN
# ============================================================

def main():

    start_time = time.time()

    hash_history, title_history = load_history()

    print(
        f"Old hash history: "
        f"{len(hash_history)}"
    )

    print(
        f"Semantic history: "
        f"{len(title_history)}"
    )

    candidates = collect_candidates(
        hash_history,
        title_history
    )

    if not candidates:

        print(
            "No fresh unused candidates found."
        )

        return

    published = 0
    selected = []

    # ========================================================
    # SOFT DIVERSITY SELECTION
    #
    # Category repetition is now a penalty, not a hard block.
    # A genuinely important breaking story can still pass.
    # ========================================================

    remaining = list(
        candidates
    )

    # Publish every genuinely new, valid candidate selected by the quality,
    # freshness, semantic-dedup, and diversity pipeline. There is no arbitrary
    # per-run quota: 0 new stories means 0 posts; 10 valid stories means 10 posts.
    while remaining:

        best = None
        best_effective_score = None

        for candidate in remaining:

            title = candidate.get(
                "title",
                ""
            )

            # Current-run semantic duplicate.
            duplicate = False

            for used in selected:

                if same_story(
                    candidate,
                    used
                ):

                    duplicate = True

                    break

            if duplicate:
                continue

            # Recent history. Critical/freshness-rescued stories may
            # intentionally bypass semantic history; the same bypass must be
            # honored by the final selection loop or the rescue is silently
            # discarded after intelligence has selected it.
            if (
                history_contains_story(
                    title,
                    title_history
                )
            ):
                # Rescue may bypass the old-hash gate, but NEVER bypass
                # semantic history. A critical story already published must
                # not consume a selection slot and then be discarded later.
                continue

            # Effective score.
            base_score = candidate.get(
                "importance",
                0
            )

            penalty = diversity_penalty(
                candidate,
                selected
            )
            effective_score = (
                base_score
                - penalty
            )

            if (
                best is None
                or effective_score
                > best_effective_score
            ):

                best = candidate
                best_effective_score = effective_score

        if best is None:
            break

        remaining.remove(
            best
        )

        print(
            f"\nSELECTED: "
            f"[{best.get('importance', 0)}] "
            f"{best.get('category', '')} - "
            f"{best.get('title', '')}"
        )

        success = process_news(
            best,
            hash_history,
            title_history
        )

        if success:

            published += 1

            selected.append(
                best
            )

            time.sleep(
                1
            )

    # ========================================================
    # FINAL STATS
    # ========================================================

    elapsed = (
        time.time()
        - start_time
    )

    print(
        "\n"
        + "=" * 64
    )

    print(
        f"FINISHED - Published: "
        f"{published}"
    )

    print(
        f"Runtime: "
        f"{elapsed:.1f}s"
    )

    print(
        f"Semantic history now: "
        f"{len(title_history)}"
    )

    print(
        "=" * 64
    )



# ============================================================
