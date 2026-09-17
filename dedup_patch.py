"""NabzKhabar duplicate + breaking-news compatibility patch.

Keeps main.py architecture intact while adding a stronger semantic guard:
- preserves main.py's existing real-world event detector
- catches paraphrased versions of the same claim/event
- keeps ceremony stories out of Breaking News
- keeps contextual emoji selection
"""

import re
import main


# Keep the stronger event detector already implemented in main.py instead of
# accidentally replacing it with a weaker title-only matcher.
_ORIGINAL_SAME_STORY = main.same_story
_ORIGINAL_SAME_EVENT = getattr(main, "same_event", None)
_ORIGINAL_HOT_NEWS_SIGNAL = main.calculate_hot_news_signal
_ORIGINAL_CALCULATE_IMPORTANCE = main.calculate_importance
_ORIGINAL_CHOOSE_NEWS_EMOJI = getattr(main, "choose_news_emoji", None)

GENERIC = {
    "خبر", "گزارش", "اعلام", "آخرین", "جدید", "مهم", "تازه", "جزئیات",
    "واکنش", "اظهارات", "مواضع", "توضیح", "انتقاد", "تاکید", "تأکید",
    "گفت", "گفتند", "کرد", "کردند", "شد", "شدند", "خواهد", "می", "شود",
    "است", "هست", "این", "آن", "یک", "از", "به", "در", "با", "برای", "و",
    "که", "را", "تا", "بر", "های", "ها", "هم", "نیز", "مورد", "درباره",
    "ادعا", "مدعی", "عنوان", "اظهارات", "تصمیم", "انتشار",
}


