import json
import os
from datetime import datetime, timezone

CHANNEL = "@NabzKhabarOfficial"
LINK = "https://t.me/NabzKhabarOfficial"
CAMPAIGNS_FILE = "growth_campaigns.json"

DEFAULT_CAMPAIGNS = {
    "general": {"label": "معرفی عمومی", "link": LINK},
    "economy": {"label": "دلار و طلا", "link": LINK},
    "news": {"label": "اخبار فوری", "link": LINK},
    "sports": {"label": "ورزش", "link": LINK},
    "tech": {"label": "فناوری", "link": LINK},
}


def load():
    try:
        with open(CAMPAIGNS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"updated_at": None, "campaigns": DEFAULT_CAMPAIGNS, "results": {}}


def save(data):
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    with open(CAMPAIGNS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    data = load()
    data["campaigns"] = DEFAULT_CAMPAIGNS
    data.setdefault("results", {})
    save(data)
    print("Growth campaign system: READY")
    print("Channel:", CHANNEL)
    print("Campaigns:", ", ".join(DEFAULT_CAMPAIGNS))


if __name__ == "__main__":
    main()
