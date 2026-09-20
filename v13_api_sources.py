"""
NABZ V13 API news sources.
Freshness contract: only articles published in the last 30 minutes are returned.
Free-first quota policy:
- Currents: max 120 requests/day (250 free/day, 130-request safety reserve).
- World News API: max 45 calls/day, max 4 results/call, keeping worst-case
  search cost below the documented 50-point free quota.
- NewsData.io / GNews: free tiers currently delay fresh articles by 12 hours,
  so they are NOT polled on the free plan. They can be enabled only when the
  caller explicitly sets *_REALTIME=1 (paid/eligible realtime plan).
- GDELT: public/free; no API key or daily API quota is consumed by this layer.
"""

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse

import requests


WINDOW_MINUTES = 30
STATE_FILE = Path("api_usage_state.json")
REQUEST_TIMEOUT = 15

CURR_API_KEY = os.getenv("CURRENTS_API_KEY", "").strip()
WORLD_API_KEY = os.getenv("WORLDNEWS_API_KEY", "").strip()
NEWSDATA_API_KEY = os.getenv("NEWSDATA_API_KEY", "").strip()
GNEWS_API_KEY = os.getenv("GNEWS_API_KEY", "").strip()

# Hard free-tier safety ceilings. These are deliberately below provider limits.
LIMITS = {
    "currents": 120,
    "worldnews": 45,
    "newsdata": 100,
    "gnews": 50,
}

# Explicit opt-in only. Free plans for these providers are delayed and therefore
# cannot satisfy the 30-minute freshness contract.
NEWSDATA_REALTIME = os.getenv("NEWSDATA_REALTIME", "0").strip() == "1"
GNEWS_REALTIME = os.getenv("GNEWS_REALTIME", "0").strip() == "1"


def _utc_day():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load_state():
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if data.get("date") == _utc_day():
            return data
    except Exception:
        pass
    return {"date": _utc_day(), "calls": {}, "last_call": {}}


def _save_state(state):
    try:
        STATE_FILE.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"API QUOTA STATE SAVE ERROR: {exc}")


_STATE = _load_state()


def _reserve(provider):
    limit = LIMITS[provider]
    used = int(_STATE.setdefault("calls", {}).get(provider, 0))
    if used >= limit:
        print(f"API QUOTA GUARD: {provider} daily ceiling reached ({used}/{limit}); skipped.")
        return False
    _STATE["calls"][provider] = used + 1
    _STATE.setdefault("last_call", {})[provider] = datetime.now(timezone.utc).isoformat()
    _save_state(_STATE)
    print(f"API QUOTA: {provider} {used + 1}/{limit}")
    return True


