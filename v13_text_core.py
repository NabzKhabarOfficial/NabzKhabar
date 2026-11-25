"""Pure text/URL/scoring helpers for the NabzKhabar bot.

Extracted verbatim from v13_standalone.py (improvement 5, module split).
No network, no Telegram, no AI, no monkeypatching: these are leaf helpers.
The monolith re-exports every name, so `main.<name>` keeps working.
"""
import hashlib
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import (
    urlparse,
    parse_qs,
    urlencode,
    quote,
    unquote,
    urlsplit,
    urlunparse,
    parse_qsl,
)

from bs4 import BeautifulSoup


# Tunables used by the helpers below. They live in this leaf module (no import
# cycle) and the monolith re-exports them so `main.<name>` keeps working.
SEMANTIC_HISTORY_DAYS = 7   # semantic duplicate protection window (days)
MAX_NEWS_AGE_HOURS = 0.5    # hard freshness window (delayed stories -> v13_freshness_rescue)


# ============================================================

def normalize_space(text):
    if not text:
        return ""

    text = str(text)

    text = text.replace("\u200c", " ")
    text = text.replace("\u200f", " ")
    text = text.replace("\u200e", " ")
    text = text.replace("\xa0", " ")

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_digits(text):
    if not text:
        return ""

    table = str.maketrans(
        "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
        "01234567890123456789"
    )

    return text.translate(table)


def clean_url(url):
    if not url:
        return ""

    return str(url).strip()


def get_hostname(url):
    try:
        return urlparse(url).netloc.lower().split(":")[0]
    except Exception:
        return ""


def base_domain(host):
    host = (host or "").lower()

    if host.startswith("www."):
        host = host[4:]

    return host


# ============================================================
# LANGUAGE HELPERS

# ============================================================

def _persian_ratio(text):
    """Return the share of alphabetic characters that are Persian/Arabic."""
    letters = re.findall(r"[A-Za-z\u0600-\u06ff]", str(text or ""))
    if not letters:
        return 1.0
    return sum("\u0600" <= ch <= "\u06ff" for ch in letters) / len(letters)


class SkipForeignStory(Exception):
    """Signal that a candidate must be skipped without failing the whole run."""
    pass


# ============================================================
# URL CANONICALIZATION

# ============================================================

TRACKING_PARAMETERS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_name",
    "gclid",
    "fbclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "referrer",
    "source",
    "output",
}


def canonicalize_url(url):
    """
    Removes tracking parameters so the same article with
    different tracking links produces the same history key.
    """

    if not url:
        return ""

    try:
        parsed = urlparse(
            clean_url(url)
        )

        scheme = (
            parsed.scheme
            or "https"
        ).lower()

        host = (
            parsed.netloc
            or ""
        ).lower()

        if host.startswith("www."):
            host = host[4:]

        path = parsed.path or "/"

        # Remove trailing slash except root.
        if path != "/":
            path = path.rstrip("/")

        query_items = parse_qsl(
            parsed.query,
            keep_blank_values=True
        )

        filtered = []

        for key, value in query_items:

            key_lower = key.lower()

            if key_lower in TRACKING_PARAMETERS:
                continue

            if key_lower.startswith("utm_"):
                continue

            filtered.append(
                (key, value)
            )

        filtered.sort()

        query = urlencode(
            filtered,
            doseq=True
        )

        return urlunparse(
            (
                scheme,
                host,
                path,
                "",
                query,
                ""
            )
        )

    except Exception:
        return clean_url(url)


# ============================================================
# HOST FILTERS

# ============================================================

def is_google_host(url):
    host = get_hostname(url)

    return (
        host == "news.google.com"
        or host == "google.com"
        or host.endswith(".google.com")
        or "googleusercontent.com" in host
        or "gstatic.com" in host
    )


