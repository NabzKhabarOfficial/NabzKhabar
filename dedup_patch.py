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

    if len(common) >= 4 and containment >= 0.60:
        return True

    if len(common) >= 5 and jaccard >= 0.32:
        return True

    common_numbers = _numbers(title_a) & _numbers(title_b)
    if common_numbers and len(common) >= 2 and jaccard >= 0.25:
        return True

    long_common = [word for word in common if len(word) >= 4]
    if len(long_common) >= 3 and containment >= 0.50:
        return True

    return False


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

# Events that are important but are normally not "breaking" merely because
# they are newly published: ceremonies, memorials, funerals and photo reports.
NON_BREAKING_CEREMONY_TERMS = {
    "تشییع", "تشییع پیکر", "تدفین", "خاکسپاری", "مراسم تشییع",
    "مراسم", "وداع", "سوگواری", "گلزار شهدا", "پیکر", "تصاویر",
    "عکس", "گزارش تصویری", "یادبود", "گرامیداشت",
}


def _is_ceremony_story(title, body):
    text = _norm(f"{title} {body}")
    return any(_norm(term) in text for term in NON_BREAKING_CEREMONY_TERMS)


def breaking_signal(candidate):
    """Return (score, is_breaking) for genuinely time-sensitive stories."""
    title = main.clean_title(candidate.get("title", ""))
    body = main.clean_content(candidate.get("summary", ""))
    title_norm = _norm(title)
    body_norm = _norm(body)

    score = 0
    title_hits = 0

    for term, weight in BREAKING_TERMS.items():
        term_norm = _norm(term)
        if term_norm and term_norm in title_norm:
            score += weight
            title_hits += 1
        elif term_norm and term_norm in body_norm:
            score += max(1, weight // 2)

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

    if cluster_size >= 2:
        score += min(cluster_size, 4) * 2

    explicit_urgent = any(
        phrase in title_norm
        for phrase in (
            "خبر فوری", "لحظاتی پیش", "دقایقی پیش", "همین حالا", "هشدار فوری",
        )
    )

    # A ceremony/photo report is not breaking unless the headline itself has
    # an explicit urgent marker. This prevents ordinary funeral/photo stories
    # from receiving breaking treatment just because they are fresh.
    if _is_ceremony_story(title, body) and not explicit_urgent:
        return 0, False

    is_breaking = (
        recency >= 8
        and (
            score >= 10
            or (title_hits >= 1 and cluster_size >= 2 and score >= 8)
        )
    )

    if explicit_urgent and recency >= 8 and title_hits >= 1:
        is_breaking = True

    return max(score, 0), is_breaking


_original_hot_news_signal = main.calculate_hot_news_signal
_original_calculate_importance = main.calculate_importance
_original_choose_news_emoji = getattr(main, "choose_news_emoji", None)


def enhanced_hot_news_signal(candidate):
    score, is_breaking = breaking_signal(candidate)
    candidate["breaking_score"] = score
    candidate["is_breaking"] = is_breaking

    # Ceremony/photo stories must not receive the generic hot prefix merely
    # because they are fresh. Explicitly urgent ceremony reports remain hot.
    if _is_ceremony_story(candidate.get("title", ""), candidate.get("summary", "")) and not is_breaking:
        return False

    return bool(_original_hot_news_signal(candidate) or is_breaking)


def enhanced_calculate_importance(candidate):
    score = _original_calculate_importance(candidate)
    breaking_score, is_breaking = breaking_signal(candidate)

    candidate["breaking_score"] = breaking_score
    candidate["is_breaking"] = is_breaking

    if is_breaking:
        score += 25
    elif _is_ceremony_story(candidate.get("title", ""), candidate.get("summary", "")):
        candidate["is_hot"] = False

    return score


main.calculate_hot_news_signal = enhanced_hot_news_signal
main.calculate_importance = enhanced_calculate_importance


# ============================================================
# CONTEXTUAL EMOJI
# ============================================================

# Replace generic urgency-style emoji selection with one topic-relevant emoji.
# The existing hot prefix (🔥) is also suppressed for ceremony/photo reports.

def contextual_news_emoji(title, body):
    text = _norm(f"{title} {body}")

    if any(x in text for x in ("تشییع", "تدفین", "خاکسپاری", "پیکر", "وداع", "سوگواری", "یادبود", "گرامیداشت")):
        return "🕊️"
    if any(x in text for x in ("زلزله", "سونامی", "سیل", "طوفان", "گردباد")):
        return "🌍"
    if any(x in text for x in ("انفجار", "آتش سوزی", "آتش‌سوزی")):
        return "🔥"
    if any(x in text for x in ("فوتبال", "ورزش", "مسابقه", "تیم", "گل")):
        return "⚽"
    if any(x in text for x in ("هوش مصنوعی", "فناوری", "موبایل", "گوشی", "ربات")):
        return "💻"
    if any(x in text for x in ("دلار", "طلا", "سکه", "بورس", "اقتصاد", "قیمت")):
        return "💰"
    if any(x in text for x in ("هواپیما", "پرواز", "قطار", "خودرو", "تصادف")):
        return "🚗"
    if any(x in text for x in ("مذاکرات", "تحریم", "مجلس", "دولت", "رئیس جمهور", "وزیر")):
        return "🏛️"
    if any(x in text for x in ("پزشکی", "سلامت", "بیمار", "درمان")):
        return "🩺"
    if any(x in text for x in ("باران", "هواشناسی", "دما", "برف")):
        return "🌦️"
    return "📰"


if _original_choose_news_emoji is not None:
    main.choose_news_emoji = contextual_news_emoji
