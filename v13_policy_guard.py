"""NABZ V13 final policy guard.

Installed last so no later layer can reopen a story rejected by the final
scope/freshness policy. Iranian-publisher international reporting remains
eligible; foreign-local reporting is blocked by event scope.
"""

import re
from datetime import datetime, timezone

NORMAL_WINDOW_MINUTES = 30
CRITICAL_RESCUE_MAX_HOURS = 6

IRANIAN_ALLOWED_HOSTS = {"yjc.ir", "irna.ir"}

FOREIGN_LOCAL_TERMS = re.compile(
    r"\b(?:australia|australian|sydney|melbourne|brisbane|perth|adelaide|canberra|"
    r"queensland|victoria|tasmania|united kingdom|britain|british|london|england|"
    r"scotland|wales|anglesey|united states|american|washington|new york|california|"
    r"texas|florida|canada|canadian|toronto|vancouver|germany|german|berlin|france|"
    r"french|paris|italy|italian|rome|spain|spanish|madrid|japan|japanese|tokyo|"
    r"south korea|korean|seoul|india|indian|delhi|pakistan|pakistani|islamabad|"
    r"afghanistan|afghan|turkey|turkish|ankara|istanbul|netherlands|dutch|amsterdam|"
    r"sweden|swedish|norway|norwegian|denmark|danish|poland|polish|uk|england|"
    r"آمریکا|امریکا|بریتانی|بریتانیا|انگلیس|لندن|انگلستان|اسکاتلند|ولز|"
    r"استرالیا|سیدنی|کانادا|تورنتو|آلمان|برلین|فرانسه|پاریس|ایتالیا|رم|اسپانیا|"
    r"ژاپن|توکیو|کره جنوبی|سئول|هند|دهلی|پاکستان|اسلام آباد|افغانستان|ترکیه|آنکارا|استانبول)\b",
    re.I,
)

GLOBAL_OVERRIDE = re.compile(
    r"\b(?:global|worldwide|international|cross[- ]border|multinational|"
    r"united nations|un general assembly|unga|nato|g7|g20|icc|international court|"
    r"iran|russia|ukraine|israel|gaza|china|taiwan|north korea|middle east|"
    r"european union|eu|war|invasion|ceasefire|sanctions|tariffs|"
    r"سازمان ملل|مجمع عمومی|بین المللی|بین‌المللی|فرامرزی|چندملیتی|"
    r"ایران|روسیه|اوکراین|اسرائیل|غزه|چین|تایوان|کره شمالی|خاورمیانه|"
    r"اتحادیه اروپا|جنگ|تهاجم|آتش بس|آتش‌بس|تحریم|تعرفه)\b",
    re.I,
)

SEVERE_SCALE = re.compile(
    r"\b(?:mass[- ]casualt(?:y|ies)|major disaster|national emergency|"
    r"dozens killed|dozens injured|hundreds killed|hundreds injured|"
    r"multiple fatalities|large[- ]scale evacuation|nationwide outage|"
    r"ده.?ها کشته|ده.?ها زخمی|صدها کشته|صدها زخمی|تلفات گسترده|فاجعه بزرگ|"
    r"وضعیت اضطراری ملی|تخلیه گسترده|اختلال سراسری|قطعی سراسری)\b",
    re.I,
)

FOREIGN_LOCAL_MARKERS = re.compile(
    r"\b(?:raf|nhs|met police|council|county council|local council|"
    r"school district|local school|mayor|shire|borough|training jet|"
    r"local election|local court|local hospital|football club|premier league|"
    r"championship|پلیس محلی|شورای شهر|شهرداری|مدرسه|بیمارستان محلی|"
    r"انتخابات محلی|باشگاه فوتبال|لیگ برتر)\b",
    re.I,
)

ROUNDUP = re.compile(
    r"(?:چه خبر|مرور مهمترین|مرور مهم‌ترین|مهمترین اخبار|مهم‌ترین اخبار|"
    r"مهمترین عناوین|مهم‌ترین عناوین|اخبار مهم امروز|اخبار مهم|آخرین اخبار|"
    r"بسته خبری|مرور اخبار|نگاهی به اخبار|نگاهی به مهمترین|نگاهی به مهم‌ترین|"
    r"نگاهی به عناوین|عناوین روزنامه|تیتر روزنامه|مرور مطبوعات|روزنامه های|"
    r"روزنامه‌های|پیشخوان روزنامه|newspaper headlines|newspaper roundup|"
    r"headlines from the newspapers|newspaper front pages)", re.I,
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
    text = _text(candidate)
    if not text:
        return False

    # Iranian publishers may legitimately report international stories. The
    # final scope gate must not mistake an Iranian-language report about Trump,
    # the US, Europe, etc. for foreign-local reporting.
    if _is_iranian_publisher(candidate):
        return False

    if FOREIGN_LOCAL_MARKERS.search(text):
        if GLOBAL_OVERRIDE.search(text) or SEVERE_SCALE.search(text):
            return False
        return True

    if not FOREIGN_LOCAL_TERMS.search(text):
        return False

    if GLOBAL_OVERRIDE.search(text) or SEVERE_SCALE.search(text):
        return False

    return True


def _filter(candidates):
    kept = []
    for candidate in candidates:
        if _foreign_local_only(candidate):
            print("V13 FINAL SCOPE DROP: " + str(candidate.get("title", "")))
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
