import json
import os
from datetime import datetime, timezone

import requests

CHANNEL = "@NabzKhabarOfficial"
LINK = "https://t.me/NabzKhabarOfficial"
CAMPAIGNS_FILE = "growth_campaigns.json"

DEFAULT_CAMPAIGNS = {
    "general": {"label": "معرفی عمومی", "slug": "general"},
    "economy": {"label": "دلار و طلا", "slug": "economy"},
    "news": {"label": "اخبار فوری", "slug": "news"},
    "sports": {"label": "ورزش", "slug": "sports"},
    "tech": {"label": "فناوری", "slug": "tech"},
}

API = "https://api.telegram.org/bot{}"


def load():
    try:
        with open(CAMPAIGNS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"updated_at": None, "channel": CHANNEL, "campaigns": {}}


def save(data):
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    with open(CAMPAIGNS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def telegram(token, method, payload=None):
    response = requests.post(
        f"{API.format(token)}/{method}",
        json=payload or {},
        timeout=25,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("description", f"Telegram API error: {method}"))
    return data["result"]


def get_or_create_link(token, campaign):
    existing = campaign.get("invite_link")
    if existing:
        return existing

    result = telegram(token, "createChatInviteLink", {
        "chat_id": CHANNEL,
        "name": f"Nabz {campaign['slug']}",
        "creates_join_request": False,
    })
    return result["invite_link"]


def main():
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is missing")

    data = load()
    data["channel"] = CHANNEL
    data.setdefault("campaigns", {})

    for key, spec in DEFAULT_CAMPAIGNS.items():
        campaign = data["campaigns"].setdefault(key, {
            "label": spec["label"],
            "slug": spec["slug"],
        })
        campaign["label"] = spec["label"]
        campaign["slug"] = spec["slug"]
        campaign["link"] = LINK
        campaign["invite_link"] = get_or_create_link(token, campaign)

    try:
        data["member_count"] = telegram(token, "getChatMemberCount", {"chat_id": CHANNEL})
    except Exception as exc:
        data["member_count_error"] = str(exc)

    data["automation"] = {
        "invite_links": True,
        "member_count": True,
        "external_group_spam": False,
        "fake_members": False,
        "paid_services": False,
    }
    save(data)

    print("Growth campaign system: ACTIVE")
    print("Channel:", CHANNEL)
    print("Members:", data.get("member_count", "unknown"))
    for key, campaign in data["campaigns"].items():
        print(f"{key}: {campaign['invite_link']}")


if __name__ == "__main__":
    main()
