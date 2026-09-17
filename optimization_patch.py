from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from datetime import datetime, timezone
import main

_ORIGINAL_SESSION_GET = main.SESSION.get
_GET_CACHE = OrderedDict()
_GET_CACHE_MAX = 80


def _cache_key(url, kwargs):
    params = kwargs.get("params")
    try:
        params_key = tuple(sorted(params.items())) if params else ""
    except Exception:
        params_key = repr(params)
    return (str(url), params_key)


def _cached_get(url, *args, **kwargs):
    if kwargs.get("stream"):
        return _ORIGINAL_SESSION_GET(url, *args, **kwargs)
    key = _cache_key(url, kwargs)
    cached = _GET_CACHE.get(key)
    if cached is not None:
        _GET_CACHE.move_to_end(key)
        return cached
    response = _ORIGINAL_SESSION_GET(url, *args, **kwargs)
    try:
        content_type = response.headers.get("content-type", "").lower()
    except Exception:
        content_type = ""
    cacheable = any(x in content_type for x in (
        "text/html", "application/xhtml", "application/rss+xml",
        "application/atom+xml", "application/xml", "text/xml"
    ))
    if cacheable and getattr(response, "ok", False):
        _GET_CACHE[key] = response
        _GET_CACHE.move_to_end(key)
        while len(_GET_CACHE) > _GET_CACHE_MAX:
            _GET_CACHE.popitem(last=False)
    return response


main.SESSION.get = _cached_get

_ORIGINAL_RESOLVE_GOOGLE = main.resolve_google_news_url
_GOOGLE_RESOLVE_CACHE = {}


def _fast_resolve_google_news_url(url):
    if not url:
        return ""
    if not main.is_google_host(url):
        return main.canonicalize_url(url)
    key = main.canonicalize_url(url)
    if key in _GOOGLE_RESOLVE_CACHE:
        return _GOOGLE_RESOLVE_CACHE[key]
    try:
        response = _ORIGINAL_SESSION_GET(url, timeout=5, allow_redirects=True, stream=True)
        final_url = main.canonicalize_url(response.url)
        try:
            response.close()
        except Exception:
            pass
        if final_url and not main.is_google_host(final_url) and not main.is_social_host(final_url):
            _GOOGLE_RESOLVE_CACHE[key] = final_url
            return final_url
    except Exception as exc:
        print(f"Fast Google resolve failed: {exc}")
    _GOOGLE_RESOLVE_CACHE[key] = ""
    return ""


main.resolve_google_news_url = _fast_resolve_google_news_url

_ORIGINAL_CATEGORY_FAMILY = main.category_family


def _category_family(category):
    value = main.normalize_space(category)
    aliases = {
        "اجتماعی": "جامعه", "جامعه و خانواده": "جامعه", "خانواده": "جامعه",
        "تکنولوژی": "فناوری", "علم و فناوری": "علم", "هنر و فرهنگ": "فرهنگ",
        "سرگرمی": "فرهنگ", "فوتبال": "ورزش", "ورزش جهان": "ورزش",
    }
    return aliases.get(value, _ORIGINAL_CATEGORY_FAMILY(value))


main.category_family = _category_family

_ORIGINAL_CALCULATE_IMPORTANCE = main.calculate_importance
CATEGORY_BOOSTS = {
    "ورزش": 8, "هوش مصنوعی": 7, "فناوری": 5, "جامعه": 6,
    "علم": 5, "فرهنگ": 4, "سلامت": 4, "خودرو": 3,
}


def _calculate_importance(candidate):
    score = _ORIGINAL_CALCULATE_IMPORTANCE(candidate)
    category = main.normalize_space(candidate.get("category", ""))
    family = main.category_family(category)
    return score + CATEGORY_BOOSTS.get(category, CATEGORY_BOOSTS.get(family, 0))


main.calculate_importance = _calculate_importance

_ORIGINAL_DIVERSITY_PENALTY = main.diversity_penalty


def _diversity_penalty(candidate, selected):
    original = _ORIGINAL_DIVERSITY_PENALTY(candidate, selected)
    family = main.category_family(candidate.get("category", ""))
    if not selected:
        return original
    seen = {main.category_family(item.get("category", "")) for item in selected}
    if family not in seen:
        return max(0, original - 7)
    count = sum(1 for item in selected if main.category_family(item.get("category", "")) == family)
    if count == 1:
        return original + 14
    if count == 2:
        return original + 24
    return original + 34