def is_social_host(url):
    host = get_hostname(url)

    social_hosts = (
        "facebook.com",
        "fb.com",
        "fbcdn.net",
        "x.com",
        "twitter.com",
        "twimg.com",
        "youtube.com",
        "youtu.be",
        "tiktok.com",
        "instagram.com",
        "telegram.me",
        "t.me"
    )

    return any(
        host == x or host.endswith("." + x)
        for x in social_hosts
    )


def is_bad_media_url(url):
    if not url:
        return True

    host = get_hostname(url)

    bad_hosts = (
        "googleusercontent.com",
        "gstatic.com",
        "google.com",
        "facebook.com",
        "fbcdn.net",
        "twitter.com",
        "twimg.com",
        "x.com"
    )

    return any(
        host == x or host.endswith("." + x)
        for x in bad_hosts
    )


def looks_like_video_url(url):
    if not url:
        return False

    value = url.lower().split("?")[0]

    return value.endswith(
        (
            ".mp4",
            ".webm",
            ".mov",
            ".m4v"
        )
    )


def is_hls_url(url):
    if not url:
        return False

    return ".m3u8" in url.lower()


# ============================================================
# GOOGLE NEWS

# ============================================================

VERY_IMPORTANT_KEYWORDS = [
    "خبر فوری",
    "فوری",
    "انفجار",
    "حمله",
    "جنگ",
    "موشک",
    "حمله موشکی",
    "زلزله",
    "سیل",
    "آتش سوزی",
    "آتش‌سوزی",
    "هواپیما",
    "سقوط",
    "کشته",
    "مفقود",
    "ترور",
    "تحریم",
    "هسته ای",
    "هسته‌ای",
    "مذاکرات",
    "آتش بس",
    "آتش‌بس",
    "قطعی اینترنت",
    "قطع اینترنت",
]


IMPORTANT_KEYWORDS = [
    "ایران",
    "تهران",
    "دلار",
    "طلا",
    "سکه",
    "بورس",
    "اقتصاد",
    "قیمت",
    "بنزین",
    "نفت",
    "برق",
    "گاز",
    "هوش مصنوعی",
    "فناوری",
    "موبایل",
    "خودرو",
    "فوتبال",
    "ورزش",
    "پزشکی",
    "سلامت",
    "دانشگاه",
    "مدرسه",
    "جهان",
    "آمریکا",
    "اروپا",
    "اسرائیل",
    "روسیه",
    "اوکراین",
    "چین",
]

# Important-news rescue: the normal feed window stays 30 minutes, but
# high-impact stories are allowed a short grace period so delayed RSS
# timestamps cannot silently discard major events before intelligence scoring.
IMPORTANT_NEWS_RESCUE_MAX_AGE_MINUTES = 360

IMPORTANT_RESCUE_PATTERNS = [
    "جنگ", "حمله", "حمله موشکی", "بمباران", "انفجار", "زلزله", "سیل",
    "سونامی", "طوفان", "رانش زمین", "سقوط هواپیما", "سقوط بالگرد",
    "کشته", "کشته شد", "زخمی", "مفقود", "ترور", "تیراندازی", "بازداشت",
    "موشک", "پرتابه", "درگیری نظامی", "عملیات نظامی", "آتش بس", "آتش‌بس",
    "تحریم", "قطع اینترنت", "اختلال گسترده", "قطع برق", "قطع گاز",
    "مذاکرات", "توافق", "فراخوان", "فوری",
    "attack", "strike", "missile", "bombing", "explosion", "earthquake",
    "flood", "tsunami", "storm", "landslide", "crash", "killed", "wounded",
    "shooting", "military", "ceasefire", "sanction", "internet outage",
]


def is_important_news_rescue_candidate(title):
    """Return True when a slightly stale RSS item is still worth intelligence scoring."""
    value = normalize_space(title).lower()
    if not value:
        return False
    hits = sum(1 for pattern in IMPORTANT_RESCUE_PATTERNS if pattern.lower() in value)
    return hits >= 1



