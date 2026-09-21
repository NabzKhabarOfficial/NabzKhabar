"""NABZ V13 intelligence/stability layer.

This module is intentionally additive: it wraps the existing V13 runtime
without replacing the news engine or touching independent pipelines.
"""

import json
import os
import re
import time
from collections import Counter
from datetime import datetime, timezone

HEALTH_FILE = "v13_health.json"
REJECTED_NEWS_FILE = "v13_rejected_news.json"
MAX_REJECTED_NEWS_HISTORY = 500
MAX_NEWS_PER_RUN = 4
MIN_EVENT_SCORE = 5

HIGH_IMPACT = (
    "جنگ", "حمله", "موشک", "انفجار", "زلزله", "سیل", "آتش سوزی",
    "آتش‌سوزی", "سقوط هواپیما", "هواپیما سقوط", "کشته", "زخمی",
    "مفقود", "ترور", "آتش بس", "آتش‌بس", "تحریم", "هسته ای", "هسته‌ای",
    "قطعی اینترنت", "قطع اینترنت", "حمله سایبری", "بحران", "اضطراری",
    "فراخوان", "ممنوع", "ممنوعیت", "تعلیق", "توقف", "قطع برق", "قطع گاز",
    "کمبود سوخت", "افزایش قیمت", "کاهش قیمت", "تورم", "نرخ بهره",
    "بنزین", "نفت", "گاز", "هوش مصنوعی", "تراشه", "قهرمان", "فینال",
)

MEDIUM_IMPACT = (
    "قانون", "تصویب", "ابلاغ", "وزارت", "دولت", "رئیس جمهور", "رئیس‌جمهور",
    "مجلس", "بانک مرکزی", "دارو", "بیماری", "واکسین", "پژوهش", "ماهواره",
    "ربات", "شرکت", "اپل", "گوگل", "مایکروسافت", "متا", "انویدیا",
)

ACTION_TERMS = (
    "کشته", "زخمی", "مفقود", "بازداشت", "تخلیه", "متوقف", "تعلیق",
    "ممنوع", "محدود", "قطع", "بازگشت", "فراخوان", "لغو", "تصویب",
    "رد", "اجرا", "ابلاغ", "اعلام", "افزایش", "کاهش", "سقوط", "رشد",
    "جهش", "تحریم", "حمله", "انفجار", "آتش بس", "آتش‌بس",
)

ROUTINE = (
    "دیدار", "سفر", "مراسم", "نشست", "همایش", "گرامیداشت", "افتتاح",
    "واکنش", "اظهارات", "گفت", "گفت:", "تاکید کرد", "تأکید کرد",
    "تسلیت", "تبریک", "پیام", "قرار است", "برنامه دارد", "تصمیم دارد",
)

HIGH_IMPACT_SECURITY_SIGNALS = (
    "تهدید", "اولتیماتوم", "تهدید نظامی", "تهدید کرد", "حمله نظامی",
    "حمله هوایی", "حمله زمینی", "حمله دریایی", "حمله موشکی", "بمباران",
    "عملیات نظامی", "عملیات هوایی", "درگیری نظامی", "تشدید درگیری",
    "تشدید تنش", "تشدید حملات", "تنش نظامی", "پاسخ نظامی", "پاسخ تلافی",
    "تلافی", "شلیک", "آتش گشود", "هدف قرار داد", "هدف قرار دادن",
    "مورد حمله قرار گرفت", "مواضع نظامی", "پایگاه نظامی", "آماده باش",
    "آماده‌باش", "تحرک نظامی", "هشدار امنیتی", "حمله به", "درگیری",
    "تجاوز نظامی", "پرتابه", "طوفان", "تخلیه",
)

HIGH_IMPACT_ACTORS = (
    "ایران", "ترامپ", "آمریکا", "اسرائیل", "سوریه", "عراق", "لبنان",
    "فلسطین", "غزه", "یمن", "عربستان", "ترکیه", "روسیه", "اوکراین",
    "چین", "تایوان", "کره جنوبی", "کره شمالی", "ناتو", "بریتانیا",
    "فرانسه", "آلمان", "دونالد ترامپ", "پنتاگون", "کاخ سفید",
    "سپاه", "ارتش", "نیروی هوایی", "نیروی دریایی",
)

