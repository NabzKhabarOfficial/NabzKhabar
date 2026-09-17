"""High-confidence semantic event deduplication for rewritten news reports."""

import re
import main

_ORIGINAL_SAME_STORY = main.same_story

GENERIC = {
    "خبر", "گزارش", "اعلام", "اعلامیه", "جنجال", "سیاسی", "مهم", "جدید", "تازه",
    "واکنش", "اظهارات", "مواضع", "تاکید", "تأکید", "گفت", "گفتند", "کرد", "کردند",
    "شد", "شدند", "خواهد", "می", "شود", "است", "هست", "این", "آن", "یک", "از",
    "به", "در", "با", "برای", "و", "که", "را", "تا", "بر", "های", "ها", "هم",
    "نیز", "مورد", "درباره", "پس", "پس از", "در پی", "خبرگزاری", "منابع", "افراد",
    "سازندگان", "کارگردانان", "کارگردان", "خانواده", "فیلم", "مستند", "تهدید", "تهدیدها",
    "مواجه", "شده اند", "شدهاند", "اسرائیل", "اسرائيل",
}

# High-signal aliases. They let different Persian spellings describe the same entity.
ALIASES = {
    "اسرائيل": "اسرائیل",
    "نتانیاهو": "نتانیاهو",
    "بنیامین نتانیاهو": "نتانیاهو",
    "نِزا": "نازا",
    "نزا": "نازا",
    "نازا": "نازا",
    "نزا": "نازا",
    "غزه": "غزه",
    "غزّه": "غزه",
    "تل آویو": "تل آویو",
    "تل‌آویو": "تل آویو",
}


def _norm(text):
    text = main.normalize_digits(str(text or "")).lower()
    text = text.replace("ي", "ی").replace("ى", "ی").replace("ك", "ک")
    text = re.sub(r"[\u064B-\u065F\u0670\u06D6-\u06ED]", "", text)
    text = text.replace("‌", " ")
    text = re.sub(r"[\u200b-\u200f\ufeff]", " ", text)
    text = re.sub(r"[،؛,:.!؟()\[\]{}\"'«»/\\|_–—-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    for src, dst in sorted(ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
        text = re.sub(rf"(?<!\S){re.escape(src)}(?!\S)", dst, text)
    return text


def _tokens(text):
    return {x for x in _norm(text).split() if len(x) >= 3 and x not in GENERIC}


def _anchors(text):
    t = _norm(text)
    anchors = set()
    # Named entities / distinctive event anchors. Only use groups when explicitly present.
    groups = {
        "نتانیاهو": ("نتانیاهو", "بنیامین نتانیاهو"),
        "ترامپ": ("ترامپ", "دونالد ترامپ"),
        "پزشکیان": ("پزشکیان", "مسعود پزشکیان"),
        "پوتین": ("پوتین", "ولادیمیر پوتین"),
        "زلنسکی": ("زلنسکی", "ولودیمیر زلنسکی"),
        "نازا": ("نازا", "نزا", "نِزا"),
        "غزه": ("غزه", "غزّه"),
        "اسرائیل": ("اسرائیل", "اسرائيل"),
        "ایران": ("ایران"),
        "آمریکا": ("آمریکا", "امریکا", "ایالات متحده"),
        "عربستان": ("عربستان", "عربستان سعودی"),
        "اوکراین": ("اوکراین"),
        "روسیه": ("روسیه"),
    }
    for canonical, variants in groups.items():
        if any(_norm(v) in t for v in variants):
            anchors.add(canonical)
    return anchors


def _event_signature(candidate):
    title = main.clean_title(candidate.get("title", ""))
    body = candidate.get("summary", "") or candidate.get("description", "") or ""
    combined = _norm(f"{title} {body}")
    return title, combined, _tokens(combined), _anchors(combined)


def semantic_same_event(a, b):
    ta, ca, tokens_a, anchors_a = _event_signature(a)
    tb, cb, tokens_b, anchors_b = _event_signature(b)
    if not ta or not tb:
        return False

    # Preserve the existing, well-tested rules first.
    try:
        if _ORIGINAL_SAME_STORY(a, b):
            return True
    except Exception:
        pass

    shared_anchors = anchors_a & anchors_b
    common = tokens_a & tokens_b
    if not common:
        return False

    # A distinctive named event/entity plus enough shared context is a strong duplicate signal.
    if len(shared_anchors) >= 2 and len(common) >= 3:
        return True

    # One distinctive anchor (e.g. a film/event name) plus two contextual anchors
    # catches rewritten reports while avoiding generic topic matches.
    if len(shared_anchors) >= 1:
        distinctive = {x for x in common if len(x) >= 4}
        if len(distinctive) >= 4:
            return True

    # High token containment catches close rewrites even when word order changes.
    containment = len(common) / max(1, min(len(tokens_a), len(tokens_b)))
    jaccard = len(common) / max(1, len(tokens_a | tokens_b))
    if len(common) >= 5 and containment >= 0.62 and jaccard >= 0.32:
        return True

    return False


main.same_story = semantic_same_event
print("Semantic event dedup patch active")