def _parse_dt(value):
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        # Common fallback formats.
        for fmt in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(str(value), fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except Exception:
                continue
    return None


def _fresh(dt):
    if not dt:
        return False
    now = datetime.now(timezone.utc)
    age = (now - dt).total_seconds()
    return 0 <= age <= WINDOW_MINUTES * 60


def _host(url):
    try:
        return urlparse(str(url)).netloc.lower().split(":")[0].removeprefix("www.")
    except Exception:
        return ""


def _candidate(category, title, summary, url, published, image="", source=""):
    dt = _parse_dt(published)
    if not title or not url or not _fresh(dt):
        return None
    return {
        "category": category,
        "title": str(title).strip(),
        "summary": str(summary or "").strip(),
        "link": str(url).strip(),
        "published_at": dt,
        "image_url": str(image or "").strip(),
        "video_url": "",
        "is_google": False,
        "resolved_link": "",
        "source_name": str(source or "").strip(),
        "source_url": "https://" + _host(url) if _host(url) else "",
        "article_text": "",
        "importance": 0,
        "cluster_size": 1,
        "api_source": True,
    }


def _get_json(url, *, headers=None, params=None):
    try:
        r = requests.get(url, headers=headers or {}, params=params or {}, timeout=REQUEST_TIMEOUT)
        if not r.ok:
            print(f"API SOURCE ERROR: {url} -> HTTP {r.status_code}")
            return None
        return r.json()
    except Exception as exc:
        print(f"API SOURCE ERROR: {url} -> {exc}")
        return None


def _currents():
    if not CURR_API_KEY or not _reserve("currents"):
        return []
    data = _get_json(
        "https://api.currentsapi.services/v1/latest-news",
        headers={"Authorization": f"Bearer {CURR_API_KEY}"},
        params={"language": "en", "page_size": 20},
    )
    out = []
    for x in (data or {}).get("news", []):
        c = _candidate(
            "جهان",
            x.get("title"),
            x.get("description"),
            x.get("url"),
            x.get("published"),
            x.get("image"),
            x.get("author"),
        )
        if c:
            out.append(c)
    return out


def _worldnews():
    if not WORLD_API_KEY or not _reserve("worldnews"):
        return []
    # 4 results keeps the documented search cost at <= 1.04 points/call.
    data = _get_json(
        "https://api.worldnewsapi.com/search-news",
        headers={"x-api-key": WORLD_API_KEY},
        params={
            "language": "en",
            "earliest-publish-date": (
                datetime.now(timezone.utc) - timedelta(minutes=WINDOW_MINUTES)
            ).strftime("%Y-%m-%d %H:%M:%S"),
            "latest-publish-date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "sort": "publish-time",
            "number": 4,
        },
    )
    out = []
    for x in (data or {}).get("news", []):
        c = _candidate(
            "جهان",
            x.get("title"),
            x.get("summary") or x.get("text"),
            x.get("url"),
            x.get("publish_date"),
            x.get("image"),
            x.get("author"),
        )
        if c:
            out.append(c)
    return out


def _newsdata():
    if not NEWSDATA_API_KEY or not NEWSDATA_REALTIME:
        if NEWSDATA_API_KEY:
            print("NewsData.io: free/delayed mode detected; 30-minute polling disabled.")
        return []
    if not _reserve("newsdata"):
        return []
    data = _get_json(
        "https://newsdata.io/api/1/latest",
        headers={"X-Api-Key": NEWSDATA_API_KEY},
        params={"language": "en", "timeframe": "30m", "size": 10},
    )
    out = []
    for x in (data or {}).get("results", []):
        c = _candidate(
            "جهان",
            x.get("title"),
            x.get("description"),
            x.get("link"),
            x.get("pubDate"),
            x.get("image_url"),
            x.get("creator"),
        )
        if c:
            out.append(c)
    return out


def _gnews():
    if not GNEWS_API_KEY or not GNEWS_REALTIME:
        if GNEWS_API_KEY:
            print("GNews: free/delayed mode detected; 30-minute polling disabled.")
        return []
    if not _reserve("gnews"):
        return []
    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=WINDOW_MINUTES)
    data = _get_json(
        "https://gnews.io/api/v4/search",
        params={
            "q": "news",
            "lang": "en",
            "max": 10,
            "from": start.isoformat().replace("+00:00", "Z"),
            "to": now.isoformat().replace("+00:00", "Z"),
            "sortby": "publishedAt",
            "apikey": GNEWS_API_KEY,
        },
    )
    out = []
    for x in (data or {}).get("articles", []):
        src = x.get("source") or {}
        c = _candidate(
            "جهان",
            x.get("title"),
            x.get("description") or x.get("content"),
            x.get("url"),
            x.get("publishedAt"),
            x.get("image"),
            src.get("name"),
        )
        if c:
            out.append(c)
    return out


def _gdelt():
    # GDELT DOC API is public and supports a 30-minute timespan directly.
    data = _get_json(
        "https://api.gdeltproject.org/api/v2/doc/doc",
        params={
            "query": "(Iran OR world OR technology OR economy OR sports)",
            "mode": "artlist",
            "format": "json",
            "timespan": "30min",
            "maxrecords": 50,
            "sort": "datedesc",
        },
    )
    out = []
    articles = (data or {}).get("articles", [])
    for x in articles:
        c = _candidate(
            "جهان",
            x.get("title"),
            x.get("seendate"),
            x.get("url"),
            x.get("seendate"),
            x.get("socialimage"),
            x.get("domain"),
        )
        if c:
            out.append(c)
    return out


def collect_api_candidates():
    out = []
    # These calls are intentionally sequential. The quota manager makes the
    # expensive providers deterministic and prevents accidental bursts.
    for name, fn in (
        ("Currents", _currents),
        ("WorldNews", _worldnews),
        ("NewsData", _newsdata),
        ("GNews", _gnews),
        ("GDELT", _gdelt),
    ):
        try:
            items = fn()
            out.extend(items)
            print(f"API SOURCE {name}: {len(items)} fresh candidates")
        except Exception as exc:
            print(f"API SOURCE {name} ERROR: {exc}")
    return out