# ============================================================
# SOURCE QUALITY

# ============================================================

HIGH_QUALITY_HOSTS = {
    "irna.ir",
    "isna.ir",
    "mehrnews.com",
    "yjc.ir",
    "zoomit.ir",
    "tasnimnews.com",
    "farsnews.ir",
    "snn.ir",
    "tabnak.ir",
    "tejaratnews.com",
    "donya-e-eqtesad.com",
    "ecoiran.com",
    "varzesh3.com",
    "bbc.com",
    "reuters.com",
    "apnews.com",
    "aljazeera.com",
    "euronews.com",
    "variety.com",
}


MEDIUM_QUALITY_HOSTS = {
    "israelhayom.com",
    "theguardian.com",
    "nytimes.com",
    "washingtonpost.com",
    "cnn.com",
    "dw.com",
}


def publisher_quality(url):
    host = base_domain(
        get_hostname(url)
    )

    if not host:
        return 0

    if is_social_host(url):
        return -40

    if is_google_host(url):
        return -50

    for domain in HIGH_QUALITY_HOSTS:

        if (
            host == domain
            or host.endswith("." + domain)
        ):
            return 25

    for domain in MEDIUM_QUALITY_HOSTS:

        if (
            host == domain
            or host.endswith("." + domain)
        ):
            return 15

    return 5



# ============================================================
# IRANIAN PUBLISHER SCOPE

# ============================================================

ROUNDUP_PATTERNS = [
    r"چه خبر",
    r"مرور مهمترین",
    r"مهم‌ترین اخبار",
    r"مهمترین اخبار",
    r"اخبار مهم امروز",
    r"اخبار مهم",
    r"آخرین اخبار",
    r"بسته خبری",
    r"مرور اخبار",
    r"در این گزارش",
    r"اخبار روز",
    r"چند خبر",
    r"نگاهی به اخبار",
]


def is_roundup_title(title):
    if not title:
        return False

    title = normalize_space(
        title
    )

    for pattern in ROUNDUP_PATTERNS:

        if re.search(
            pattern,
            title,
            re.I
        ):
            return True

    return False


# ============================================================
# SOURCE CLEANING

# ============================================================

SOURCE_PHRASES = [
    "به گزارش خبرنگار مهر",
    "به گزارش مهر",
    "به گزارش ایسنا",
    "به گزارش ایرنا",
    "به گزارش خبرنگار ایرنا",
    "به گزارش خبرنگار ایسنا",
    "به گزارش یزدانه",
    "به گزارش باشگاه خبرنگاران جوان",
    "به گزارش خبرنگار باشگاه خبرنگاران جوان",
    "به گزارش خبرنگار",
    "به نقل از",
    "در گفت‌وگو با",
    "در گفتگو با",
    "طبق اعلام",
    "بر اساس اعلام",
    "براساس اعلام",
]


