"""NABZ V13 final policy guard.

Installed last so no later layer can reopen a story rejected by the final
scope/freshness policy. Iranian-publisher international reporting remains
eligible; foreign-local reporting and opinion-only commentary are blocked.
"""

import re
from datetime import datetime, timezone

NORMAL_WINDOW_MINUTES = 30
CRITICAL_RESCUE_MAX_HOURS = 6
IRANIAN_ALLOWED_HOSTS = {"yjc.ir", "irna.ir"}

FOREIGN_LOCAL_TERMS = re.compile(
    r"\b(?:australia|australian|sydney|melbourne|brisbane|perth|adelaide|canberra|queensland|victoria|tasmania|"
    r"united kingdom|britain|british|london|england|scotland|wales|anglesey|united states|american|washington|new york|"
    r"california|texas|florida|canada|canadian|toronto|vancouver|germany|german|berlin|france|french|paris|italy|"
    r"italian|rome|spain|spanish|madrid|japan|japanese|tokyo|south korea|korean|seoul|india|indian|delhi|pakistan|"
    r"pakistani|islamabad|afghanistan|afghan|turkey|turkish|ankara|istanbul|netherlands|dutch|amsterdam|sweden|"
    r"swedish|norway|norwegian|denmark|danish|poland|polish|uk|mexico|mexican|brazil|brazilian|china|chinese|taiwan|"
    r"russia|russian|ukraine|ukrainian|israel|israeli|gaza|oman|bangladesh|bangladeshi|dhaka|"
    r"آمریکا|امریکا|بریتانی|بریتانیا|انگلیس|لندن|انگلستان|اسکاتلند|ولز|استرالیا|سیدنی|کانادا|تورنتو|آلمان|برلین|"
    r"فرانسه|پاریس|ایتالیا|رم|اسپانیا|ژاپن|توکیو|کره جنوبی|سئول|هند|دهلی|پاکستان|اسلام آباد|افغانستان|ترکیه|"
    r"آنکارا|استانبول|چین|تایوان|روسیه|اوکراین|اسرائیل|غزه|مکزیک|برزیل|عمان|بنگلادش|دکا)\b",
    re.I,
)

GLOBAL_OVERRIDE = re.compile(
    r"\b(?:global|worldwide|international|cross[- ]border|multinational|united nations|un general assembly|unga|nato|g7|g20|"
    r"icc|international court|iran|russia|ukraine|israel|gaza|china|taiwan|north korea|middle east|european union|eu|"
    r"war|invasion|ceasefire|sanctions|tariffs|brics|سازمان ملل|مجمع عمومی|بین المللی|بین‌المللی|فرامرزی|چندملیتی|ایران|"
    r"روسیه|اوکراین|اسرائیل|غزه|چین|تایوان|کره شمالی|خاورمیانه|اتحادیه اروپا|جنگ|تهاجم|آتش بس|آتش‌بس|تحریم|تعرفه)\b",
    re.I,
)

SEVERE_SCALE = re.compile(
    r"\b(?:mass[- ]casualt(?:y|ies)|major disaster|national emergency|dozens killed|dozens injured|hundreds killed|"
    r"hundreds injured|multiple fatalities|large[- ]scale evacuation|nationwide outage|ده.?ها کشته|ده.?ها زخمی|صدها کشته|"
    r"صدها زخمی|تلفات گسترده|فاجعه بزرگ|وضعیت اضطراری ملی|تخلیه گسترده|اختلال سراسری|قطعی سراسری)\b",
    re.I,
)

FOREIGN_LOCAL_MARKERS = re.compile(
    r"\b(?:raf|nhs|met police|council|county council|local council|school district|local school|mayor|shire|borough|"
    r"training jet|local election|local court|local hospital|football club|premier league|championship|پلیس محلی|"
    r"شورای شهر|شهرداری|مدرسه|بیمارستان محلی|انتخابات محلی|باشگاه فوتبال|لیگ برتر)",
    re.I,
)