def _norm(text):
    text = main.normalize_digits(str(text or "")).lower()
    text = (text.replace("ي", "ی").replace("ى", "ی").replace("ك", "ک").replace("ة", "ه"))
    text = re.sub(r"[\u200b-\u200f\ufeff]", " ", text)
    text = re.sub(r"[،؛,:.!؟()\[\]{}\"'«»/\\|_–—-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokens(text):
    return {x for x in _norm(text).split() if len(x) >= 2 and x not in GENERIC}


def _numbers(text):
    return set(re.findall(r"\d+(?:[.,٬]\d+)*", main.normalize_digits(str(text or ""))))


# ============================================================
# EVENT / CLAIM DEDUPLICATION
# ============================================================

# Explicit actor aliases. These are intentionally conservative: an actor is
# required before a claim-family match can suppress a story.
ACTOR_GROUPS = (
    {"ترامپ", "دونالد ترامپ", "رئیس جمهور آمریکا", "رئیس جمهوری آمریکا", "رئیس جمهور ایالات متحده"},
    {"بایدن", "جو بایدن", "رئیس جمهور سابق آمریکا"},
    {"پزشکیان", "مسعود پزشکیان", "رئیس جمهور ایران"},
    {"نتانیاهو", "بنیامین نتانیاهو", "نخست وزیر اسرائیل"},
    {"پوتین", "ولادیمیر پوتین", "رئیس جمهور روسیه"},
    {"زلنسکی", "ولودیمیر زلنسکی", "رئیس جمهور اوکراین"},
)

TOPIC_GROUPS = (
    {"جنگ ایران", "جنگ با ایران", "جنگ علیه ایران", "جنگ آمریکا و ایران", "جنگ ایران و آمریکا", "درگیری با ایران"},
    {"مذاکرات ایران", "مذاکرات با ایران", "مذاکره با ایران", "مذاکرات آمریکا و ایران", "توافق با ایران", "صلح با ایران"},
    {"آتش بس ایران", "آتش بس با ایران", "آتش‌بس ایران", "آتش‌بس با ایران"},
    {"قیمت دلار", "دلار", "نرخ دلار", "ارز"},
    {"قیمت طلا", "طلا", "سکه", "نرخ طلا"},
)

CLAIM_GROUPS = (
    {"پایان", "خاتمه", "تمام", "تمامی", "مراحل انتهایی", "مراحل پایانی", "نزدیک پایان", "به پایان رسیدن", "پایان یافتن", "پایان جنگ"},
    {"آغاز", "شروع", "شروع شدن", "آغاز شدن", "عملیات آغاز", "حمله آغاز"},
    {"مذاکره", "مذاکرات", "گفتگو", "گفت وگو", "گفتگوها", "رایزنی", "توافق"},
    {"حمله", "حمله موشکی", "موشک", "حمله هوایی", "حمله پهپادی"},
    {"افزایش", "صعود", "گران", "رشد", "کاهش", "افت", "ارزان"},
)


def _contains_any(text, group):
    return any(_norm(term) in text for term in group)


def _same_group(text_a, text_b, groups):
    a = _norm(text_a)
    b = _norm(text_b)
    for group in groups:
        if _contains_any(a, group) and _contains_any(b, group):
            return True
    return False


def _shared_actor(a, b):
    return _same_group(a, b, ACTOR_GROUPS)


def _shared_topic(a, b):
    return _same_group(a, b, TOPIC_GROUPS)


def _shared_claim(a, b):
    return _same_group(a, b, CLAIM_GROUPS)


def same_claim_event(title_a, body_a, title_b, body_b):
    """Catch paraphrased headlines reporting the same actor+topic+claim.

    This is deliberately stricter than ordinary keyword similarity. For
    example, two different Trump statements about Iran are not merged unless
    they share the same topic AND the same claim family.
    """
    a = _norm(f"{title_a} {body_a}")
    b = _norm(f"{title_b} {body_b}")
    if not a or not b:
        return False

    # Strong exact claim pattern: same actor + same topic + same claim.
    if _shared_actor(a, b) and _shared_topic(a, b) and _shared_claim(a, b):
        return True

    # If the actor is absent from one headline, require a very strong lexical
    # overlap plus the same topic/claim so generic stories are not suppressed.
    if _shared_topic(a, b) and _shared_claim(a, b):
        ta, tb = _tokens(a), _tokens(b)
        common = ta & tb
        if len(common) >= 3:
            return True

    return False


def strong_same_story(a, b):
    title_a = main.clean_title(a.get("title", ""))
    title_b = main.clean_title(b.get("title", ""))
    if not title_a or not title_b:
        return False

    # First preserve main.py's existing real-world event protection.
    try:
        if _ORIGINAL_SAME_STORY(a, b):
            return True
    except Exception:
        pass

    # Then add the new claim-level layer.
    if same_claim_event(title_a, a.get("summary", ""), title_b, b.get("summary", "")):
        return True

    if _norm(title_a) == _norm(title_b):
        return True

    tokens_a, tokens_b = _tokens(title_a), _tokens(title_b)
    if not tokens_a or not tokens_b:
        return False

    common = tokens_a & tokens_b
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
    return len(long_common) >= 3 and containment >= 0.50


main.same_story = strong_same_story


def strong_same_event(a_title, a_body, b_title, b_body):
    if _ORIGINAL_SAME_EVENT is not None:
        try:
            if _ORIGINAL_SAME_EVENT(a_title, a_body, b_title, b_body):
                return True
        except Exception:
            pass
    if same_claim_event(a_title, a_body, b_title, b_body):
        return True
    return strong_same_story(
        {"title": f"{a_title} {a_body}"},
        {"title": f"{b_title} {b_body}"},
    )


main.same_event = strong_same_event


# ============================================================
# BREAKING NEWS ENGINE
# ============================================================

BREAKING_TERMS = {
    "خبر فوری": 8, "فوری": 7, "لحظاتی پیش": 7, "همین حالا": 7, "دقایقی پیش": 7,
    "انفجار": 6, "حمله موشکی": 6, "حمله": 5, "موشک": 5, "زلزله": 6,
    "سونامی": 6, "سقوط هواپیما": 7, "سقوط": 5, "آتش سوزی": 5, "آتش‌سوزی": 5,
    "کشته": 5, "مفقود": 5, "ترور": 6, "درگیری": 5, "جنگ": 5, "آتش بس": 5,
    "آتش‌بس": 5, "قطع اینترنت": 5, "قطعی اینترنت": 5, "خاموشی گسترده": 5,
    "وضعیت فوق العاده": 6, "وضعیت فوق‌العاده": 6, "تخلیه": 5, "هشدار فوری": 7,
}

NON_BREAKING_CEREMONY_TERMS = {
    "تشییع", "تشییع پیکر", "تدفین", "خاکسپاری", "مراسم تشییع", "مراسم", "وداع",
    "سوگواری", "گلزار شهدا", "پیکر", "تصاویر", "عکس", "گزارش تصویری", "یادبود", "گرامیداشت",
}


def _is_ceremony_story(title, body):
    text = _norm(f"{title} {body}")
    return any(_norm(term) in text for term in NON_BREAKING_CEREMONY_TERMS)


def breaking_signal(candidate):
    title = main.clean_title(candidate.get("title", ""))
    body = main.clean_content(candidate.get("summary", ""))
    title_norm, body_norm = _norm(title), _norm(body)
    score = 0
    title_hits = 0

    for term, weight in BREAKING_TERMS.items():
        term_norm = _norm(term)
        if term_norm in title_norm:
            score += weight
            title_hits += 1
        elif term_norm in body_norm:
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

    explicit_urgent = any(p in title_norm for p in ("خبر فوری", "لحظاتی پیش", "دقایقی پیش", "همین حالا", "هشدار فوری"))
    if _is_ceremony_story(title, body) and not explicit_urgent:
        return 0, False

    is_breaking = recency >= 8 and (score >= 10 or (title_hits >= 1 and cluster_size >= 2 and score >= 8))
    if explicit_urgent and recency >= 8 and title_hits >= 1:
        is_breaking = True
    return max(score, 0), is_breaking


def enhanced_hot_news_signal(candidate):
    score, is_breaking = breaking_signal(candidate)
    candidate["breaking_score"] = score
    candidate["is_breaking"] = is_breaking
    if _is_ceremony_story(candidate.get("title", ""), candidate.get("summary", "")) and not is_breaking:
        return False
    return bool(_ORIGINAL_HOT_NEWS_SIGNAL(candidate) or is_breaking)


def enhanced_calculate_importance(candidate):
    score = _ORIGINAL_CALCULATE_IMPORTANCE(candidate)
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


if _ORIGINAL_CHOOSE_NEWS_EMOJI is not None:
    main.choose_news_emoji = contextual_news_emoji
