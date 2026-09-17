from collections import OrderedDict
import time
import main

# Reuse HTML/XML responses within one run so article text, image and video
# extraction do not download the same publisher page repeatedly.
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

# Google News redirects: fail fast and memoize results.
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
        response = _ORIGINAL_SESSION_GET(
            url, timeout=5, allow_redirects=True, stream=True
        )
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

# Normalize Persian category variants for diversity selection.
_ORIGINAL_CATEGORY_FAMILY = main.category_family


def _category_family(category):
    value = main.normalize_space(category)
    aliases = {
        "اجتماعی": "جامعه",
        "جامعه و خانواده": "جامعه",
        "خانواده": "جامعه",
        "تکنولوژی": "فناوری",
        "علم و فناوری": "علم",
        "هنر و فرهنگ": "فرهنگ",
        "سرگرمی": "فرهنگ",
        "فوتبال": "ورزش",
        "ورزش جهان": "ورزش",
    }
    return aliases.get(value, _ORIGINAL_CATEGORY_FAMILY(value))


main.category_family = _category_family

# Small editorial boosts for categories that tend to lose to Iran/world
# political stories. These remain soft and do not hard-block important news.
_ORIGINAL_CALCULATE_IMPORTANCE = main.calculate_importance
CATEGORY_BOOSTS = {
    "ورزش": 8,
    "هوش مصنوعی": 7,
    "فناوری": 5,
    "جامعه": 6,
    "علم": 5,
    "فرهنگ": 4,
    "سلامت": 4,
    "خودرو": 3,
}


def _calculate_importance(candidate):
    score = _ORIGINAL_CALCULATE_IMPORTANCE(candidate)
    category = main.normalize_space(candidate.get("category", ""))
    family = main.category_family(category)
    return score + CATEGORY_BOOSTS.get(category, CATEGORY_BOOSTS.get(family, 0))


main.calculate_importance = _calculate_importance

# Stronger soft diversity: repeated families become increasingly expensive,
# while unseen families receive a modest bonus. Breaking news can still win.
_ORIGINAL_DIVERSITY_PENALTY = main.diversity_penalty


def _diversity_penalty(candidate, selected):
    original = _ORIGINAL_DIVERSITY_PENALTY(candidate, selected)
    family = main.category_family(candidate.get("category", ""))
    if not selected:
        return original
    seen = {
        main.category_family(item.get("category", "")) for item in selected
    }
    if family not in seen:
        return max(0, original - 7)
    count = sum(
        1 for item in selected
        if main.category_family(item.get("category", "")) == family
    )
    if count == 1:
        return original + 14
    if count == 2:
        return original + 24
    return original + 34


main.diversity_penalty = _diversity_penalty

# Stage timing for the next run so the remaining bottleneck is measurable.
_ORIGINAL_COLLECT_CANDIDATES = main.collect_candidates


def _collect_candidates_with_metrics(hash_history, title_history):
    started = time.time()
    result = _ORIGINAL_COLLECT_CANDIDATES(hash_history, title_history)
    print(
        f"Optimization metrics: candidate pipeline {time.time() - started:.1f}s | "
        f"GET cache {len(_GET_CACHE)} | Google cache {len(_GOOGLE_RESOLVE_CACHE)}"
    )
    return result


main.collect_candidates = _collect_candidates_with_metrics
print("Optimization patch active: GET cache + fast Google resolve + topic diversity")