OPINION_ONLY = re.compile(
    r"(?:تحلیلگر|تحلیل‌گر|کارشناس|اندیشمند|مجری|فعال|نویسنده|استاد|commentator|analyst|expert|host|presenter|"
    r"response|responds|slams|criticizes|criticises|calls out|hits back|"
    r"حمله تند|حمله شدید|پاسخ قاطع|واکنش تند|واکنش شدید|انتقاد تند|اظهارات|ادعا(?:ی)?|می‌گوید|گفت)",
    re.I,
)
CONCRETE_EVENT = re.compile(
    r"(?:کشته|زخمی|مفقود|بازداشت|انفجار|زلزله|سیل|طوفان|آتش.?سوزی|سقوط|موشک|بمباران|"
    r"حمله موشکی|جنگ|درگیری نظامی|عملیات نظامی|تحریم|تعلیق|توقف|ممنوع|قطعی|اختلال|تخلیه|"
    r"تصویب|ابلاغ|لغو|افزایش قیمت|کاهش قیمت|جهش قیمت|ادغام|تملک|شکایت|دادگاه|حکم|"
    r"killed|wounded|missing|explosion|earthquake|flood|storm|crash|missile|strike|bombing|"
    r"war|military|sanction|ceasefire|outage|evacuation|merger|acquisition|lawsuit|court|verdict)",
    re.I,
)
ROUNDUP = re.compile(
    r"(?:چه خبر|مرور مهمترین|مرور مهم‌ترین|مهمترین اخبار|مهم‌ترین اخبار|مهمترین عناوین|مهم‌ترین عناوین|اخبار مهم امروز|"
    r"اخبار مهم|آخرین اخبار|بسته خبری|مرور اخبار|نگاهی به اخبار|نگاهی به مهمترین|نگاهی به مهم‌ترین|نگاهی به عناوین|"
    r"عناوین روزنامه|تیتر روزنامه|مرور مطبوعات|روزنامه های|روزنامه‌های|پیشخوان روزنامه|newspaper headlines|"
    r"newspaper roundup|headlines from the newspapers|newspaper front pages)", re.I,
)


def _text(candidate):
    return " ".join(str(candidate.get(k, "") or "") for k in ("title", "summary", "description")).strip()


def _is_iranian_publisher(candidate):
    for key in ("resolved_link", "link", "source_url"):
        value = str(candidate.get(key, "") or "").strip().lower()
        host = re.sub(r"^https?://", "", value).split("/", 1)[0].split(":", 1)[0]
        if host.startswith("www."):
            host = host[4:]
        if host in IRANIAN_ALLOWED_HOSTS:
            return True
    return False