def clean_content(text):
    if not text:
        return ""

    text = BeautifulSoup(
        str(text),
        "html.parser"
    ).get_text(" ")

    text = normalize_space(
        text
    )

    # Remove a leading reporter/byline fragment such as
    # "سید محمدعلی سجادی - سرهنگ کاظمی رئیس پلیس راه ...".
    # This is deliberately limited to a short leading fragment followed by
    # an attribution/official-role phrase, so ordinary factual sentences
    # are not accidentally truncated.
    text = re.sub(
        r"^[^|،؛.!؟]{2,60}\s*[-–—]\s*(?="
        r"(?:سرهنگ|سردار|سرتیپ|رئیس|مدیر|فرمانده|استاندار|وزیر|معاون|"
        r"نماینده|سخنگو|مسئول|او\s+افزود|وی\s+افزود|وی\s+گفت|"
        r"گفت|افزود|اظهار\s+کرد|اعلام\s+کرد)"
        r")",
        "",
        text,
        count=1,
        flags=re.I
    )

    text = re.sub(
        r"^(مشهد|تهران|قم|تبریز|اصفهان|شیراز|کرج|اهواز|بغداد|واشنگتن|لندن)"
        r"\s*[-–—:]\s*",
        "",
        text,
        flags=re.I
    )

    for phrase in SOURCE_PHRASES:

        text = text.replace(
            phrase,
            ""
        )

    # Remove publisher/navigation boilerplate that can leak from broad
    # webpage containers (for example Digiato's membership and navigation
    # blocks). These are not article facts and must never reach the AI.
    BOILERPLATE_PHRASES = [
        "عضویت در دیجیاتو",
        "دیجیاتو را در گوگل بیشتر ببینید",
        "در دیجیاتو ثبت نام کنید",
        "جهت بهره مندی و دسترسی به امکانات ویژه",
        "عضو ویژه دیجیاتو شوید",
        "کپی لینک",
        "عضویت در خبرنامه",
        "اشتراک گذاری",
        "مطالب مرتبط",
        "بیشتر بخوانید",
        "آخرین اخبار",
    ]

    for phrase in BOILERPLATE_PHRASES:
        text = text.replace(phrase, " ")

    # Strip common byline/date fragments that are page chrome rather than
    # the article body. Keep dates that are actually part of a sentence.
    text = re.sub(
        r"\b(?:منتشر شده در|نوشته شده در)\s+"
        r"[^|]{0,100}?\s*\d{1,2}\s+"
        r"(?:فروردین|اردیبهشت|خرداد|تیر|مرداد|شهریور|مهر|آبان|آذر|دی|بهمن|اسفند)"
        r"\s+\d{4}\s*\|?\s*\d{1,2}:\d{2}",
        " ",
        text,
        flags=re.I
    )

    text = re.sub(
        r"\b(?:مرتضی قانع|نویسنده)\b",
        " ",
        text,
        flags=re.I
    )

    text = re.sub(
        r"\s+#?[A-Za-z0-9_]+\s*$",
        "",        text
    )

    text = re.sub(
        r"\b(ایرنا|ایسنا|مهر|باشگاه خبرنگاران جوان|خبرگزاری)"
        r"\s*[:：-]",
        "",
        text,
        flags=re.I
    )

    text = re.sub(
        r"\+\s*(فیلم|ویدئو|ویدیو|عکس|تصاویر)\s*$",
        "",
        text,
        flags=re.I
    )

    text = normalize_space(
        text
    )

    return text[:6000]


# ============================================================
# TITLE CLEANING

# ============================================================

def clean_title(title):
    if not title:
        return ""

    title = BeautifulSoup(
        str(title),
        "html.parser"
    ).get_text(" ")

    title = normalize_space(
        title
    )

    title = re.sub(
        r"\s*[-|]\s*"
        r"(facebook\.com|twitter\.com|x\.com|youtube\.com)"
        r"\s*$",
        "",
        title,
        flags=re.I
    )

    title = re.sub(
        r"\s+-\s+[A-Za-z0-9._-]+\.[A-Za-z]{2,}$",
        "",
        title
    )

    title = re.sub(
        r"^(ایرنا|ایسنا|مهر|فارس|تسنیم|یعنی چه|باشگاه خبرنگاران جوان)"
        r"\s*[-|:：]\s*",
        "",
        title,
        flags=re.I
    )

    title = re.sub(
        r"\s*\+\s*(فیلم|ویدئو|ویدیو|عکس|تصاویر)\s*$",
        "",
        title,
        flags=re.I
    )

    title = strip_unbacked_media_labels(title)

    return normalize_space(
        title
    )[:180]


# ============================================================
# MEDIA CLAIM CONSISTENCY

# ============================================================

