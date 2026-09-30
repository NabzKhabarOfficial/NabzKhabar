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
        code = int(status)
        if code == 429:
            entry["disabled_until"] = max(float(entry.get("disabled_until", 0)), now + 10 * 60)
        elif code in (500, 502, 503, 504, 599):
            entry["disabled_until"] = max(float(entry.get("disabled_until", 0)), now + 5 * 60)
        elif code in (400, 401, 403, 404, 422):
            entry["disabled_until"] = max(float(entry.get("disabled_until", 0)), now + 60)
        v13_ai_router._save_health(health)
    except Exception as exc:
        print(f"V13 AI ROUTER: hardened cooldown save warning: {exc}")

v13_ai_router._mark_model_failure = _hardened_mark_model_failure

_original_openai_compatible_json = v13_ai_router._openai_compatible_json

def _hardened_openai_compatible_json(main_obj, provider, base_url, api_key, model, prompt, max_output_tokens=900):
    return _original_openai_compatible_json(
        main_obj, provider, base_url, api_key, model, prompt,
        max_output_tokens=max_output_tokens,
    )

v13_ai_router._openai_compatible_json = _hardened_openai_compatible_json


def _bounded_explicit_retry(original, label, attempts=2):
    def wrapped(*args, **kwargs):
        for attempt in range(1, attempts + 1):
            result = original(*args, **kwargs)
            if result is not False:
                return result
            if attempt < attempts:
                delay = attempt * 2
                print(f"V13 PUBLICATION RETRY: {label} explicit failure; retry {attempt + 1}/{attempts} after {delay}s")
                time.sleep(delay)
        return False
    return wrapped

main.send_message = _bounded_explicit_retry(main.send_message, "sendMessage")
main.send_photo = _bounded_explicit_retry(main.send_photo, "sendPhoto")
main.send_video = _bounded_explicit_retry(main.send_video, "sendVideo")

_original_policy_scope = v13_policy_guard._foreign_local_only
_GLOBAL_CRITICAL_SCOPE = re.compile(r"(?:saudi\s+arabia|saudi|mecca|makkah|medina|madinah|red\s+sea|hormuz|strait\s+of\s+hormuz|حوثی|عربستان|مکه|مدینه|دریای\s+سرخ|تنگه\s+هرمز|تنگه هرمز)", re.I)
_GLOBAL_CRITICAL_EVENT = re.compile(r"(?:attack|strike|missile|drone|war|conflict|ceasefire|red\s+line|military|evacuation|حمله|حمله موشکی|موشک|پهپاد|جنگ|درگیری|آتش\s*بس|خط\s*قرمز|نظامی|تخلیه)", re.I)

def _hardened_policy_scope(candidate):
    text = " ".join(str(candidate.get(k, "") or "") for k in ("title", "summary", "description"))
    if _GLOBAL_CRITICAL_SCOPE.search(text) and _GLOBAL_CRITICAL_EVENT.search(text):
        return False
    return _original_policy_scope(candidate)

v13_policy_guard._foreign_local_only = _hardened_policy_scope

_original_freshness_critical = v13_freshness_rescue._is_critical
_MAJOR_POLITICAL_CHANGE = re.compile(r"(?:استعفا|کناره\s*گیری|انتخابات\s+زودهنگام|resign|resigned|resignation|snap\s+election|early\s+election)", re.I)
_MAJOR_POLITICAL_ACTOR = re.compile(r"(?:رئیس\s*جمهور|رئیس‌جمهور|نخست\s*وزیر|دولت|پارلمان|president|prime\s+minister|government|parliament)", re.I)
_STRATEGIC_CHANGE = re.compile(r"(?:تنگه\s+هرمز|مذاکره|آتش\s*بس|صلح|پیشنهاد|راه\s*حل|جنگ|حمله|استارلینک|Hormuz|negotiat|ceasefire|peace\s+plan|roadmap|conflict|attack)", re.I)
_STRATEGIC_ACTOR = re.compile(r"(?:ایران|آمریکا|اسرائیل|روسیه|اوکراین|صربستان|serbia|iran|us|u\.s\.|israel|russia|ukraine)", re.I)

def _editorial_freshness_critical(candidate):
    if _original_freshness_critical(candidate):
        return True
    text = f"{candidate.get('title', '')} {candidate.get('summary', '')}"
    if _MAJOR_POLITICAL_CHANGE.search(text) and _MAJOR_POLITICAL_ACTOR.search(text):
        return True
    if _STRATEGIC_CHANGE.search(text) and _STRATEGIC_ACTOR.search(text):
        return True
    return False

v13_freshness_rescue._is_critical = _editorial_freshness_critical


def _history_rescue_candidate(candidate):
    if not candidate.get("freshness_rescued"):
        return False
    try:
        return bool(v13_freshness_rescue._is_critical(candidate) or v13_global_rescue._is_global_critical(candidate))
    except Exception:
        return False