LOW_VALUE = (
    "تخفیف", "فروش ویژه", "قرعه کشی", "قرعه‌کشی", "استخدام", "فال",
    "طالع بینی", "تولد", "اینستاگرام", "چهره", "سلبریتی", "رپورتاژ",
    "تبلیغات", "تبلیغاتی", "مسابقه", "لایف استایل", "سبک زندگی",
    "اکران", "مستند", "رونمایی هنری", "کنسرت", "جشنواره فیلم",
)

IRAN_REGION_ENTITIES = (
    "ایران", "تهران", "خوزستان", "کردستان", "کرمان", "سیستان", "آذربایجان",
    "عراق", "سوریه", "لبنان", "فلسطین", "غزه", "اسرائیل", "ترکیه",
    "عربستان", "قطر", "امارات", "آمریکا", "روسیه", "اوکراین", "چین",
    "اروپا", "کره جنوبی", "کره شمالی",
)

GENERIC = {
    "خبر", "گزارش", "اعلام", "آخرین", "مهم", "جدید", "درباره", "مورد",
    "واکنش", "اظهارات", "تصمیم", "جزئیات",
}


def _norm(value):
    value = str(value or "").replace("ي", "ی").replace("ك", "ک")
    value = value.replace("\u200c", " ")
    return re.sub(r"\s+", " ", value).strip()


def _text(candidate):
    return _norm(" ".join(
        str(candidate.get(k, "") or "")
        for k in ("title", "summary", "description", "article_text")
    ))


def _source_host(main, candidate):
    url = candidate.get("resolved_link") or candidate.get("link") or ""
    try:
        return main.base_domain(main.get_hostname(url))
    except Exception:
        return ""


def source_reliability(main, candidate):
    quality = main.publisher_quality(
        candidate.get("resolved_link") or candidate.get("link") or ""
    )
    if quality >= 25:
        return 10
    if quality >= 15:
        return 8
    if quality >= 5:
        return 6
    if quality > 0:
        return 4
    return 2


def event_score(main, candidate):
    title = _norm(candidate.get("title", "")).lower()
    body = _text(candidate).lower()
    title_high = sum(x.lower() in title for x in HIGH_IMPACT)
    title_medium = sum(x.lower() in title for x in MEDIUM_IMPACT)
    actions = sum(x.lower() in title or x.lower() in body[:3000] for x in ACTION_TERMS)
    entities = sum(x.lower() in title for x in IRAN_REGION_ENTITIES)
    concrete = bool(re.search(
        r"(\d+[٫,.]?\d*\s*(?:نفر|درصد|درجه|میلیون|میلیارد|کیلومتر|دلار|یورو|تومان|سال|روز))"
        r"|(?:افزایش|کاهش|رشد|سقوط|جهش|قطع|تعلیق|ممنوع|کشته|زخمی|بازداشت|انفجار|حمله)",
        title + " " + body[:2500],
        re.I,
    ))
    routine = sum(x.lower() in title for x in ROUTINE)
    low = sum(x.lower() in title for x in LOW_VALUE)

    score = 0
    score += min(title_high * 5, 20)
    score += min(title_medium * 2, 4)
    score += min(actions * 2, 6)
    score += 1 if entities and actions else 0
    score += 2 if concrete else 0
    score += source_reliability(main, candidate) // 3
    score += 1 if candidate.get("cluster_size", 1) >= 2 else 0
    score -= min(routine * 2, 6)
    score -= min(low * 8, 16)
    return score


def _major_business_legal_override(candidate):
    title = _norm(candidate.get("title", "")).lower()
    event = any(x in title for x in (
        "ادغام", "ادغام شد", "تملک", "تصاحب", "خرید", "دعوی قضایی",
        "شکایت", "حل و فصل", "رقابت", "انحصار",
        "merger", "acquisition", "acquired", "lawsuit", "settlement", "antitrust",
    ))
    concrete = bool(re.search(
        r"(?:\$?\d[\d,.]*\s*(?:میلیارد|million|billion)|"
        r"میلیارد|میلیون|%|درصد|states|state|دادگاه|دادستان|regulator|regulators|"
        r"lawsuit|settlement|antitrust)",
        title,
        re.I,
    ))
    return event and concrete