def strip_unbacked_media_labels(text):
    """Remove false video labels when no video is actually published."""
    value = normalize_space(str(text or ""))
    if not value:
        return ""
    patterns = (
        r"^\s*(?:🎬\s*)?(?:فیلم|ویدئو|ویدیو)\s*[/|:：-]\s*",
        r"^\s*[/|:：-]+\s*(?:فیلم|ویدئو|ویدیو)\s*[/|:：-]\s*",
        r"\s*[+＋]\s*(?:فیلم|ویدئو|ویدیو)\s*$",
        r"\s*[-|]\s*(?:فیلم|ویدئو|ویدیو)\s*$",
        r"\[\s*(?:فیلم|ویدئو|ویدیو)\s*\]\s*",
    )
    for pattern in patterns:
        value = re.sub(pattern, " ", value, flags=re.I)
    value = re.sub(r"^\s*[/|:：-]+\s*", "", value)
    return normalize_space(value)


def media_consistent_text(text, has_video=False):
    """Media claims are allowed only when a real video is actually published."""
    value = normalize_space(str(text or ""))
    if not value:
        return ""

    if has_video:
        return value

    value = strip_unbacked_media_labels(value)

    # Remove standalone sentences that claim a video exists. This catches
    # AI/source summaries such as "فیلم این حادثه منتشر شد" even when the
    # headline itself contains no media marker.
    sentences = re.split(r"(?<=[.!؟?؛])\s+|\n+", value)
    kept = []
    for sentence in sentences:
        sentence = normalize_space(sentence)
        if not sentence:
            continue
        if re.search(r"(?:فیلم|ویدئو|ویدیو)", sentence, flags=re.I):
            continue
        kept.append(sentence)

    return normalize_space(" ".join(kept))


# ============================================================
# SENTENCE HELPERS

# ============================================================

def split_sentences(text):
    if not text:
        return []

    text = normalize_space(
        text
    )

    parts = re.split(
        r"(?<=[\.\!\؟\?؛])\s+",
        text
    )

    result = []

    for item in parts:

        item = normalize_space(
            item
        )

        if len(item) >= 15:
            result.append(
                item
            )

    return result


def sentence_score(sentence):
    score = 0

    for word in VERY_IMPORTANT_KEYWORDS:

        if word in sentence:
            score += 4

    for word in IMPORTANT_KEYWORDS:

        if word in sentence:
            score += 2

    if any(
        x in sentence
        for x in [
            "اعلام کرد",
            "گفت",
            "تصمیم",
            "تصویب",
            "تأیید"
        ]
    ):
        score += 1

    return score


def enforce_short_summary(text):
    text = clean_content(
        text
    )

    if not text:
        return ""

    sentences = split_sentences(
        text
    )

    if not sentences:
        return text[:600].strip()

    selected = [
        sentences[0]
    ]

    remaining = sorted(
        sentences[1:],
        key=sentence_score,
        reverse=True
    )

    for sentence in remaining:

        if len(selected) >= 3:
            break

        candidate = " ".join(
            selected + [sentence]
        )

        if len(candidate) <= 600:
            selected.append(
                sentence
            )

    return " ".join(
        selected
    )[:600].strip()


# ============================================================
# HISTORY

# ============================================================

STOPWORDS = {
    "از",
    "به",
    "در",
    "با",
    "برای",
    "و",
    "که",
    "را",
    "این",
    "آن",
    "یک",
    "شد",
    "شدند",
    "کرد",
    "کرده",
    "است",
    "هست",
    "می",
    "شود",
    "خواهد",
    "خبر",
    "گزارش",
    "اعلام",
    "جدید",
    "مهم",
    "آخرین",
    "درباره",
    "مورد",
    "پس",
    "نیز",
    "اما",
    "هم",
    "تا",
    "بر",
    "های",
    "ها",
}


GENERIC_NEWS_WORDS = {
    "خبر",
    "گزارش",
    "اعلام",
    "آخرین",
    "جدید",
    "مهم",
    "ادعا",
    "مدعی",
    "تصمیم",
    "تازه",
    "جزئیات",
    "واکنش",
    "اظهارات",
    "مواضع",
    "توضیح",
    "انتقاد",
    "تأکید",
    "تاکید",
    "خبرگزاری",
    "تحلیل",
    "تحلیلگر",
    "گفت",
    "گفتند",
    "عنوان",
    "رونمایی",
    "انتشار",
}


