import json
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHANNEL_ID = "@NabzKhabarOfficial"
SOURCE_URL = "https://1car.ir/price"
STATE_FILE = "car_prices_history.json"
IRAN_TIMEZONE = ZoneInfo("Asia/Tehran")

# A compact daily board: popular Iranian/assembled models, rather than hundreds
# of rows. The source page itself covers hundreds of models.
TARGET_MODELS = [
    ("پژو ۲۰۷", ("پژو 207",)),
    ("دنا پلاس", ("دنا پلاس",)),
    ("تارا اتوماتیک", ("تارا اتوماتیک",)),
    ("ری‌را", ("ری را",)),
    ("سمند سورن", ("سمند سورن",)),
    ("شاهین", ("شاهین",)),
    ("ساینا S", ("ساینا S",)),
    ("اطلس", ("اطلس دنده ای", "اطلس")),
    ("پراید ۱۵۱", ("پراید 151",)),
    ("آریسان ۲", ("آریسان 2",)),
    ("ام‌وی‌ام X33 کراس", ("ام وی ام X33 کراس",)),
    ("ام‌وی‌ام X55 PRO", ("ام وی ام X55 PRO",)),
    ("اکستریم LX", ("اکستریم LX",)),
    ("ریسپکت پرایم", ("ریسپکت پرایم",)),
    ("بایک BJ30", ("بایک BJ30",)),
]

def normalize(text):
    text = str(text or "").replace("ي", "ی").replace("ك", "ک")
    text = text.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "۰۱۲۳۴۵۶۷۸۹"))
    return re.sub(r"\s+", " ", text).strip()

def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, TypeError):
        return {}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def fetch_source():
    response = requests.get(
        SOURCE_URL,
        headers={"User-Agent": "Mozilla/5.0 (compatible; NabzKhabar/1.0)"},
        timeout=25,
    )
    response.raise_for_status()
    return response.text

def extract_update_date(soup):
    text = normalize(soup.get_text(" ", strip=True))
    match = re.search(r"تاریخ بروزرسانی\s*:\s*([^|]{3,40})", text)
    return match.group(1).strip() if match else ""

def parse_price(text):
    text = normalize(text)
    if not text or text == "—":
        return None
    return text

def extract_models(html):
    soup = BeautifulSoup(html, "html.parser")
    found = {}

    for tr in soup.find_all("tr"):
        cells = [normalize(c.get_text(" ", strip=True)) for c in tr.find_all(["th", "td"])]
        if len(cells) < 4:
            continue

        # Expected: model, year, market, factory, dealer, daily change
        model, year = cells[0], cells[1]
        market = parse_price(cells[2])
        factory = parse_price(cells[3])
        change = parse_price(cells[5]) if len(cells) >= 6 else None

        if not model or not year:
            continue

        found[model] = {
            "model": model,
            "year": year,
            "market": market,
            "factory": factory,
            "change": change,
        }

    return found

def choose_model(found, aliases):
    # Prefer newer model-year rows when several variants exist.
    matches = [
        item for model, item in found.items()
        if any(alias.lower() in model.lower() for alias in aliases)
        and item.get("market")
    ]
    if not matches:
        return None

    def year_key(item):
        nums = re.findall(r"\d+", item.get("year", ""))
        return int(nums[-1]) if nums else 0

    return sorted(matches, key=year_key, reverse=True)[0]

def format_line(label, item):
    market = item["market"]
    factory = item.get("factory")
    change = item.get("change")

    parts = [f"🚗 {label}: {market} تومان"]
    if factory:
        parts.append(f"🏭 کارخانه: {factory} تومان")
    if change and change != "—":
        parts.append(f"📊 تغییر: {change}")
    return "\n".join(parts)

def send_telegram(text):
    response = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={
            "chat_id": CHANNEL_ID,
            "text": text,
            "disable_web_page_preview": True,
        },
        timeout=20,
    )
    response.raise_for_status()

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing")

    now = datetime.now(IRAN_TIMEZONE)
    today = now.strftime("%Y-%m-%d")
    state = load_state()

    # The workflow runs every 10 minutes; this module is intentionally once/day.
    if state.get("last_published_date") == today:
        print(f"CAR PRICES: already published today ({today}).")
        return

    html = fetch_source()
    soup = BeautifulSoup(html, "html.parser")
    update_date = extract_update_date(soup)
    found = extract_models(html)

    lines = [
        "╔══════════════════════╗",
        "║   🚗 قیمت روز خودرو  ║",
        "║      NABZ AUTO       ║",
        "╚══════════════════════╝",
        f"📅 بروزرسانی منبع: {update_date or 'امروز'}",
        "",
    ]

    count = 0
    for label, aliases in TARGET_MODELS:
        item = choose_model(found, aliases)
        if item:
            lines.append(format_line(label, item))
            lines.append("────────────")
            count += 1

    if count == 0:
        raise RuntimeError("No supported car prices were found")

    lines += [
        "",
        "ℹ️ منبع قیمت: وان‌کار",
        "📌 قیمت بازار و کارخانه در صورت وجود داده نمایش داده می‌شود.",
        "",
        "@NabzKhabarOfficial",
    ]

    send_telegram("\n".join(lines))
    state["last_published_date"] = today
    state["source_update_date"] = update_date
    state["published_at"] = now.isoformat()
    state["models_count"] = count
    save_state(state)
    print(f"CAR PRICES: published {count} models for {today}.")

if __name__ == "__main__":
    main()