def _high_impact_security_override(candidate):
    title = _norm(candidate.get("title", "")).lower()
    title_signals = sum(x.lower() in title for x in HIGH_IMPACT_SECURITY_SIGNALS)
    actor_hits = sum(x.lower() in title for x in HIGH_IMPACT_ACTORS)
    strong_topic = any(x.lower() in title for x in HIGH_IMPACT)
    disaster_topic = any(x.lower() in title for x in (
        "زلزله", "سیل", "طوفان", "سونامی", "رانش زمین", "آتش سوزی",
        "آتش‌سوزی", "تخلیه", "هواپیما", "کشتی", "نفتکش",
    ))
    english_event = any(x in title for x in (
        "attack", "strike", "missile", "bombing", "explosion", "earthquake",
        "flood", "storm", "typhoon", "tsunami", "evacuat", "escalat",
        "military", "threat", "wildfire", "landslide", "shooting",
        "crash", "wounded", "killed",
    ))
    if title_signals == 0 and not disaster_topic and not english_event:
        return False
    if disaster_topic or english_event:
        return True
    return strong_topic and (actor_hits > 0 or title_signals > 0)

def _publication_tier(candidate):
    """Classify editorial importance so routine warnings cannot displace major news."""
    title = _norm(candidate.get("title", "")).lower()
    body = _text(candidate).lower()
    security = _high_impact_security_override(candidate)
    major_business = _major_business_legal_override(candidate)
    critical = any(x.lower() in title for x in (
        "جنگ", "حمله", "حمله موشکی", "بمباران", "انفجار بزرگ", "زلزله",
        "سیل", "سونامی", "سقوط هواپیما", "کشته", "مفقود", "ترور",
        "آتش بس", "آتش‌بس", "تحریم", "قطع اینترنت", "حمله سایبری",
        "پرتابه", "نفتکش", "درگیری نظامی", "عملیات نظامی",
        "attack", "strike", "missile", "bombing", "explosion", "earthquake",
        "flood", "tsunami", "crash", "killed", "wounded", "tanker",
    ))
    major = any(x.lower() in title or x.lower() in body[:4000] for x in (
        "ادغام", "تملک", "تصاحب", "دعوی قضایی", "شکایت", "انحصار",
        "نرخ بهره", "تورم", "بانک مرکزی", "قیمت نفت", "کمبود سوخت",
        "هوش مصنوعی", "تراشه", "اختلال گسترده", "قطع برق", "قطع گاز",
        "قانون", "تصویب", "ممنوعیت", "فراخوان", "major", "merger",
        "acquisition", "lawsuit", "antitrust", "interest rate", "inflation",
        "oil price", "ai", "chip",
    ))
    if security or critical:
        return 3
    if major_business or major:
        return 2
    return 1


def is_publishable(main, candidate):
    title = _norm(candidate.get("title", ""))
    if len(title) < 12:
        return False, 0, "short-title"

    lower = title.lower()
    if any(x.lower() in lower for x in LOW_VALUE):
        return False, 0, "low-value"

    body = _text(candidate).lower()
    has_event = any(x.lower() in lower or x.lower() in body[:3000] for x in HIGH_IMPACT + ACTION_TERMS)

    score = event_score(main, candidate)
    if _high_impact_security_override(candidate):
        score = max(score, MIN_EVENT_SCORE + 2)
        return True, score, "high-impact-security-override"

    if _major_business_legal_override(candidate):
        score = max(score, MIN_EVENT_SCORE + 1)
        return True, score, "major-business-legal-override"

    if not has_event:
        return False, 0, "no-concrete-event"

    if score < MIN_EVENT_SCORE:
        return False, score, "below-event-threshold"

    return True, score, "ok"


def _tokens(main, title):
    try:
        return set(main.story_tokens(title))
    except Exception:
        return {
            x for x in re.findall(r"[\w\u0600-\u06ff]+", _norm(title).lower())
            if len(x) > 2 and x not in GENERIC
        }