def title_tokens(title):

    title = normalize_digits(
        title
    )

    title = clean_title(
        title
    ).lower()

    title = re.sub(
        r"[^\w\u0600-\u06ff]+",
        " ",
        title
    )

    tokens = set()

    for token in title.split():

        token = token.strip()

        if len(token) < 2:
            continue

        if token in STOPWORDS:
            continue

        tokens.add(
            token
        )

    return tokens


def story_tokens(title):

    tokens = title_tokens(
        title
    )

    return {
        x
        for x in tokens
        if x not in GENERIC_NEWS_WORDS
    }


def title_similarity(a, b):

    A = title_tokens(a)
    B = title_tokens(b)

    if not A or not B:
        return 0

    intersection = len(
        A & B
    )

    union = len(
        A | B
    )

    if union == 0:
        return 0

    return (
        intersection
        / union
    )


def story_similarity(a, b):

    A = story_tokens(a)
    B = story_tokens(b)

    if not A or not B:

        return title_similarity(
            a,
            b
        )

    intersection = len(
        A & B
    )

    if intersection == 0:
        return 0

    union = len(
        A | B
    )

    jaccard = (
        intersection
        / union
    )

    containment = (
        intersection
        / min(
            len(A),
            len(B)
        )
    )

    return (
        jaccard * 0.45
        + containment * 0.55
    )


def numeric_anchors(text):
    """
    Numbers often identify the same event:
    15 نفر, 2-0, F-15, 1405, 49%, etc.
    """

    text = normalize_digits(
        text
    )

    found = re.findall(
        r"\b\d+(?:[.,]\d+)?\b",
        text
    )

    return set(
        found
    )


def _high_confidence_event_duplicate(title_a, title_b):
    """Catch the same high-impact event when media/title wording differs."""
    a = normalize_space(title_a).lower()
    b = normalize_space(title_b).lower()
    event_groups = (
        (
            ("شورای عالی امنیت ملی", "supreme national security council"),
            ("محدودیت های هوایی", "محدودیت‌های هوایی", "محدودیت هوایی"),
            ("اقدام نظامی", "مقابله به مثل نظامی", "مقابله‌به‌مثل نظامی"),
        ),
        (
            ("تنگه هرمز", "هرمز"),
            ("بازگشایی", "باز شود", "بازگشایی فوری", "reopen", "reopening"),
            ("پیشنهاد ایران", "iran proposal", "پیشنهاد تهران"),
        ),
    )
    for groups in event_groups:
        hits_a = sum(any(x in a for x in group) for group in groups)
        hits_b = sum(any(x in b for x in group) for group in groups)
        if hits_a >= 2 and hits_b >= 2:
            return True
    return False


