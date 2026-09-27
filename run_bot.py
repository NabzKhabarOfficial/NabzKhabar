import inspect
import re
import sys
import time

import v13_standalone as main
import v13_media_branding
import v13_ai_router
import v13_content_enhancer
import v13_ad_filter
import v13_intelligence
import v13_quality_gate
import v13_freshness_rescue
import v13_critical_rescue
import v13_global_rescue
import v13_editorial_formatter
import v13_byline_cleaner
import v13_policy_guard

PERSIAN_RSS_FEEDS = [
    ("جهان", "https://feeds.bbci.co.uk/persian/rss.xml"),
    ("جهان", "https://rss.dw.com/xml/rss-fa-all"),
    ("جهان", "https://www.radiofarda.com/api/z-pqpiev-qpp"),
]

existing_rss = {(str(name), str(url)) for name, url in getattr(main, "DIRECT_RSS_FEEDS", [])}
for feed in PERSIAN_RSS_FEEDS:
    if feed not in existing_rss:
        main.DIRECT_RSS_FEEDS.append(feed)
        existing_rss.add(feed)

PERSIAN_GOOGLE_QUERIES = [
    ("جهان", "site:bbc.com/persian اخبار جهان"),
    ("جهان", "site:dw.com/fa-ir اخبار جهان"),
    ("جهان", "site:radiofarda.com جهان"),
]
existing_google = {(str(name), str(url)) for name, url in getattr(main, "GOOGLE_NEWS_FEEDS", [])}
for category, query in PERSIAN_GOOGLE_QUERIES:
    try:
        url = main.google_news_search_url(query)
    except Exception:
        url = ""
    feed = (category, url)
    if url and feed not in existing_google:
        main.GOOGLE_NEWS_FEEDS.append(feed)
        existing_google.add(feed)

_original_mark_model_failure = v13_ai_router._mark_model_failure

def _hardened_mark_model_failure(model, status):
    _original_mark_model_failure(model, status)
    try:
        health = v13_ai_router._load_health()
        entry = health.setdefault(model, {})
        now = int(time.time())
        if int(status) == 429:
            entry["disabled_until"] = max(float(entry.get("disabled_until", 0)), now + 60 * 60)
        elif int(status) in (500, 502, 503, 504):
            entry["disabled_until"] = max(float(entry.get("disabled_until", 0)), now + 20 * 60)
        v13_ai_router._save_health(health)
    except Exception as exc:
        print(f"V13 AI ROUTER: hardened cooldown save warning: {exc}")

v13_ai_router._mark_model_failure = _hardened_mark_model_failure

_original_policy_scope = v13_policy_guard._foreign_local_only
_GLOBAL_CRITICAL_SCOPE = re.compile(
    r"(?:saudi\s+arabia|saudi|mecca|makkah|medina|madinah|red\s+sea|hormuz|strait\s+of\s+hormuz|"
    r"حوثی|عربستان|مکه|مدینه|دریای\s+سرخ|تنگه\s+هرمز|تنگه هرمز)", re.I,
)
_GLOBAL_CRITICAL_EVENT = re.compile(
    r"(?:attack|strike|missile|drone|war|conflict|ceasefire|red\s+line|military|evacuation|"
    r"حمله|حمله موشکی|موشک|پهپاد|جنگ|درگیری|آتش\s*بس|خط\s*قرمز|نظامی|تخلیه)", re.I,
)

def _hardened_policy_scope(candidate):
    text = " ".join(str(candidate.get(k, "") or "") for k in ("title", "summary", "description"))
    if _GLOBAL_CRITICAL_SCOPE.search(text) and _GLOBAL_CRITICAL_EVENT.search(text):
        return False
    return _original_policy_scope(candidate)

v13_policy_guard._foreign_local_only = _hardened_policy_scope


def _history_rescue_candidate(candidate):
    """Only bypass history for a late, objectively critical rescue candidate.

    Ordinary fresh stories and already-published critical stories remain protected
    by the normal seven-day semantic history. The bypass is intentionally tied to
    freshness_rescued so a missed late-breaking event can enter scoring once.
    """
    if not candidate.get("freshness_rescued"):
        return False
    try:
        return bool(
            v13_freshness_rescue._is_critical(candidate)
            or v13_global_rescue._is_global_critical(candidate)
        )
    except Exception:
        return False