def _patch_history_rescue_pipeline():
    collect_source = inspect.getsource(main.collect_candidates)
    old_collect_hash = '''        if old_hash in hash_history:\n\n            history_skipped += 1\n\n            print(\n                f"PRE-SKIPPED OLD HASH: "\n                f"{title}"\n            )\n\n            continue\n'''
    new_collect_hash = '''        if old_hash in hash_history:\n\n            if _history_rescue_candidate(item):\n                item["_history_rescue_bypass"] = True\n                print(f"V13 HISTORY RESCUE BYPASS: old hash -> {title}")\n            else:\n                history_skipped += 1\n                print(f"PRE-SKIPPED OLD HASH: {title}")\n                continue\n'''
    old_collect_semantic = '''        if history_contains_story(\n            title,\n            title_history\n        ):\n\n            history_skipped += 1\n\n            print(\n                f"PRE-SKIPPED SEMANTIC: "\n                f"{title}"\n            )\n\n            continue\n'''
    new_collect_semantic = '''        if history_contains_story(\n            title,\n            title_history\n        ):\n\n            if _history_rescue_candidate(item):\n                item["_history_rescue_bypass"] = True\n                print(f"V13 HISTORY RESCUE BYPASS: semantic -> {title}")\n            else:\n                history_skipped += 1\n                print(f"PRE-SKIPPED SEMANTIC: {title}")\n                continue\n'''
    old_collect_final = '''        if history_contains_story(\n            title,\n            title_history\n        ):\n            continue\n\n        if make_history_key(\n            title,\n            link\n        ) in hash_history:\n            continue\n'''
    new_collect_final = '''        if history_contains_story(\n            title,\n            title_history\n        ) and not item.get("_history_rescue_bypass"):\n            continue\n\n        if (\n            make_history_key(\n                title,\n                link\n            ) in hash_history\n            and not item.get("_history_rescue_bypass")\n        ):\n            continue\n'''
    for old, new, label in ((old_collect_hash, new_collect_hash, "collect hash"), (old_collect_semantic, new_collect_semantic, "collect semantic"), (old_collect_final, new_collect_final, "final collect")):
        if old not in collect_source:
            raise RuntimeError(f"V13 HISTORY PATCH FAILED: {label} anchor missing")
        collect_source = collect_source.replace(old, new, 1)

    process_source = inspect.getsource(main.process_news)
    old_process_hash = '''    if history_key in hash_history:\n\n        print(\n            "SKIPPED: old hash history"\n        )\n\n        return False\n'''
    new_process_hash = '''    if history_key in hash_history and not candidate.get("_history_rescue_bypass"):\n\n        print(\n            "SKIPPED: old hash history"\n        )\n\n        return False\n'''
    old_process_semantic = '''    if history_contains_story(\n        original_title,\n        title_history\n    ):\n\n        print(\n            "SKIPPED: semantic history"\n        )\n\n        return False\n'''
    new_process_semantic = '''    if (\n        history_contains_story(\n            original_title,\n            title_history\n        )\n        and not candidate.get("_history_rescue_bypass")\n    ):\n\n        print(\n            "SKIPPED: semantic history"\n        )\n\n        return False\n'''
    for old, new, label in ((old_process_hash, new_process_hash, "process hash"), (old_process_semantic, new_process_semantic, "process semantic")):
        if old not in process_source:
            raise RuntimeError(f"V13 HISTORY PATCH FAILED: {label} anchor missing")
        process_source = process_source.replace(old, new, 1)

    filename = inspect.getsourcefile(main.collect_candidates) or "v13_standalone.py"
    namespace = main.__dict__
    namespace["_history_rescue_candidate"] = _history_rescue_candidate
    exec(compile(collect_source, filename, "exec"), namespace)
    exec(compile(process_source, filename, "exec"), namespace)

    original_collect = main.collect_candidates
    def _editorial_category_normalized_collect(hash_history, title_history):
        candidates = original_collect(hash_history, title_history)
        for item in candidates:
            title = str(item.get("title", "") or "").lower()
            if any(x in title for x in ("serbia", "serbian", "vucic", "بلگراد", "صربستان", "ووجیچ")):
                item["category"] = "جهان"
            elif any(x in title for x in ("un general assembly", "unga", "سازمان ملل", "مجمع عمومی")):
                item["category"] = "جهان"
        return candidates
    main.collect_candidates = _editorial_category_normalized_collect
    print("V13 HISTORY/EDITORIAL PRIORITY PATCH: active", flush=True)


if __name__ == "__main__":
    _patch_history_rescue_pipeline()
    print("V13 ENGINE LAUNCH: run_bot -> v13_standalone.main()", flush=True)
    result = main.main()
    if result is False:
        raise SystemExit(1)