def _foreign_local_only(candidate):
    """Reject routine foreign-local reporting, but keep consequential global events."""
    text = _text(candidate)
    if not text:
        return False
    if ROUNDUP.search(text):
        return True
    # Evaluate nationally significant regulatory/safety changes before generic
    # local markers such as "football club" can reject them.
    national_policy_impact = re.search(
        r"\b(?:football association|national football association|governing body|stadium accreditation|"
        r"safety rules?|safety regulations?|regulations?|rules?)\b",
        text, re.I,
    ) and re.search(
        r"\b(?:changed|changes|updated|update|banned|ban|prohibited|introduced|revised|"
        r"affected|clubs?|all levels|national league|169 clubs?)\b",
        text, re.I,
    ) and re.search(
        r"\b(?:death|died|killed|fatal|fatality|serious injury|injured|accident|collision|"
        r"مرگ|جان باخت|کشته|فوت|مصدومیت شدید|آسیب شدید|حادثه|ایمنی|قوانین|مقررات|ممنوع|اصلاح|تغییر)\b",
        text, re.I,
    )
    if national_policy_impact:
        return False
    if FOREIGN_LOCAL_MARKERS.search(text):
        if GLOBAL_OVERRIDE.search(text) or SEVERE_SCALE.search(text):
            return False
        return True
    if not FOREIGN_LOCAL_TERMS.search(text):
        return False
    if GLOBAL_OVERRIDE.search(text) or SEVERE_SCALE.search(text):
        return False
    # National-level safety/regulatory consequences are not routine local news.
    # Example: a national governing body changes safety rules after a fatality,
    # affecting many clubs or an entire competition system.
    national_policy_impact = re.search(
        r"\b(?:football association|national football association|governing body|stadium accreditation|"
        r"safety rules?|safety regulations?|regulations?|rules?)\b",
        text, re.I,
    ) and re.search(
        r"\b(?:changed|changes|updated|update|banned|ban|prohibited|introduced|revised|"
        r"affected|clubs?|all levels|national league|169 clubs?)\b",
        text, re.I,
    ) and re.search(
        r"\b(?:death|died|killed|fatal|fatality|serious injury|injured|accident|collision|"
        r"مرگ|جان باخت|کشته|فوت|جان.?باخت|مصدومیت شدید|آسیب شدید|حادثه|ایمنی|قوانین|مقررات|"
        r"ممنوع|اصلاح|تغییر)\b",
        text, re.I,
    )
    consequential_event = re.search(
        r"\b(?:hurricane|typhoon|earthquake|tsunami|volcan|wildfire|deadly attack|terror attack|mass shooting|major explosion|major fire|large[- ]scale evacuation|dozens killed|hundreds killed|dozens injured|hundreds injured)\b|"
        r"هاریکن|تایفون|زلزله شدید|سونامی|آتشفشان|حمله مرگبار|حمله تروریستی|انفجار بزرگ|آتش‌سوزی گسترده|تخلیه گسترده|ده.?ها کشته|صدها کشته|ده.?ها زخمی|صدها زخمی",
        text, re.I,
    )
    if consequential_event or national_policy_impact:
        return False
    country_hits = re.findall(
        r"\b(?:australia|britain|united kingdom|america|united states|canada|germany|france|italy|spain|japan|south korea|india|pakistan|afghanistan|turkey|china|taiwan|russia|ukraine|israel|mexico|brazil|oman|bangladesh)\b|"
        r"استرالیا|بریتانیا|انگلیس|آمریکا|کانادا|آلمان|فرانسه|ایتالیا|اسپانیا|ژاپن|کره جنوبی|هند|پاکستان|افغانستان|ترکیه|چین|تایوان|روسیه|اوکراین|اسرائیل|مکزیک|برزیل|عمان|بنگلادش",
        text, re.I
    )
    return len({x.lower() for x in country_hits}) < 2


def _opinion_only(candidate):
    text = _text(candidate)
    title = str(candidate.get("title", "") or "")
    return bool(OPINION_ONLY.search(title)) and not CONCRETE_EVENT.search(text)


def _filter(candidates):
    kept = []
    for candidate in candidates:
        title = str(candidate.get("title", ""))
        if _opinion_only(candidate):
            print("V13 FINAL OPINION DROP: " + title)
            continue
        if _foreign_local_only(candidate):
            print("V13 FINAL SCOPE DROP: " + title)
            continue
        kept.append(candidate)
    return kept


def _age_minutes(dt):
    if not dt:
        return None
    try:
        return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 60.0)
    except Exception:
        return None


def install(main):
    main.FEED_COLLECTION_WINDOW_MINUTES = NORMAL_WINDOW_MINUTES
    main.MAX_NEWS_AGE_HOURS = NORMAL_WINDOW_MINUTES / 60.0
    main.IMPORTANT_NEWS_RESCUE_MAX_AGE_MINUTES = CRITICAL_RESCUE_MAX_HOURS * 60
    original_filter = getattr(main, "_filter_foreign_local_scope", None)
    if original_filter is not None:
        def final_filter(candidates):
            return _filter(original_filter(candidates))
        main._filter_foreign_local_scope = final_filter
    original_select = getattr(main, "select_best_candidate", None)
    if original_select is not None:
        def guarded_select(candidates, *args, **kwargs):
            return original_select(_filter(candidates), *args, **kwargs)
        main.select_best_candidate = guarded_select
    print(f"V13 FINAL POLICY GUARD ACTIVE: fresh={NORMAL_WINDOW_MINUTES}m, rescue={CRITICAL_RESCUE_MAX_HOURS}h")