def _patch_history_rescue_pipeline():
    """Patch V13's pre-scoring history gate without weakening final dedup.

    Previous runs showed that the freshness/global rescue correctly recovered
    important stories, but collect_candidates removed them again before the
    intelligence layer could score them. This patch marks only late critical
    rescues and lets them reach scoring. process_news bypasses only its two
    initial history checks for that same marker; the final AI-title duplicate
    check remains untouched.
    """
    collect_source = inspect.getsource(main.collect_candidates)
    old_collect_hash = '''        if old_hash in hash_history:\n\n            history_skipped += 1\n\n            print(\n                f"PRE-SKIPPED OLD HASH: "\n                f"{title}"\n            )\n\n            continue\n'''
    new_collect_hash = '''        if old_hash in hash_history:\n\n            if _history_rescue_candidate(item):\n                item["_history_rescue_bypass"] = True\n                print(\n                    f"V13 HISTORY RESCUE BYPASS: old hash -> "\n                    f"{title}"\n                )\n            else:\n                history_skipped += 1\n                print(\n                    f"PRE-SKIPPED OLD HASH: "\n                    f"{title}"\n                )\n                continue\n'''
    old_collect_semantic = '''        if history_contains_story(\n            title,\n            title_history\n        ):\n\n            history_skipped += 1\n\n            print(\n                f"PRE-SKIPPED SEMANTIC: "\n                f"{title}"\n            )\n\n            continue\n'''
    new_collect_semantic = '''        if history_contains_story(\n            title,\n            title_history\n        ):\n\n            if _history_rescue_candidate(item):\n                item["_history_rescue_bypass"] = True\n                print(\n                    f"V13 HISTORY RESCUE BYPASS: semantic -> "\n                    f"{title}"\n                )\n            else:\n                history_skipped += 1\n                print(\n                    f"PRE-SKIPPED SEMANTIC: "\n                    f"{title}"\n                )\n                continue\n'''
    old_collect_final = '''        if history_contains_story(\n            title,\n            title_history\n        ):\n            continue\n\n        if make_history_key(\n            title,\n            link\n        ) in hash_history:\n            continue\n'''
    new_collect_final = '''        if history_contains_story(\n            title,\n            title_history\n        ) and not item.get("_history_rescue_bypass"):\n            continue\n\n        if (\n            make_history_key(\n                title,\n                link\n            ) in hash_history\n            and not item.get("_history_rescue_bypass")\n        ):\n            continue\n'''
    for old, new, label in (
        (old_collect_hash, new_collect_hash, "collect hash history"),
        (old_collect_semantic, new_collect_semantic, "collect semantic history"),
        (old_collect_final, new_collect_final, "final collect history"),
    ):
        if old not in collect_source:
            raise RuntimeError(f"V13 HISTORY PATCH FAILED: {label} anchor missing")
        collect_source = collect_source.replace(old, new, 1)

    process_source = inspect.getsource(main.process_news)
    old_process_hash = '''    if history_key in hash_history:\n\n        print(\n            "SKIPPED: old hash history"\n        )\n\n        return False\n'''
    new_process_hash = '''    if history_key in hash_history and not candidate.get("_history_rescue_bypass"):\n\n        print(\n            "SKIPPED: old hash history"\n        )\n\n        return False\n'''
    old_process_semantic = '''    if history_contains_story(\n        original_title,\n        title_history\n    ):\n\n        print(\n            "SKIPPED: semantic history"\n        )\n\n        return False\n'''
    new_process_semantic = '''    if (\n        history_contains_story(\n            original_title,\n            title_history\n        )\n        and not candidate.get("_history_rescue_bypass")\n    ):\n\n        print(\n            "SKIPPED: semantic history"\n        )\n\n        return False\n'''
    for old, new, label in (
        (old_process_hash, new_process_hash, "process hash history"),
        (old_process_semantic, new_process_semantic, "process semantic history"),
    ):
        if old not in process_source:
            raise RuntimeError(f"V13 HISTORY PATCH FAILED: {label} anchor missing")
        process_source = process_source.replace(old, new, 1)

    filename = inspect.getsourcefile(main.collect_candidates) or "v13_standalone.py"
    namespace = main.__dict__
    exec(compile(collect_source, filename, "exec"), namespace)
    exec(compile(process_source, filename, "exec"), namespace)

    # Correct source-family metadata before intelligence selection. A feed's
    # configured category must never make a clearly foreign geopolitical event
    # look like domestic Iranian news.
    original_collect = main.collect_candidates
    def _editorial_category_normalized_collect(hash_history, title_history):
        candidates = original_collect(hash_history, title_history)
        for item in candidates:
            title = str(item.get("title", "") or "").lower()
            if any(x in title for x in (
                "serbia", "serbian", "vucic", "بلگراد", "صربستان", "ووجیچ",
            )):
                item["category"] = "جهان"
            elif any(x in title for x in (
                "un general assembly", "unga", "سازمان ملل", "مجمع عمومی",
            )):
                item["category"] = "جهان"
        return candidates
    main.collect_candidates = _editorial_category_normalized_collect

    print("V13 HISTORY/EDITORIAL PRIORITY PATCH: active", flush=True)


