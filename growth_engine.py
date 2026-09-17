import os
import re
import json
import time
from datetime import datetime, timezone

import requests

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHANNEL_ID = "@NabzKhabarOfficial"
STATS_FILE = "growth_stats.json"

API = f"https://api.telegram.org/bot{BOT_TOKEN}"


def load_stats():
    try:
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "runs": 0,
            "checked_posts": 0,
            "posts": {},
            "updated_at": None,
        }


def save_stats(data):
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def telegram(method, payload):
    r = requests.post(f"{API}/{method}", json=payload, timeout=20)
    r.raise_for_status()
    return r.json()


def get_recent_channel_posts(limit=100):
    """Best-effort public-channel discovery using Telegram search API is not available.
    This engine therefore records only data supplied by the bot itself and remains
    deliberately passive: it never joins groups, invites users, or sends spam.
    """
    return []


def score_topic(text):
    text = (text or "").lower()
    hot = [
        "فوری", "زلزله", "انفجار", "حمله", "جنگ", "موشک", "دلار",
        "طلا", "سکه", "فوتبال", "آرسنال", "پرسپولیس", "استقلال",
        "هوش مصنوعی", "iphone", "آیفون", "خودرو", "تصادف", "ویدئو", "فیلم"
    ]
    return sum(1 for x in hot if x in text)


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing")

    stats = load_stats()
    stats["runs"] = int(stats.get("runs", 0)) + 1

    # Passive growth intelligence only. It does not alter the news publisher,
    # duplicate engine, formatting, or Telegram audience.
    stats["growth_policy"] = {
        "priority_topics": ["breaking", "video", "markets", "sports", "technology"],
        "spam": False,
        "fake_members": False,
        "paid_services": False,
    }
    save_stats(stats)
    print("Growth engine: OK - passive analytics enabled")


if __name__ == "__main__":
    main()
