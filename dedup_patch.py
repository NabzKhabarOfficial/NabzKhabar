"""Stronger duplicate guard + Breaking News layer for NabzKhabar.

This module is imported by the GitHub Actions runner before main.main().
It monkey-patches the existing engine instead of rewriting main.py, keeping
its current architecture, schedules and state format intact.
"""

import re
import main


GENERIC = {
    "خبر", "گزارش", "اعلام", "آخرین", "جدید", "مهم", "تازه", "جزئیات",
    "واکنش", "اظهارات", "مواضع", "توضیح", "انتقاد", "تاکید", "تأکید",
    "گفت", "گفتند", "کرد", "کردند", "شد", "شدند", "خواهد", "می", "شود",
    "است", "هست", "این", "آن", "یک", "از", "به", "در", "با", "برای", "و",
    "که", "را", "تا", "بر", "های", "ها", "هم", "نیز", "مورد", "درباره",
    "درخواست", "دیدار", "سخنان", "مقامات", "مقام", "کشور", "منطقه", "شهر",
    "استان", "رئیس", "وزیر", "وزارت", "دولت",
}


def _norm(text):
    text = main.normalize_digits(str(text or "")).lower()
    text = (
        text.replace("ي", "ی")
        .replace("ى", "ی")
        .replace("ك", "ک")
        .replace("ة", "ه")
    )
    text = re.sub(r"[\u200b-\u200f\ufeff]", " ", text)
    text = re.sub(r"[،؛,:.!؟()\[\]{}\"'«»/\\|_–—-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokens(text):
    return {
        token
        for token in _norm(text).split()
        if len(token) >= 2 and token not in GENERIC
    }


def _numbers(text):
    return set(
        re.findall(
            r"\d+(?:[.,٬]\d+)*",
            main.normalize_digits(str(text or "")),
        )
    )


def strong_same_story(a, b):
    """Catch paraphrased headlines that describe the same story."""
    title_a = main.clean_title(a.get("title", ""))
    title_b = main.clean_title(b.get("title", ""))

    if not title_a or not title_b:
        return False

    if _norm(title_a) == _norm(title_b):
        return True

    tokens_a = _tokens(title_a)
    tokens_b = _tokens(title_b)
    common = tokens_a & tokens_b

    if not tokens_a or not tokens_b:
        return False

    jaccard = len(common) / len(tokens_a | tokens_b)
    containment = len(common) / min(len(tokens_a), len(tokens_b))

    # Strong overlap: different wording, same core entities.
    if len(common) >= 4 and containment >= 0.60:
        return True

    if len(common) >= 5 and jaccard >= 0.32:
        return True

    # A shared number is a strong event anchor.
    common_numbers = _numbers(title_a) & _numbers(title_b)
    if common_numbers and len(common) >= 2 and jaccard >= 0.25:
        return True

    # Several distinctive long words shared between headlines.
    long_common = [word for word in common if len(word) >= 4]
    if len(long_common) >= 3 and containment >= 0.50:
        return True

    return False


# The existing pipeline calls same_story in clustering, current-run selection,
# and history checks. Replacing this single function strengthens all of them.
main.same_story = strong_same_story


def strong_same_event(a_title, a_body, b_title, b_body):
    return strong_same_story(
        {"title": f"{a_title} {a_body}"},
        {"title": f"{b_title} {b_body}"},
    )


main.same_event = strong_same_event


# ============================================================
# BREAKING NEWS ENGINE
# ============================================================

# These terms are intentionally narrower than the normal importance list.
# The goal is to surface genuinely time-sensitive events without turning
# every important headline into a breaking alert.
BREAKING_TERMS = {
    "خبر فوری": 8,
    "فوری": 7,
    "لحظاتی پیش": 7,
    "همین حالا": 7,
    "دقایقی پیش": 7,
    "انفجار": 6,
    "حمله موشکی": 6,
    "حمله": 5,
    "موشک": 5,
    "زلزله": 6,
    "سونامی": 6,
    "سقوط هواپیما": 7,
    "سقوط": 5,
    "آتش سوزی": 5,
    "آتش‌سوزی": 5,
    "کشته": 5,
    "مفقود": 5,
    "ترور": 6,
    "درگیری": 5,
    "جنگ": 5,
    "آتش بس": 5,
    "آتش‌بس": 5,
    "قطع اینترنت": 5,
    "قطعی اینترنت": 5,
    "خاموشی گسترده": 5,
    "وضعیت فوق العاده": 6,
    "وضعیت فوق‌العاده": 6,
    "تخلیه": 5,
    "هشدار فوری": 7,
}


def breaking_signal(candidate):
    """Return (score, is_breaking) for a fresh time-sensitive story."""
    title = main.clean_title(candidate.get("title", ""))
    body = main.clean_content(candidate.get("summary", ""))
    title_norm = _norm(title)
    body_norm = _norm(body)

    score = 0
    title_hits = 0
    body_hits = 0

    for term, weight in BREAKING_TERMS.items():
        term_norm = _norm(term)
        if term_norm and term_norm in title_norm:
            score += weight
            title_hits += 1
        elif term_norm and term_norm in body_norm:
            score += max(1, weight // 2)
            body_hits += 1

    # Recency is mandatory for the breaking classification.
    recency = main.calculate_recency_score(candidate.get("published_at"))
    cluster_size = int(candidate.get("cluster_size", 1) or 1)

    if recency >= 12:
        score += 5
    elif recency >= 10:
        score += 3
    elif recency >= 8:
        score += 1
    else:
        score -= 4

    # Independent publishers reporting the same event is a useful signal.
    if cluster_size >= 2:
        score += min(cluster_size, 4) * 2

    # A title hit is much stronger than a body-only hit.
    is_breaking = (
        recency >= 8
        and (
            score >= 10
            or (title_hits >= 1 and cluster_size >= 2 and score >= 8)
        )
    )

    # A very explicit emergency phrase can break through even before a second
    # publisher has picked it up, provided the article is genuinely fresh.
    explicit_urgent = any(
        phrase in title_norm
        for phrase in (
            "خبر فوری",
            "لحظاتی پیش",
            "دقایقی پیش",
            "همین حالا",
            "هشدار فوری",
        )
    )

    if explicit_urgent and recency >= 8 and title_hits >= 1:
        is_breaking = True

    return max(score, 0), is_breaking


_original_hot_news_signal = main.calculate_hot_news_signal
_original_calculate_importance = main.calculate_importance


def enhanced_hot_news_signal(candidate):
    score, is_breaking = breaking_signal(candidate)
    candidate["breaking_score"] = score
    candidate["is_breaking"] = is_breaking

    # Keep the existing hot-news rules as a safety net; breaking news is an
    # additional path, not a replacement. This prevents the new layer from
    # making the 5-minute hot lane more restrictive.
    return bool(_original_hot_news_signal(candidate) or is_breaking)


def enhanced_calculate_importance(candidate):
    score = _original_calculate_importance(candidate)
    breaking_score, is_breaking = breaking_signal(candidate)

    candidate["breaking_score"] = breaking_score
    candidate["is_breaking"] = is_breaking

    if is_breaking:
        # Strong priority boost for urgent stories in both hot and normal lanes.
        score += 25

    return score


main.calculate_hot_news_signal = enhanced_hot_news_signal
main.calculate_importance = enhanced_calculate_importance