def same_story(a, b):

    title_a = clean_title(
        a.get(
            "title",
            ""
        )
    )

    title_b = clean_title(
        b.get(
            "title",
            ""
        )
    )

    if not title_a or not title_b:
        return False

    # High-confidence event signatures survive title rewrites and media changes.
    # This prevents one event from being posted once as photo and again as text.
    if _high_confidence_event_duplicate(title_a, title_b):
        return True

    # Exact normalized title.
    if (
        normalize_space(
            title_a
        ).lower()
        ==
        normalize_space(
            title_b
        ).lower()
    ):
        return True

    similarity = story_similarity(
        title_a,
        title_b
    )

    title_sim = title_similarity(
        title_a,
        title_b
    )

    A = story_tokens(
        title_a
    )

    B = story_tokens(
        title_b
    )

    common = A & B

    # Very high similarity.
    if similarity >= 0.72:
        return True

    # High token overlap.
    if (
        len(common) >= 4
        and similarity >= 0.50
    ):
        return True

    # Short titles.
    if (
        len(A) <= 3
        or len(B) <= 3
    ):

        if title_sim >= 0.80:
            return True

    # Numeric anchors strengthen a moderate match.
    nums_a = numeric_anchors(
        title_a
    )

    nums_b = numeric_anchors(
        title_b
    )

    common_numbers = (
        nums_a & nums_b
    )

    if (
        common_numbers
        and similarity >= 0.45
        and len(common) >= 3
    ):
        return True

    # Strong event-anchor duplicate guard. Different publishers often phrase
    # the same breaking event very differently (e.g. "students injured" vs
    # "11 killed and wounded"). If a concrete event/location pair and the same
    # numeric casualty count are present, treat it as the same story even when
    # generic token similarity is below the normal threshold.
    event_anchors = (
        "تیراندازی", "انفجار", "زلزله", "سیل", "سونامی", "طوفان",
        "حمله", "حملات", "درگیری", "سقوط", "آتش سوزی", "آتش‌سوزی",
        "shooting", "explosion", "earthquake", "flood", "tsunami",
        "typhoon", "attack", "strike", "crash", "fire",
    )
    location_anchors = (
        "ترکیه", "اوکراین", "روسیه", "ژاپن", "ایران", "عربستان",
        "آمریکا", "آمریکا", "اسرائیل", "یمن", "لبنان",
        "turkey", "ukraine", "russia", "japan", "iran", "saudi",
        "america", "israel", "yemen", "lebanon",
    )
    event_a = {x for x in event_anchors if x in title_a.lower()}
    event_b = {x for x in event_anchors if x in title_b.lower()}
    loc_a = {x for x in location_anchors if x in title_a.lower()}
    loc_b = {x for x in location_anchors if x in title_b.lower()}
    if (
        common_numbers
        and (event_a & event_b)
        and (loc_a & loc_b)
    ):
        return True

    return False


def history_contains_story(
    title,
    title_history
):

    if not title:
        return False

    now = int(
        datetime.now(
            timezone.utc
        ).timestamp()
    )

    cutoff = (
        now
        - int(
            SEMANTIC_HISTORY_DAYS
            * 86400
        )
    )

    for timestamp, old_title in title_history:

        if timestamp < cutoff:
            continue

        if same_story(
            {"title": title},
            {"title": old_title}
        ):
            return True

    return False


def record_semantic_history(
    title,
    title_history
):

    title = clean_title(
        title
    )

    if not title:
        return

    # Avoid storing an immediate exact duplicate.
    for _, old_title in title_history[-20:]:

        if (
            normalize_space(
                old_title
            ).lower()
            ==
            normalize_space(
                title
            ).lower()
        ):
            return

    title_history.append(
        (
            int(
                datetime.now(
                    timezone.utc
                ).timestamp()
            ),
            title
        )
    )


# ============================================================
# DATE / FRESHNESS

# ============================================================

def parse_entry_time(entry):

    try:

        parsed = (
            entry.get(
                "published_parsed"
            )
            or entry.get(
                "updated_parsed"
            )
        )
        if parsed:

            return datetime(
                parsed.tm_year,
                parsed.tm_mon,
                parsed.tm_mday,
                parsed.tm_hour,
                parsed.tm_min,
                parsed.tm_sec,
                tzinfo=timezone.utc
            )

    except Exception:
        pass

    return None


def is_fresh(
    published_at
):

    if not published_at:
        return True

    try:

        now = datetime.now(
            timezone.utc
        )

        age_hours = (
            now - published_at
        ).total_seconds() / 3600

        if age_hours < 0:
            return True

        return (
            age_hours
            <= MAX_NEWS_AGE_HOURS
        )

    except Exception:
        return True


