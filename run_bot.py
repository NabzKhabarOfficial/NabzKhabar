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
import v13_editorial_final_patch
import v13_post_design
import v13_editor_gate

PERSIAN_RSS_FEEDS = [
    ("جهان", "https://feeds.bbci.co.uk/persian/rss.xml"),
    ("جهان", "https://rss.dw.com/xml/rss-fa-all"),
    ("جهان", "https://www.radiofarda.com/api/z-pqpiev-qpp"),
]

# Fast international breaking-news wires (verified live RSS, 2026-10-01).
# Foreign stories still go through AI translation, the foreign-local policy
# filter and semantic dedup, so these add speed/coverage, not noise.
WORLD_BREAKING_RSS_FEEDS = [
    ("جهان", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("جهان", "https://feeds.skynews.com/feeds/rss/world.xml"),
    ("جهان", "http://www.france24.com/en/top-stories/rss"),
    ("جهان", "https://www.theguardian.com/world/rss"),
    ("جهان", "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"),
    # Earthquakes M4.5+ worldwide (USGS, official, minutes after the event). Only quakes in or
    # near Iran, or M6+ anywhere, are kept (see _keep_quake); the rest never become candidates.
    ("جهان", "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.atom"),
    # Major international sport (Olympics, World Cup, big finals); the sports desk decides.
    ("جهان", "https://feeds.bbci.co.uk/sport/rss.xml"),
]
# Extra Persian agencies for faster Iran coverage (verified live 2026-10-01).
# These hosts were blocked by default; they are unblocked below but held to a
# stricter importance bar (see _install_new_source_quality_gate) so routine
# and local items never reach the channel.
STRICT_IRANIAN_RSS_FEEDS = [
    ("ایران", "https://www.isna.ir/rss"),
    ("ایران", "https://www.mehrnews.com/rss"),
    ("ایران", "https://www.independentpersian.com/rss.xml"),
]
# Added Oct 9 2026 (owner's choice) to fill coverage gaps: economy (prices, markets),
# non-state domestic outlets, Iranian sport and technology. Same strict importance bar.
NEW_IRANIAN_RSS_FEEDS = [
    ("ایران", "https://www.khabaronline.ir/rss"),
    ("ایران", "https://www.entekhab.ir/fa/rss/allnews"),
    ("ایران", "https://fararu.com/fa/rss/allnews"),
    ("ایران", "https://www.eghtesadnews.com/fa/rss/allnews"),
    ("ایران", "https://www.varzesh3.com/rss/all"),
    ("ایران", "https://digiato.com/feed"),
]
STRICT_IRANIAN_RSS_FEEDS = STRICT_IRANIAN_RSS_FEEDS + NEW_IRANIAN_RSS_FEEDS
STRICT_SOURCE_HOSTS = {"isna.ir", "mehrnews.com", "independentpersian.com",
                       "khabaronline.ir", "entekhab.ir", "fararu.com", "eghtesadnews.com",
                       "donya-e-eqtesad.com", "ecoiran.com", "varzesh3.com", "digiato.com", "zoomit.ir"}
PERSIAN_RSS_FEEDS = PERSIAN_RSS_FEEDS + WORLD_BREAKING_RSS_FEEDS + STRICT_IRANIAN_RSS_FEEDS

# Unblock only these hosts (sets are read at call time by the source filters).
for _allowed in (getattr(main, "IRANIAN_ALLOWED_HOSTS", None), getattr(v13_policy_guard, "IRANIAN_ALLOWED_HOSTS", None)):
    if isinstance(_allowed, set):
        _allowed.update(STRICT_SOURCE_HOSTS)
existing_rss = {(str(name), str(url)) for name, url in getattr(main, "DIRECT_RSS_FEEDS", [])}
for feed in PERSIAN_RSS_FEEDS:
    if feed not in existing_rss:
        main.DIRECT_RSS_FEEDS.append(feed)
        existing_rss.add(feed)

PERSIAN_GOOGLE_QUERIES = [
    ("جهان", "site:bbc.com/persian اخبار جهان"),
    ("جهان", "site:dw.com/fa-ir اخبار جهان"),
    ("جهان", "site:radiofarda.com جهان"),
    # Reuters and AP have no public RSS; Google News is the standard route.
    ("جهان", "site:reuters.com world"),
    ("جهان", "site:apnews.com world"),
    # Economy and tech outlets without a reliable public RSS (Oct 9 2026).
    ("ایران", "site:donya-e-eqtesad.com"),
    ("ایران", "site:ecoiran.com"),
    ("ایران", "site:zoomit.ir"),
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

def _install_v13_stack():
    """Install the V13 editorial/runtime layers explicitly and exactly once."""
    if getattr(main, "_v13_stack_installed", False):
        return

    v13_media_branding.install(main)
    v13_ai_router.install(main)
    v13_content_enhancer.install(main, v13_ai_router)
    v13_ad_filter.install(main)
    v13_freshness_rescue.install(main)
    v13_editorial_formatter.install(main)
    v13_byline_cleaner.install(main)
    v13_policy_guard.install(main)
    # Must sit *inside* v13_intelligence's tracked_process (installed below)
    # so editorial blocks can be told apart from real Telegram failures.
    _install_editorial_block_classifier()
    v13_quality_gate.install()
    v13_intelligence.install(main)
    v13_critical_rescue.install()
    v13_global_rescue.install()

    # Major sports desk: Iran's teams and athletes, decisive big-stage
    # results and the Tehran derby. Without it every sports story was
    # rejected as "no-concrete-event". The final AI editor still decides.
    try:
        import v13_sports_desk
        v13_sports_desk.install(main)
    except Exception as exc:
        print(f"V13 SPORTS DESK: install skipped: {type(exc).__name__}: {exc}", flush=True)

    # v13_media_branding replaces send_video outright, which silently dropped
    # the bounded retry installed at import time. Re-apply it to send_video
    # only: send_photo is *wrapped* (not replaced) by v13_content_enhancer, so
    # its inner retry is still active and wrapping again would double-retry.
    _ensure_publication_retry(only=("send_video",))

    # Outermost selection gate: skip stories that were editorially blocked in
    # a recent run (e.g. no AI translation passed validation), so the same
    # story is not re-selected and re-failed on every run.
    _install_recent_block_selection_gate()

    # Stricter bar for the newly unblocked Iranian agencies.
    _install_new_source_quality_gate()

    # Visual layer last: wraps the final caption, photo sender and story.
    v13_post_design.install(main, v13_editorial_formatter)

    # Final editor: installed last so no override/rescue layer can bypass it.
    v13_editor_gate.install(main)

    main._v13_stack_installed = True
    print("V13 STACK: all editorial, rescue, media, AI, and health layers installed", flush=True)


# --- Editorial blocks vs. real publication failures -------------------------
# v13_intelligence.tracked_process counts every False from process_news as a
# failed publication, even when no Telegram request was made (final policy
# scope drop, foreign story with no valid AI translation). Those runs then
# failed the "Enforce publication health" step with error "" and the same
# story was re-selected on every run. We classify these editorial blocks,
# correct the telemetry after the run, and remember them for a few hours.
import json as _json

EDITORIAL_BLOCK_STATUSES = {"ai_unavailable_foreign", "policy_scope_blocked"}
_EDITORIAL_BLOCK_KEY = "_editorial_blocks"  # stored in ai_model_health.json (persisted)
_EDITORIAL_BLOCK_TTL_SECONDS = 6 * 60 * 60
_EDITORIAL_BLOCK_MAX = 300
_HEALTH_FILE = "v13_health.json"
_editorial_blocks_this_run = {}


def _norm_title(title):
    try:
        return str(v13_intelligence._norm(title or "")).strip().lower()
    except Exception:
        return re.sub(r"\s+", " ", str(title or "")).strip().lower()


def _load_recent_blocks():
    try:
        blocks = v13_ai_router._load_health().get(_EDITORIAL_BLOCK_KEY) or {}
        now = time.time()
        return {
            k: v for k, v in blocks.items()
            if isinstance(v, dict) and float(v.get("until", 0) or 0) > now
        }
    except Exception as exc:
        print(f"V13 EDITORIAL BLOCKS: load warning: {type(exc).__name__}: {exc}")
        return {}


def _save_recent_blocks(new_blocks):
    if not new_blocks:
        return
    try:
        health = v13_ai_router._load_health()
        blocks = _load_recent_blocks()
        until = time.time() + _EDITORIAL_BLOCK_TTL_SECONDS
        for title, reason in new_blocks.items():
            blocks[title] = {"until": until, "reason": reason}
        if len(blocks) > _EDITORIAL_BLOCK_MAX:
            newest = sorted(blocks.items(), key=lambda kv: kv[1].get("until", 0))[-_EDITORIAL_BLOCK_MAX:]
            blocks = dict(newest)
        health[_EDITORIAL_BLOCK_KEY] = blocks
        v13_ai_router._save_health(health)
    except Exception as exc:
        print(f"V13 EDITORIAL BLOCKS: save warning: {type(exc).__name__}: {exc}")


def _install_editorial_block_classifier():
    inner = main.process_news

    def classified_process(candidate, *args, **kwargs):
        title = _norm_title(candidate.get("title", ""))
        try:
            scope_blocked = bool(v13_policy_guard._foreign_local_only(candidate))
        except Exception:
            scope_blocked = False
        if scope_blocked:
            # Same decision v13_policy_guard makes, but labelled.
            candidate["publication_status"] = "policy_scope_blocked"
            print("V13 FINAL PUBLICATION SCOPE DROP: " + str(candidate.get("title", "") or ""), flush=True)
            _editorial_blocks_this_run[title] = "policy_scope_blocked"
            return False
        result = inner(candidate, *args, **kwargs)
        status = candidate.get("publication_status")
        if not result and status in EDITORIAL_BLOCK_STATUSES:
            _editorial_blocks_this_run[title] = status
        return result

    main.process_news = classified_process


def _install_recent_block_selection_gate():
    recent = _load_recent_blocks()
    if recent:
        print(f"V13 EDITORIAL BLOCKS: {len(recent)} recently blocked stor(y/ies) will not be re-selected", flush=True)
    previous = v13_intelligence.is_publishable

    def recent_block_gate(main_obj, candidate):
        ok, score, reason = previous(main_obj, candidate)
        if ok and recent and _norm_title(candidate.get("title", "")) in recent:
            return False, 0, "recent-editorial-block"
        return ok, score, reason

    v13_intelligence.is_publishable = recent_block_gate


# A story from a STRICT_SOURCE_HOSTS publisher is only publishable when it is
# clearly important: intelligence score at least MIN_EVENT_SCORE + 3 (the same
# "important" level the monitor uses) and never a routine local item.
STRICT_SOURCE_MIN_SCORE_BONUS = 3


def _candidate_host(candidate):
    from urllib.parse import urlparse
    for key in ("resolved_link", "link", "source_url"):
        try:
            host = (urlparse(str(candidate.get(key, "") or "")).hostname or "").lower()
        except Exception:
            host = ""
        if host:
            return host[4:] if host.startswith("www.") else host
    return ""


def _is_strict_source(candidate):
    host = _candidate_host(candidate)
    return any(host == h or host.endswith("." + h) for h in STRICT_SOURCE_HOSTS)


def _install_new_source_quality_gate():
    previous = v13_intelligence.is_publishable
    min_score = int(getattr(v13_intelligence, "MIN_EVENT_SCORE", 7)) + STRICT_SOURCE_MIN_SCORE_BONUS

    def strict_source_gate(main_obj, candidate):
        ok, score, reason = previous(main_obj, candidate)
        if not ok or not _is_strict_source(candidate):
            return ok, score, reason
        title = str(candidate.get("title", "") or "")
        try:
            routine_local = v13_editorial_final_patch._routine_local(title)
        except Exception:
            routine_local = False
        if routine_local:
            return False, 0, "strict-source-local-routine"
        if int(score or 0) < min_score:
            return False, score, f"strict-source-below-importance({score}<{min_score})"
        return ok, score, reason

    v13_intelligence.is_publishable = strict_source_gate
    print(f"V13 STRICT SOURCES: {', '.join(sorted(STRICT_SOURCE_HOSTS))} require score>={min_score}", flush=True)


def _reclassify_editorial_blocks():
    """Persist this run's editorial blocks and fix the run telemetry."""
    if not _editorial_blocks_this_run:
        return
    _save_recent_blocks(_editorial_blocks_this_run)
    try:
        with open(_HEALTH_FILE, "r", encoding="utf-8") as f:
            health = _json.load(f)
    except Exception as exc:
        print(f"V13 EDITORIAL BLOCKS: telemetry read warning: {type(exc).__name__}: {exc}")
        return
    corrected = 0
    for attempt in health.get("publication_attempts") or []:
        if attempt.get("result") != "failed":
            continue
        reason = _editorial_blocks_this_run.get(_norm_title(attempt.get("title", "")))
        if reason:
            attempt["result"] = "editorial_blocked"
            attempt["reason"] = reason
            corrected += 1
    if corrected:
        health["failed_publications"] = max(0, int(health.get("failed_publications", 0) or 0) - corrected)
        health["editorial_blocked_publications"] = int(health.get("editorial_blocked_publications", 0) or 0) + corrected
        with open(_HEALTH_FILE, "w", encoding="utf-8") as f:
            _json.dump(health, f, ensure_ascii=False, indent=2)
        print(f"V13 EDITORIAL BLOCKS: {corrected} attempt(s) reclassified from failed to editorial_blocked", flush=True)


_original_openai_compatible_json = v13_ai_router._openai_compatible_json

def _hardened_openai_compatible_json(main_obj, provider, base_url, api_key, model, prompt, max_output_tokens=900):
    """Reject non-object JSON (string/list) so the router fails over instead of crashing."""
    result, flag = _original_openai_compatible_json(
        main_obj, provider, base_url, api_key, model, prompt,
        max_output_tokens=max_output_tokens,
    )
    if result is not None and not isinstance(result, dict):
        print(f"V13 AI ROUTER: {provider}/{model} returned non-object JSON ({type(result).__name__}); failing over.")
        try:
            v13_ai_router._record_quality_failure(f"{str(provider).lower()}:{model}")
        except Exception:
            pass
        return None, flag
    return result, flag

v13_ai_router._openai_compatible_json = _hardened_openai_compatible_json


def _bounded_explicit_retry(original, label, attempts=2):
    # Only an explicit False (Telegram rejected the request) is retried.
    # None means an ambiguous transport outcome and is never retried, to
    # avoid duplicate publications.
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
    wrapped._v13_retry_wrapped = True
    return wrapped

_PUBLICATION_SENDERS = (("send_message", "sendMessage"), ("send_photo", "sendPhoto"), ("send_video", "sendVideo"))


def _ensure_publication_retry(only=None):
    for attr, label in _PUBLICATION_SENDERS:
        if only is not None and attr not in only:
            continue
        fn = getattr(main, attr, None)
        if fn is not None and not getattr(fn, "_v13_retry_wrapped", False):
            setattr(main, attr, _bounded_explicit_retry(fn, label))
            print(f"V13 PUBLICATION RETRY: re-applied to {attr}", flush=True)

_ensure_publication_retry()

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
# Short Latin actors are word-bounded so "us" does not match inside "business".
_STRATEGIC_ACTOR = re.compile(r"(?:ایران|آمریکا|اسرائیل|روسیه|اوکراین|صربستان|serbia|iran|(?<![a-z])us(?![a-z])|(?<![a-z])u\.s\.|israel|russia|ukraine)", re.I)

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


# The Google News resolver sometimes picks a page asset (e.g. a
# fonts.googleapis.com stylesheet) instead of the publisher URL. Such a
# candidate can never be fetched or published, but it was still selected on
# every run, wasting one of the (max 2) publication slots.
_ASSET_HOSTS = (
    "fonts.googleapis.com", "fonts.gstatic.com", "gstatic.com",
    "ajax.googleapis.com", "apis.google.com", "googletagmanager.com",
    "google-analytics.com",
)
_ASSET_EXTENSIONS = (".css", ".js", ".woff", ".woff2", ".ttf", ".otf", ".ico")


def _is_asset_link(url):
    try:
        from urllib.parse import urlparse
        parsed = urlparse(str(url or "").strip())
    except Exception:
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    if any(host == h or host.endswith("." + h) for h in _ASSET_HOSTS):
        return True
    path = (parsed.path or "").lower()
    return path.endswith(_ASSET_EXTENSIONS) or "/css" == path


_QUAKE_NEAR_IRAN = re.compile(
    r"\b(?:iran|iraq|turkey|t[uü]rkiye|afghanistan|pakistan|turkmenistan|azerbaijan|armenia|"
    r"kuwait|bahrain|qatar|united arab emirates|uae|oman|saudi|caspian|persian gulf)\b", re.I)
_QUAKE_MAG = re.compile(r"\bM\s*([0-9]+(?:\.[0-9])?)", re.I)


def _keep_quake(item):
    """USGS items: keep a quake in or next to Iran, or M6+ anywhere."""
    link = str(item.get("resolved_link") or item.get("link") or "")
    if "earthquake.usgs.gov" not in link:
        return True
    title = str(item.get("title", "") or "")
    found = _QUAKE_MAG.search(title)
    mag = float(found.group(1)) if found else 0.0
    return mag >= 6.0 or bool(_QUAKE_NEAR_IRAN.search(title))


def _drop_asset_link_candidates(candidates):
    kept = []
    for item in candidates:
        link = item.get("resolved_link") or item.get("link") or ""
        if _is_asset_link(link):
            print(f"V13 ASSET LINK DROP: {item.get('title', '')} | {link[:120]}", flush=True)
            continue
        if not _keep_quake(item):
            continue
        kept.append(item)
    return kept


def _patch_history_rescue_pipeline():
    collect_source = inspect.getsource(main.collect_candidates)
    old_collect_hash = '''        if old_hash in hash_history:\n\n            history_skipped += 1\n\n            print(\n                f"PRE-SKIPPED OLD HASH: "\n                f"{title}"\n            )\n\n            continue\n'''
    new_collect_hash = '''        if old_hash in hash_history:\n\n            if _history_rescue_candidate(item):\n                item["_history_rescue_bypass"] = True\n                print(f"V13 HISTORY RESCUE BYPASS: old hash -> {title}")\n            else:\n                history_skipped += 1\n                print(f"PRE-SKIPPED OLD HASH: {title}")\n                continue\n'''
    old_collect_semantic = '''        if history_contains_story(\n            title,\n            title_history\n        ):\n\n            history_skipped += 1\n\n            print(\n                f"PRE-SKIPPED SEMANTIC: "\n                f"{title}"\n            )\n\n            continue\n'''
    new_collect_semantic = '''        if history_contains_story(\n            title,\n            title_history\n        ):\n\n            history_skipped += 1\n            print(f"PRE-SKIPPED SEMANTIC: {title}")\n            continue\n'''
    old_collect_final = '''        if history_contains_story(\n            title,\n            title_history\n        ):\n            continue\n\n        if make_history_key(\n            title,\n            link\n        ) in hash_history:\n            continue\n'''
    new_collect_final = '''        if history_contains_story(\n            title,\n            title_history\n        ):\n            continue\n\n        if (\n            make_history_key(\n                title,\n                link\n            ) in hash_history\n            and not item.get("_history_rescue_bypass")\n        ):\n            continue\n'''
    for old, new, label in ((old_collect_hash, new_collect_hash, "collect hash"), (old_collect_semantic, new_collect_semantic, "collect semantic"), (old_collect_final, new_collect_final, "final collect")):
        if old not in collect_source:
            raise RuntimeError(f"V13 HISTORY PATCH FAILED: {label} anchor missing")
        collect_source = collect_source.replace(old, new, 1)

    process_source = inspect.getsource(main.process_news)
    old_process_hash = '''    if history_key in hash_history:\n\n        print(\n            "SKIPPED: old hash history"\n        )\n\n        return False\n'''
    new_process_hash = '''    if history_key in hash_history and not candidate.get("_history_rescue_bypass"):\n\n        print(\n            "SKIPPED: old hash history"\n        )\n\n        return False\n'''
    old_process_semantic = '''    if history_contains_story(\n        original_title,\n        title_history\n    ):\n\n        print(\n            "SKIPPED: semantic history"\n        )\n\n        return False\n'''
    new_process_semantic = old_process_semantic
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
        candidates = _drop_asset_link_candidates(original_collect(hash_history, title_history))
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
    # Daily boards (weather, car prices, education) are independent of the
    # news engine and must never block or fail it.
    try:
        import daily_boards
        daily_boards.run()
    except Exception as exc:
        print(f"DAILY BOARDS: launcher error: {type(exc).__name__}: {exc}", flush=True)
    _patch_history_rescue_pipeline()
    _install_v13_stack()
    print("V13 ENGINE LAUNCH: run_bot -> v13_standalone.main()", flush=True)
    try:
        result = main.main()
    finally:
        _reclassify_editorial_blocks()
    if result is False:
        raise SystemExit(1)
