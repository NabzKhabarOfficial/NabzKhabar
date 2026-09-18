"""Currents API discovery adapter for Nabz Khabar.

Free-tier only. A local daily request budget prevents scheduled or manual runs
from intentionally exceeding the free-plan allowance. The adapter remains an
additional discovery source; existing source quality, deduplication, AI
localization and publication gates remain authoritative.
"""

import json
import os
from datetime import datetime, timezone

import requests

API_URL = "https://api.currentsapi.services/v2/latest-news"
TIMEOUT = 12
PAGE_SIZE = 20

# Keep a safety margin below the documented free-plan daily allowance.
DAILY_REQUEST_BUDGET = 200
USAGE_FILE = "currents_usage.json"


def _utc_today():
    return datetime.now(timezone.utc).date().isoformat()


def _load_usage():
    today = _utc_today()
    try:
        with open(USAGE_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if data.get("date") != today:
            return {"date": today, "requests": 0}
        return {"date": today, "requests": int(data.get("requests", 0))}
    except Exception:
        return {"date": today, "requests": 0}


def _save_usage(usage):
    temp = f"{USAGE_FILE}.tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(usage, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(temp, USAGE_FILE)


def _reserve_request():
    usage = _load_usage()
    if usage["requests"] >= DAILY_REQUEST_BUDGET:
        print(
            f"CURRENTS: local daily safety budget reached "
            f"({usage['requests']}/{DAILY_REQUEST_BUDGET}); skipping."
        )
        return False

    # Reserve before the HTTP request because an attempted API call can count
    # against the provider quota even when the response is an error/timeout.
    usage["requests"] += 1
    _save_usage(usage)
    print(
        f"CURRENTS REQUEST RESERVED: "
        f"{usage['requests']}/{DAILY_REQUEST_BUDGET} today"
    )
    return True


def _parse_published(value):
    if not value:
        return None
    try:
        text = str(value).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _candidate(article):
    title = str(article.get("title") or "").strip()
    url = str(article.get("url") or "").strip()
    if not title or not url:
        return None

    published_at = _parse_published(article.get("published"))
    categories = article.get("category") or []
    if isinstance(categories, str):
        categories = [categories]

    category_map = {
        "politics_government": "جهان",
        "economy_business_finance": "اقتصاد",
        "science_technology": "فناوری",
        "sport": "ورزش",
        "health": "سلامت",
        "education": "آموزش",
        "environment": "محیط زیست",
        "crime_law_justice": "حوادث",
        "arts_culture_entertainment": "فرهنگ",
        "general": "جهان",
        "society": "جامعه",
        "human_interest": "جامعه",
    }

    category = next(
        (
            category_map.get(str(x).strip().lower())
            for x in categories
            if category_map.get(str(x).strip().lower())
        ),
        "جهان",
    )

    return {
        "category": category,
        "title": title,
        "summary": str(article.get("description") or "").strip(),
        "link": url,
        "published_at": published_at,
        "image_url": str(article.get("image") or "").strip(),
        "video_url": "",
        "is_google": False,
        "resolved_link": url,
        "source_name": str(article.get("author") or "").strip(),
        "source_url": url,
        "article_text": "",
        "importance": 0,
        "cluster_size": 1,
        "currents_source": True,
    }


def collect():
    key = os.getenv("CURRENTS_API_KEY", "").strip()
    if not key:
        print("CURRENTS: API key not configured; source disabled.")
        return []

    if not _reserve_request():
        return []

    try:
        response = requests.get(
            API_URL,
            params={
                "language": "en",
                "page_size": PAGE_SIZE,
            },
            headers={"Authorization": f"Bearer {key}"},
            timeout=TIMEOUT,
        )

        if response.status_code == 429:
            print("CURRENTS: provider daily free quota reached; skipping.")
            return []

        if response.status_code in (401, 403):
            print("CURRENTS: API key rejected; skipping source.")
            return []

        response.raise_for_status()
        data = response.json()

        if data.get("status") != "ok":
            print(f"CURRENTS: unexpected response status={data.get('status')}")
            return []

        items = []
        for article in data.get("news", []):
            item = _candidate(article)
            if item:
                items.append(item)

        usage = _load_usage()
        print(
            f"CURRENTS OK: {len(items)} fresh candidates "
            f"| requests today: {usage['requests']}/{DAILY_REQUEST_BUDGET}"
        )
        return items

    except Exception as exc:
        print(f"CURRENTS ERROR: {exc}")
        return []