def calculate_recency_score(dt):

    if not dt:
        return 0

    try:

        now = datetime.now(
            timezone.utc
        )

        age_hours = (
            now - dt
        ).total_seconds() / 3600

        if age_hours < 1:
            return 12

        if age_hours < 3:
            return 10

        if age_hours < 6:
            return 8

        if age_hours < 12:
            return 5

        if age_hours < 24:
            return 3

        if age_hours <= 36:
            return 1

    except Exception:
        pass

    return 0


# ============================================================
# IMPORTANCE

# ============================================================

def calculate_keyword_importance(
    title,
    body
):

    text = f"{title} {body}"

    score = 0

    for word in VERY_IMPORTANT_KEYWORDS:

        if word in text:
            score += 8

    for word in IMPORTANT_KEYWORDS:

        if word in text:
            score += 3

    # Major international events must compete fairly with local stories
    # even when the source/headline is in English.
    if _has_global_high_impact(text):
        score += 14

    return min(
        score,
        55
    )


def source_priority(
    url,
    is_google=False
):

    score = publisher_quality(
        url
    )

    if is_google:
        score -= 10

    return score


def calculate_importance(
    candidate
):

    title = candidate.get(
        "title",
        ""
    )

    body = candidate.get(
        "summary",
        ""
    )

    score = 0

    score += calculate_keyword_importance(
        title,
        body
    )

    score += calculate_recency_score(
        candidate.get(
            "published_at"
        )
    )

    score += source_priority(
        candidate.get(
            "link",
            ""
        ),
        candidate.get(
            "is_google",
            False
        )
    )

    if candidate.get(
        "video_url"
    ):
        score += 3

    if candidate.get(
        "image_url"
    ):
        score += 2

    # Only count resolved_link if it is
    # actually a publisher article.
    resolved = candidate.get(
        "resolved_link",
        ""
    )

    if (
        resolved
        and not is_google_host(
            resolved
        )
        and not is_social_host(
            resolved
        )
    ):
        score += 8

    if is_social_host(
        candidate.get(
            "link",
            ""
        )
    ):
        score -= 30

    if is_google_host(
        candidate.get(
            "link",
            ""
        )
    ):
        score -= 20

    if is_roundup_title(
        title
    ):
        score -= 25

    if candidate.get(
        "cluster_size",
        1
    ) >= 2:

        score += min(
            candidate[
                "cluster_size"
            ],
            4
        ) * 2

    return score


# ============================================================
# GOOGLE NEWS RESOLUTION

def _has_global_high_impact(text):
    """True for objectively high-impact global events used by Google fallback."""
    value = normalize_space(str(text or "")).lower()
    if not value:
        return False
    critical = (
        "war", "conflict", "ceasefire", "invasion", "missile", "airstrike",
        "bombing", "explosion", "earthquake", "tsunami", "hurricane",
        "wildfire", "mass shooting", "hostage", "terror attack", "nuclear",
        "sanction", "tariff", "strait of hormuz", "airspace", "nationwide outage",
        "emergency", "evacuation", "کشته", "زخمی", "انفجار", "زلزله", "سیل",
        "حمله", "جنگ", "درگیری", "موشک", "بمباران", "آتش‌بس", "تحریم",
        "تعرفه", "هسته‌ای", "تنگه هرمز", "وضعیت اضطراری", "تخلیه",
    )
    actors = (
        "iran", "united states", "u.s.", "china", "russia", "ukraine",
        "israel", "nato", "united nations", "un general assembly",
        "آمریکا", "ایران", "چین", "روسیه", "اوکراین", "اسرائیل",
        "ناتو", "سازمان ملل", "مجمع عمومی",
    )
    def hit(term):
        if any("\u0600" <= ch <= "\u06ff" for ch in term):
            return term in value
        return bool(re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", value, re.I))
    return any(hit(x) for x in critical) and any(hit(x) for x in actors)


def _is_telemetry_or_tracking_url(url):
    """Reject analytics/tracking endpoints during Google News resolution."""
