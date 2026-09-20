"""NABZ V13 Google discovery quality filter.

Keeps Google News as a free discovery layer, but blocks low-value local/
non-Iranian stories before they reach Telegram. Direct RSS/API candidates
are left untouched.
"""

import re


IRAN_TERMS = (
    "iran", "tehran", "persian", "ایران", "تهران", "ایرانی",
    "iranian", "iran's", "ایرانیان",
)

GLOBAL_TERMS = (
    "trump", "white house", "congress", "pentagon", "nato", "un", "european union",
    "europe", "russia", "ukraine", "china", "taiwan", "japan", "south korea",
    "north korea", "israel", "palestine", "gaza", "lebanon", "syria", "iraq",
    "yemen", "saudi", "turkey", "india", "pakistan", "afghanistan", "election",
    "sanctions", "ceasefire", "war", "missile", "airstrike", "invasion",
    "nuclear", "diplomacy", "summit", "president", "prime minister", "parliament",
    "central bank", "federal reserve", "ecb", "opec", "oil", "gas", "inflation",
    "interest rate", "tariff", "trade war", "stock market", "bitcoin",
    "openai", "chatgpt", "gemini", "deepmind", "anthropic", "claude", "nvidia",
    "microsoft", "apple", "google", "meta", "amazon", "tesla", "spacex",
    "artificial intelligence", "robotics", "semiconductor", "chip",
    "cybersecurity", "cyber attack", "5g", "iphone", "android",
    "world cup", "olympics", "champions league", "premier league", "fifa",
    "nba", "nfl", "formula 1", "f1", "ufc", "wimbledon", "atp", "wta",
)

MAJOR_EVENT_TERMS = (
    "breaking", "developing", "major", "historic", "global", "worldwide",
    "international", "national", "emergency", "earthquake", "tsunami",
    "hurricane", "plane crash", "explosion", "mass casualty",
    "مهم", "فوری", "جهان", "بین الملل", "بین‌الملل", "زلزله", "انفجار",
    "جنگ", "حمله", "موشک", "تحریم", "آتش بس", "آتش‌بس",
)

LOCAL_NOISE_TERMS = (
    "morgantown", "nashville", "county", "township", "school district",
    "high school", "college football", "local police", "local officials",
    "city council", "mayor", "assistance expo", "housing program",
    "hvac", "heat keeps", "weather forecast", "festival", "fundraiser",
    "community event", "church event", "traffic alert", "road closure",
    "teen mom", "local reporter", "tv reporter", "sports reporter",
    "arrested after", "stolen trailer", "stamp duty", "lingerie",
    "jazz festival", "farmers market", "county fair",
)

LOCAL_HOST_HINTS = (
    "wsmv", "wdtv", "kait", "kplc", "1011now", "localnews",
    "wxyz", "wspa", "wreg", "wbtv",
)


def _text(candidate):
    return " ".join(
        str(candidate.get(k, "") or "")
        for k in ("title", "summary", "article_text")
    ).lower()


def _contains(text, terms):
    return any(term in text for term in terms)


def _has_global_signal(text):
    if _contains(text, GLOBAL_TERMS):
        return True
    # Avoid substring false positives from short tokens such as "AI", "UN", etc.
    return bool(re.search(r"(?<![A-Za-z])(?:ai|un|f1)(?![A-Za-z])", text, re.I))


def _is_local_google_noise(candidate):
    if not candidate.get("is_google"):
        return False

    title = str(candidate.get("title", "") or "")
    text = _text(candidate)
    link = str(
        candidate.get("resolved_link")
        or candidate.get("link")
        or ""
    ).lower()

    has_iran = _contains(text, IRAN_TERMS)
    has_global = _has_global_signal(text)
    has_major_event = _contains(text, MAJOR_EVENT_TERMS)

    if _contains(text, LOCAL_NOISE_TERMS) and not (has_iran or has_global or has_major_event):
        return True

    if any(hint in link for hint in LOCAL_HOST_HINTS) and not (has_iran or has_global or has_major_event):
        return True

    category = str(candidate.get("category", "") or "")

    if category == "ورزش" and not (has_iran or has_global):
        return True

    if category in ("فرهنگ", "سینما", "فیلم و سریال") and not (has_iran or has_global or has_major_event):
        return True

    if category in ("جهان", "اقتصاد", "جامعه", "سلامت", "علم", "بازار", "جهان و ایران"):
        if not (has_iran or has_global or has_major_event):
            return True

    if re.search(r"[A-Za-z]", title) and not (has_iran or has_global or has_major_event):
        return True

    return False


def install(main):
    original = main.collect_candidates

    def filtered_collect_candidates(hash_history, title_history):
        candidates = original(hash_history, title_history)
        clean = []
        removed = 0

        for candidate in candidates:
            if _is_local_google_noise(candidate):
                removed += 1
                print(
                    "V13 GOOGLE QUALITY FILTER: blocked local/irrelevant Google story: "
                    + str(candidate.get("title", "")).strip()
                )
                continue
            clean.append(candidate)

        print(f"V13 GOOGLE QUALITY FILTER: kept={len(clean)} blocked={removed}")
        return clean

    main.collect_candidates = filtered_collect_candidates
    print("V13 Google discovery quality filter: ON")


__all__ = ["install"]
