import re
import sys
import time

import v13_standalone as main
import v13_media_branding
import v13_ai_router
import v13_argos_translate
import v13_content_enhancer
import v13_ad_filter
import v13_intelligence
import v13_freshness_rescue
import v13_critical_rescue
import v13_editorial_formatter
import v13_policy_guard

# ---------------------------------------------------------------------------
# V13 HARDENING
# Keep the news runtime independent, but add a small set of high-value Persian
# feeds so the channel can still publish when foreign-language AI providers are
# quota/rate limited. These are RSS-only, free, and do not require API keys.
# ---------------------------------------------------------------------------
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

# Add Persian-language Google News discovery as a second path. This improves
# coverage without introducing another API or another paid dependency.
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

# The previous run showed Gemini 429/503 churn every ~15 minutes. Extend the
# persisted cooldown for rate-limit/server failures so ten-minute scheduled
# runs do not repeatedly hammer unhealthy models. This is only a circuit
# breaker; it does not disable healthy models permanently.
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

# Final scope correction: a Saudi/Red Sea/Hormuz geopolitical event must never
# be mistaken for routine foreign-local reporting merely because only one
# country appears in the headline. Routine city/local stories remain blocked.
_original_policy_scope = v13_policy_guard._foreign_local_only
_GLOBAL_CRITICAL_SCOPE = re.compile(
    r"(?:saudi\s+arabia|saudi|mecca|makkah|medina|madinah|red\s+sea|hormuz|strait\s+of\s+hormuz|"
    r"حوثی|عربستان|مکه|مدینه|دریای\s+سرخ|تنگه\s+هرمز|تنگه هرمز)",
    re.I,
)
_GLOBAL_CRITICAL_EVENT = re.compile(
    r"(?:attack|strike|missile|drone|war|conflict|ceasefire|red\s+line|military|evacuation|"
    r"حمله|حمله موشکی|موشک|پهپاد|جنگ|درگیری|آتش\s*بس|خط\s*قرمز|نظامی|تخلیه)",
    re.I,
)

def _hardened_policy_scope(candidate):
    text = " ".join(str(candidate.get(k, "") or "") for k in ("title", "summary", "description"))
    if _GLOBAL_CRITICAL_SCOPE.search(text) and _GLOBAL_CRITICAL_EVENT.search(text):
        return False
    return _original_policy_scope(candidate)

v13_policy_guard._foreign_local_only = _hardened_policy_scope

# V13 is the only news runtime. Obsolete legacy engines and patches were removed.
# The final editorial formatter runs immediately before the policy guard so the
# text that reaches Telegram is mobile-first, source-clean, concise and complete.
v13_media_branding.install(main)
v13_ai_router.install(main)
v13_argos_translate.install(main)
v13_content_enhancer.install(main, v13_ai_router)
v13_ad_filter.install(main)
v13_intelligence.install(main)
v13_freshness_rescue.install(main)
v13_critical_rescue.install()
v13_editorial_formatter.install(main)
v13_policy_guard.install(main)

# Re-apply the hardened scope after policy_guard.install(), because that
# installer may replace main's scope callback with its own wrapper.
try:
    _installed_policy_scope = v13_policy_guard._foreign_local_only
    def _final_hardened_scope(candidate):
        text = " ".join(str(candidate.get(k, "") or "") for k in ("title", "summary", "description"))
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
        # Car prices are an independent daily board, so they must use their
        # own Telegram sender rather than the V13 news language gate.
        car_prices.main()
    except Exception as exc:
        print(f"CAR PRICES ERROR: {exc}", flush=True)

    try:
        # Weather is an independent daily board, just like car prices.
        weather.main()
    except Exception as exc:
        print(f"WEATHER ERROR: {exc}", flush=True)

    if news_failed:
        sys.exit(1)