_patch_history_rescue_pipeline()

# Install source/media/AI layers. History rescue must be patched BEFORE
# intelligence captures collect_candidates/process_news.
v13_media_branding.install(main)
v13_ai_router.install(main)
v13_content_enhancer.install(main, v13_ai_router)
v13_ad_filter.install(main)
v13_intelligence.install(main)

# Promote objectively critical rescued events and major political changes.
_original_publication_tier = v13_intelligence._publication_tier

def _priority_publication_tier(candidate):
    tier = int(_original_publication_tier(candidate) or 1)
    title = str(candidate.get("title", "") or "").lower()
    critical_rescue = bool(
        candidate.get("freshness_rescued")
        and (
            v13_freshness_rescue._is_critical(candidate)
            or v13_global_rescue._is_global_critical(candidate)
        )
    )
    casualty_or_public_safety = any(x in title for x in (
        "کشته", "زخمی", "مفقود", "به شهادت رسید", "به شهادت رسیدند",
        "تیراندازی", "انفجار", "حمله", "زلزله", "سیل",
        "killed", "dead", "wounded", "missing", "mass shooting", "explosion",
    ))
    major_political_change = any(x in title for x in (
        "استعفا", "کناره گیری", "کناره‌گیری", "انتخابات زودهنگام",
        "resign", "resigned", "resignation", "snap election",
    )) and any(x in title for x in (
        "رئیس جمهور", "رئیس‌جمهور", "نخست وزیر", "دولت", "پارلمان", "president",
        "prime minister", "government", "parliament",
    ))
    if critical_rescue or (casualty_or_public_safety and any(x in title for x in ("ایران", "آمریکا", "روسیه", "اوکراین", "اسرائیل", "صربستان", "britain", "serbia", "iran", "russia", "ukraine", "israel"))):
        return max(tier, 4)
    if major_political_change:
        return max(tier, 3)
    return tier

v13_intelligence._publication_tier = _priority_publication_tier

v13_quality_gate.install()
v13_freshness_rescue.install(main)
v13_critical_rescue.install()
v13_global_rescue.install()
v13_editorial_formatter.install(main)
v13_byline_cleaner.install(main)
v13_policy_guard.install(main)

try:
    _installed_policy_scope = v13_policy_guard._foreign_local_only
    def _final_hardened_scope(candidate):
        text = " ".join(str(candidate.get(k, "") or "") for k in ("title", "summary", "description"))
        if v13_policy_guard._final_global_security_override(candidate):
            return False
        if _GLOBAL_CRITICAL_SCOPE.search(text) and _GLOBAL_CRITICAL_EVENT.search(text):
            return False
        return _installed_policy_scope(candidate)
    v13_policy_guard._foreign_local_only = _final_hardened_scope
except Exception as exc:
    print(f"V13 SCOPE HARDENING WARNING: {exc}")

import education
import car_prices
import weather

if __name__ == "__main__":
    news_failed = False
    try:
        main.main()
    except Exception as exc:
        news_failed = True
        print(f"NEWS RUNTIME ERROR: {exc}", flush=True)
    try:
        education.main.send_message = main.send_message
        education.post_daily_education()
    except Exception as exc:
        print(f"EDUCATION ERROR: {exc}", flush=True)
    try:
        car_prices.main()
    except Exception as exc:
        print(f"CAR PRICES ERROR: {exc}", flush=True)
    try:
        weather.main()
    except Exception as exc:
        print(f"WEATHER ERROR: {exc}", flush=True)
    if news_failed:
        sys.exit(1)
