"""NabzKhabar duplicate + breaking-news + contextual emoji compatibility patch."""

import re
import main

_ORIGINAL_SAME_STORY = main.same_story
_ORIGINAL_SAME_EVENT = getattr(main, "same_event", None)
_ORIGINAL_HOT_NEWS_SIGNAL = main.calculate_hot_news_signal
_ORIGINAL_CALCULATE_IMPORTANCE = main.calculate_importance
_ORIGINAL_CHOOSE_NEWS_EMOJI = getattr(main, "choose_news_emoji", None)

GENERIC = {
    "خبر", "گزارش", "اعلام", "آخرین", "جدید", "مهم", "تازه", "واکنش", "اظهارات", "مواضع",
    "توضیح", "انتقاد", "تاکید", "تأکید", "گفت", "گفتند", "کرد", "کردند", "شد", "شدند",
    "خواهد", "می", "شود", "است", "هست", "این", "آن", "یک", "از", "به", "در", "با",
    "برای", "و", "که", "را", "تا", "بر", "های", "ها", "هم", "نیز", "مورد", "درباره",
    "تصمیم", "انتشار", "کرده", "شده",
}


def _norm(text):
    text = main.normalize_digits(str(text or "")).lower()
    text = text.replace("ي", "ی").replace("ى", "ی").replace("ك", "ک")
    text = text.replace("‌", " ")
    text = re.sub(r"[\u200b-\u200f\ufeff]", " ", text)
    text = re.sub(r"[،؛,:.!؟()\[\]{}\"'«»/\\|_–—-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokens(text):
    return {x for x in _norm(text).split() if len(x) >= 2 and x not in GENERIC}


def _numbers(text):
    return set(re.findall(r"\d+(?:[.,٬]\d+)*", main.normalize_digits(str(text or ""))))

# ---------- duplicate / event protection ----------
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
    a, b = _norm(text_a), _norm(text_b)
    return any(_contains_any(a, g) and _contains_any(b, g) for g in groups)


def _shared_actor(a, b): return _same_group(a, b, ACTOR_GROUPS)
def _shared_topic(a, b): return _same_group(a, b, TOPIC_GROUPS)
def _shared_claim(a, b): return _same_group(a, b, CLAIM_GROUPS)


def same_claim_event(title_a, body_a, title_b, body_b):
    a, b = _norm(f"{title_a} {body_a}"), _norm(f"{title_b} {body_b}")
    if not a or not b: return False
    if _shared_actor(a, b) and _shared_topic(a, b) and _shared_claim(a, b): return True
    if _shared_topic(a, b) and _shared_claim(a, b) and len(_tokens(a) & _tokens(b)) >= 3: return True
    return False


def strong_same_story(a, b):
    title_a = main.clean_title(a.get("title", "")); title_b = main.clean_title(b.get("title", ""))
    if not title_a or not title_b: return False
    try:
        if _ORIGINAL_SAME_STORY(a, b): return True
    except Exception: pass
    if same_claim_event(title_a, a.get("summary", ""), title_b, b.get("summary", "")): return True
    if _norm(title_a) == _norm(title_b): return True
    ta, tb = _tokens(title_a), _tokens(title_b)
    if not ta or not tb: return False
    common = ta & tb
    jaccard = len(common) / len(ta | tb)
    containment = len(common) / min(len(ta), len(tb))
    if len(common) >= 4 and containment >= .60: return True
    if len(common) >= 5 and jaccard >= .32: return True
    if _numbers(title_a) & _numbers(title_b) and len(common) >= 2 and jaccard >= .25: return True
    return len([w for w in common if len(w) >= 4]) >= 3 and containment >= .50

main.same_story = strong_same_story


def strong_same_event(a_title, a_body, b_title, b_body):
    if _ORIGINAL_SAME_EVENT is not None:
        try:
            if _ORIGINAL_SAME_EVENT(a_title, a_body, b_title, b_body): return True
        except Exception: pass
    if same_claim_event(a_title, a_body, b_title, b_body): return True
    return strong_same_story({"title": f"{a_title} {a_body}"}, {"title": f"{b_title} {b_body}"})

main.same_event = strong_same_event

# ---------- breaking news ----------
BREAKING_TERMS = {
    "خبر فوری": 8, "فوری": 7, "لحظاتی پیش": 7, "همین حالا": 7, "دقایقی پیش": 7,
    "انفجار": 6, "حمله موشکی": 6, "حمله": 5, "موشک": 5, "زلزله": 6, "سونامی": 6,
    "سقوط هواپیما": 7, "سقوط": 5, "آتش سوزی": 5, "آتش‌سوزی": 5, "کشته": 5, "مفقود": 5,
    "ترور": 6, "درگیری": 5, "جنگ": 5, "آتش بس": 5, "آتش‌بس": 5, "قطع اینترنت": 5,
    "قطعی اینترنت": 5, "خاموشی گسترده": 5, "وضعیت فوق العاده": 6, "وضعیت فوق‌العاده": 6,
    "تخلیه": 5, "هشدار فوری": 7,
}
NON_BREAKING_CEREMONY_TERMS = {"تشییع", "تشییع پیکر", "تدفین", "خاکسپاری", "مراسم تشییع", "مراسم", "وداع", "سوگواری", "گلزار شهدا", "پیکر", "تصاویر", "عکس", "گزارش تصویری", "یادبود", "گرامیداشت"}


def _is_ceremony_story(title, body):
    text = _norm(f"{title} {body}")
    return any(_norm(term) in text for term in NON_BREAKING_CEREMONY_TERMS)


def breaking_signal(candidate):
    title = main.clean_title(candidate.get("title", "")); body = main.clean_content(candidate.get("summary", ""))
    title_norm, body_norm = _norm(title), _norm(body)
    score = 0; title_hits = 0
    for term, weight in BREAKING_TERMS.items():
        term_norm = _norm(term)
        if term_norm in title_norm: score += weight; title_hits += 1
        elif term_norm in body_norm: score += max(1, weight // 2)
    recency = main.calculate_recency_score(candidate.get("published_at")); cluster_size = int(candidate.get("cluster_size", 1) or 1)
    if recency >= 12: score += 5
    elif recency >= 10: score += 3
    elif recency >= 8: score += 1
    else: score -= 4
    if cluster_size >= 2: score += min(cluster_size, 4) * 2
    explicit_urgent = any(p in title_norm for p in ("خبر فوری", "لحظاتی پیش", "دقایقی پیش", "همین حالا", "هشدار فوری"))
    if _is_ceremony_story(title, body) and not explicit_urgent: return 0, False
    is_breaking = recency >= 8 and (score >= 10 or (title_hits >= 1 and cluster_size >= 2 and score >= 8))
    if explicit_urgent and recency >= 8 and title_hits >= 1: is_breaking = True
    return max(score, 0), is_breaking


def enhanced_hot_news_signal(candidate):
    score, is_breaking = breaking_signal(candidate)
    candidate["breaking_score"] = score; candidate["is_breaking"] = is_breaking
    if _is_ceremony_story(candidate.get("title", ""), candidate.get("summary", "")) and not is_breaking: return False
    return bool(_ORIGINAL_HOT_NEWS_SIGNAL(candidate) or is_breaking)


def enhanced_calculate_importance(candidate):
    score = _ORIGINAL_CALCULATE_IMPORTANCE(candidate)
    breaking_score, is_breaking = breaking_signal(candidate)
    candidate["breaking_score"] = breaking_score; candidate["is_breaking"] = is_breaking
    if is_breaking: score += 25
    elif _is_ceremony_story(candidate.get("title", ""), candidate.get("summary", "")): candidate["is_hot"] = False
    return score

main.calculate_hot_news_signal = enhanced_hot_news_signal
main.calculate_importance = enhanced_calculate_importance

# ---------- contextual emoji ----------
# Rules are intentionally conservative: generic words such as "گل", "تیم",
# "قیمت" or "وزیر" are not enough by themselves to select an emoji.
EMOJI_RULES = (
    ("🕊️", ("تشییع", "تشییع پیکر", "تدفین", "خاکسپاری", "مراسم تشییع", "وداع", "سوگواری", "یادبود", "گرامیداشت")),
    ("🌍", ("زلزله", "سونامی", "سیل", "طوفان", "گردباد", "رانش زمین")),
    ("🔥", ("انفجار", "انفجار بزرگ", "آتش سوزی", "آتش‌سوزی", "حریق", "آتش گرفت", "آتش گرفتند")),
    ("⚽", ("فوتبال", "لیگ", "جام جهانی", "گلزنی", "گل زد", "دیدار فوتبال", "مسابقه فوتبال", "استقلال", "پرسپولیس", "آرسنال", "منچستر", "رئال مادرید", "بارسلونا", "لیورپول")),
    ("💻", ("هوش مصنوعی", "فناوری", "تکنولوژی", "موبایل", "گوشی هوشمند", "ربات", "اپلیکیشن", "نرم افزار", "نرم‌افزار", "پردازنده", "تراشه", "اینترنت", "سایبری")),
    ("💰", ("دلار", "یورو", "پوند", "طلا", "سکه", "ارز", "بورس", "اقتصاد", "تورم", "نرخ ارز", "قیمت طلا", "قیمت دلار", "بازار سرمایه")),
    ("🚗", ("تصادف", "واژگونی خودرو", "خودرو", "اتوبوس", "کامیون", "قطار", "هواپیما", "پرواز", "سقوط هواپیما", "مترو")),
    ("🏛️", ("مجلس", "دولت", "رئیس جمهور", "رئیس‌جمهور", "وزیر", "وزارت", "استاندار", "نماینده مجلس", "انتخابات", "مذاکرات", "تحریم", "قانون", "تصویب", "کابینه")),
    ("🩺", ("پزشکی", "سلامت", "بیمارستان", "بیمار", "درمان", "دارو", "پزشک", "ویروس", "بیماری", "واکسین")),
    ("🌦️", ("هواشناسی", "پیش بینی هوا", "پیش‌بینی هوا", "بارش", "باران", "برف", "دما", "گرما", "سرما", "آلودگی هوا")),
)


def contextual_news_emoji(title, body):
    text = _norm(f"{title} {body}")
    # Strong incident rules first; avoid accidental classification by generic words.
    for emoji, terms in EMOJI_RULES:
        if any(_norm(term) in text for term in terms):
            return emoji
    return "📰"


if _ORIGINAL_CHOOSE_NEWS_EMOJI is not None:
    main.choose_news_emoji = contextual_news_emoji