def same_event(main, a, b):
    if main.same_story(a, b):
        return True
    ta = _tokens(main, a.get("title", ""))
    tb = _tokens(main, b.get("title", ""))
    if not ta or not tb:
        return False
    common = ta & tb
    if len(common) < 3:
        return False
    ratio = len(common) / max(1, min(len(ta), len(tb)))
    nums_a = set(re.findall(r"\d+", main.normalize_digits(a.get("title", ""))))
    nums_b = set(re.findall(r"\d+", main.normalize_digits(b.get("title", ""))))
    shared_number = bool(nums_a & nums_b)
    return ratio >= 0.78 or (ratio >= 0.62 and shared_number)


def _dedup_events(main, candidates):
    groups = []
    for candidate in candidates:
        placed = False
        for group in groups:
            if same_event(main, candidate, group[0]):
                group.append(candidate)
                placed = True
                break
        if not placed:
            groups.append([candidate])

    selected = []
    for group in groups:
        best = max(
            group,
            key=lambda c: (
                event_score(main, c),
                source_reliability(main, c),
                c.get("importance", 0),
                c.get("published_at") or datetime.min.replace(tzinfo=timezone.utc),
            ),
        )
        best["intelligence_event_cluster"] = len(group)
        selected.append(best)
    return selected


def _write_health(state):
    try:
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        with open(HEALTH_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        print(f"V13 HEALTH WRITE ERROR: {exc}", flush=True)


def _load_rejected_history():
    try:
        with open(REJECTED_NEWS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_rejected_history(history):
    try:
        history = history[-MAX_REJECTED_NEWS_HISTORY:]
        with open(REJECTED_NEWS_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        print(f"V13 REJECTED NEWS WRITE ERROR: {exc}", flush=True)


def _rejected_record(main, candidate, score, reason, stage="intelligence_filter"):
    title = _norm(candidate.get("title", ""))
    published_at = candidate.get("published_at")
    if hasattr(published_at, "isoformat"):
        published_at = published_at.isoformat()
    url = candidate.get("resolved_link") or candidate.get("link") or ""
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "title": title,
        "source": _source_host(main, candidate) or candidate.get("source", "") or "unknown",
        "category": candidate.get("category", ""),
        "published_at": published_at or "",
        "url": url,
        "age_seconds": candidate.get("age_seconds"),
        "intelligence_score": score,
        "reason": reason,
        "stage": stage,
        "high_impact_security_candidate": _high_impact_security_override(candidate),
        "major_business_legal_candidate": _major_business_legal_override(candidate),
    }


def install(main):
    original_collect = main.collect_candidates
    original_process = main.process_news
    original_strict_gate = getattr(main, "is_strictly_useful_news", None)
    strict_rejection_records = []

    if original_strict_gate is not None:
        def _intelligence_strict_gate(candidate):
            if _high_impact_security_override(candidate):
                print(
                    "V13 INTELLIGENCE: high-impact security override -> "
                    f"{candidate.get('title', '')}",
                    flush=True,
                )
                return True
            result = original_strict_gate(candidate)
            if not result:
                strict_rejection_records.append(
                    _rejected_record(
                        main, candidate, 0, "strict-pre-intelligence",
                        stage="strict_gate",
                    )
                )
            return result
        main.is_strictly_useful_news = _intelligence_strict_gate

    state = {
        "status": "starting",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "raw_candidates": 0,
        "strict_rejected": 0,
        "event_duplicates_removed": 0,
        "selected_for_publication": 0,
        "published": 0,
        "failed_publications": 0,
        "top_sources": {},
        "last_errors": [],
        "rejected_news_this_run": [],
    }

    def intelligent_collect(hash_history, title_history):
        candidates = original_collect(hash_history, title_history)
        state["raw_candidates"] = len(candidates)

        if strict_rejection_records:
            history = _load_rejected_history()
            history.extend(strict_rejection_records)
            _save_rejected_history(history)
            state["rejected_news_this_run"].extend(strict_rejection_records)
            strict_rejection_records.clear()

        filtered = []
        rejected = Counter()
        rejected_records = []
        evaluated = []

        for candidate in candidates:
            ok, score, reason = is_publishable(main, candidate)
            candidate["intelligence_score"] = score
            evaluated.append((candidate, ok, score, reason))
            if not ok:
                rejected[reason] += 1
                record = _rejected_record(main, candidate, score, reason)
                rejected_records.append(record)
                print(
                    f"V13 INTELLIGENCE: rejected [{reason}] "
                    f"{candidate.get('title', '')}",
                    flush=True,
                )
                continue
            candidate["importance"] = max(
                int(candidate.get("importance", 0) or 0),
                score,
            )
            filtered.append(candidate)

        state["strict_rejected"] = sum(rejected.values()) + len(state["rejected_news_this_run"])
        state["rejected_news_this_run"] = rejected_records

        history = _load_rejected_history()
        history.extend(rejected_records)
        _save_rejected_history(history)

        publishable_before_dedup = sum(1 for _, ok, _, _ in evaluated if ok)
        filtered = _dedup_events(main, filtered)
        state["event_duplicates_removed"] = max(
            0, publishable_before_dedup - len(filtered)
        )

        filtered.sort(
            key=lambda c: (
                int(c.get("intelligence_score", 0)),
                int(c.get("importance", 0)),
                source_reliability(main, c),
                c.get("published_at") or datetime.min.replace(tzinfo=timezone.utc),
            ),
            reverse=True,
        )

        # Editorial priority gate:
        # Never fill the channel with routine/low-tier stories when a major
        # or critical event is available. If no major story exists at all,
        # publish nothing rather than substituting a weak story.
        for candidate in filtered:
            candidate["publication_tier"] = _publication_tier(candidate)

        highest_tier = max(
            (int(c.get("publication_tier", 1) or 1) for c in filtered),
            default=0,
        )
        if highest_tier >= 3:
            eligible = [c for c in filtered if int(c.get("publication_tier", 1) or 1) >= 3]
        elif highest_tier >= 2:
            eligible = [c for c in filtered if int(c.get("publication_tier", 1) or 1) >= 2]
        else:
            eligible = []

        selected = []
        families = Counter()
        for candidate in eligible:
            family = main.category_family(candidate.get("category", ""))
            if families[family] >= 2 and candidate.get("intelligence_score", 0) < 12:
                continue
            selected.append(candidate)
            families[family] += 1
            if len(selected) >= MAX_NEWS_PER_RUN:
                break

        state["selected_for_publication"] = len(selected)
        state["top_sources"] = dict(Counter(
            _source_host(main, x) or "unknown" for x in selected
        ))
        state["status"] = "collect-complete"
        _write_health(state)

        print(
            f"V13 INTELLIGENCE: {len(candidates)} candidates -> "
            f"{len(filtered)} event-valid -> {len(selected)} selected",
            flush=True,
        )
        return selected

    def tracked_process(candidate, hash_history, title_history):
        try:
            result = original_process(candidate, hash_history, title_history)
            if result:
                state["published"] += 1
            else:
                state["failed_publications"] += 1
            _write_health(state)
            return result
        except Exception as exc:
            state["failed_publications"] += 1
            state["last_errors"].append(str(exc)[:300])
            state["last_errors"] = state["last_errors"][-5:]
            _write_health(state)
            raise

    main.collect_candidates = intelligent_collect
    main.process_news = tracked_process

    original_main = main.main

    def tracked_main():
        started = time.time()
        state["status"] = "running"
        _write_health(state)
        try:
            result = original_main()
            state["status"] = "success"
            state["runtime_seconds"] = round(time.time() - started, 1)
            _write_health(state)
            return result
        except Exception as exc:
            state["status"] = "failed"
            state["runtime_seconds"] = round(time.time() - started, 1)
            state["last_errors"].append(str(exc)[:300])
            state["last_errors"] = state["last_errors"][-5:]
            _write_health(state)
            raise

    main.main = tracked_main
    print(
        "V13 INTELLIGENCE ACTIVE: event scoring + semantic event dedup + "
        f"source reliability + max {MAX_NEWS_PER_RUN} news/run + health monitor "
        "+ rejected-news audit",
        flush=True,
    )