main.diversity_penalty = _diversity_penalty

_ORIGINAL_CLUSTER_CANDIDATES = main.cluster_candidates
_CLUSTER_LIMIT = 90


def _cluster_shortlist(candidates):
    if len(candidates) <= _CLUSTER_LIMIT:
        return _ORIGINAL_CLUSTER_CANDIDATES(candidates)
    now = datetime.now(timezone.utc)
    ranked = []
    for candidate in candidates:
        published = candidate.get("published_at")
        if not published:
            age_hours = 999.0
        else:
            try:
                if published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
                age_hours = max(0.0, (now - published).total_seconds() / 3600.0)
            except Exception:
                age_hours = 999.0
        freshness = max(0.0, 36.0 - age_hours)
        try:
            importance = main.calculate_importance(candidate)
        except Exception:
            importance = 0
        ranked.append((importance + freshness * 0.35, candidate))
    ranked.sort(key=lambda item: item[0], reverse=True)
    selected = []
    seen_families = set()
    for _, candidate in ranked:
        family = main.category_family(candidate.get("category", ""))
        if family and family not in seen_families:
            selected.append(candidate)
            seen_families.add(family)
        if len(selected) >= min(20, _CLUSTER_LIMIT):
            break
    selected_ids = {id(item) for item in selected}
    for _, candidate in ranked:
        if id(candidate) in selected_ids:
            continue
        selected.append(candidate)
        if len(selected) >= _CLUSTER_LIMIT:
            break
    print(f"Performance guard: clustering shortlist {len(candidates)} -> {len(selected)}")
    return _ORIGINAL_CLUSTER_CANDIDATES(selected)


main.cluster_candidates = _cluster_shortlist

# Parallel RSS prefetch. The original collect_candidates() already contains
# all filtering, clustering, history and scoring logic. We only replace its
# feed collector temporarily with a cache-backed function, so every RSS feed
# is fetched once in parallel instead of sequentially.
_ORIGINAL_COLLECT_FEED = main.collect_feed
_FEED_WORKERS = 8


def _prefetch_feeds():
    feed_cache = {}
    feeds = [(c, u, False) for c, u in main.DIRECT_RSS_FEEDS]
    feeds += [(c, u, True) for c, u in main.GOOGLE_NEWS_FEEDS]
    started = time.time()
    with ThreadPoolExecutor(max_workers=_FEED_WORKERS) as executor:
        futures = {
            executor.submit(_ORIGINAL_COLLECT_FEED, category, url, is_google): (category, url, is_google)
            for category, url, is_google in feeds
        }
        for future in as_completed(futures):
            category, url, is_google = futures[future]
            try:
                feed_cache[(category, url, is_google)] = future.result()
            except Exception as exc:
                print(f"Parallel RSS worker failed: {category} | {url} | {exc}")
                feed_cache[(category, url, is_google)] = []
    print(f"Parallel RSS prefetch: {len(feeds)} feeds in {time.time() - started:.1f}s")
    return feed_cache


# Stage timing for verification.
_ORIGINAL_COLLECT_CANDIDATES = main.collect_candidates


def _collect_candidates_with_metrics(hash_history, title_history):
    started = time.time()
    feed_cache = _prefetch_feeds()
    original_feed_collector = main.collect_feed

    def cached_collect_feed(category, url, is_google=False):
        return feed_cache.get((category, url, is_google), [])

    main.collect_feed = cached_collect_feed
    try:
        result = _ORIGINAL_COLLECT_CANDIDATES(hash_history, title_history)
    finally:
        main.collect_feed = original_feed_collector

    print(
        f"Optimization metrics: candidate pipeline {time.time() - started:.1f}s | "
        f"GET cache {len(_GET_CACHE)} | Google cache {len(_GOOGLE_RESOLVE_CACHE)}"
    )
    return result


main.collect_candidates = _collect_candidates_with_metrics
print("Optimization patch active: parallel RSS + clustering guard + caches + diversity")
