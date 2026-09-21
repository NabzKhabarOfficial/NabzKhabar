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

TARGET_MODELS = [
    ("پژو ۲۰۷", ("پژو 207",)),
    ("دنا پلاس", ("دنا پلاس",)),
    ("تارا اتوماتیک", ("تارا اتوماتیک",)),
    ("تارا دستی", ("تارا دستی",)),
    ("ری‌را", ("ری را",)),
    ("سمند سورن", ("سمند سورن",)),
    ("شاهین", ("شاهین",)),
    ("شاهین اتوماتیک", ("شاهین اتوماتیک",)),
    ("ساینا S", ("ساینا S",)),
    ("ساینا", ("ساینا",)),
    ("اطلس", ("اطلس دنده ای", "اطلس")),
    ("کوییک", ("کوییک",)),
    ("کوییک R", ("کوییک R",)),
    ("پراید ۱۵۱", ("پراید 151",)),
    ("آریسان ۲", ("آریسان 2",)),
    ("وانت آریسان", ("آریسان",)),
    ("ام‌وی‌ام X33 کراس", ("ام وی ام X33 کراس",)),
    ("ام‌وی‌ام X55 PRO", ("ام وی ام X55 PRO",)),
    ("ام‌وی‌ام X22 PRO", ("ام وی ام X22 PRO",)),
    ("اکستریم LX", ("اکستریم LX",)),
    ("اکستریم TXL", ("اکستریم TXL",)),
    ("اکستریم VX", ("اکستریم VX",)),
    ("فونیکس FX", ("فونیکس FX",)),
    ("فونیکس تیگو ۷ پرو", ("تیگو 7 پرو",)),
    ("فونیکس تیگو ۸ پرو", ("تیگو 8 پرو",)),
    ("آریزو ۵", ("آریزو 5",)),
    ("آریزو ۶", ("آریزو 6",)),
    ("رسپکت پرایم", ("ریسپکت پرایم", "رسپکت پرایم")),
    ("بایک BJ30", ("بایک BJ30",)),
    ("لاماری ایما", ("لاماری ایما",)),
    ("فیدلیتی پرایم", ("فیدلیتی پرایم",)),
    ("دیگنیتی پرایم", ("دیگنیتی پرایم",)),
    ("KMC J7", ("KMC J7",)),
    ("KMC T8", ("KMC T8",)),
    ("KMC X5", ("KMC X5",)),
    ("هایما S5", ("هایما S5",)),
    ("هایما S7", ("هایما S7",)),
    ("هایما 8S", ("هایما 8S",)),
    ("چانگان CS35", ("چانگان CS35",)),
    ("چانگان CS55", ("چانگان CS55",)),
]

JALALI_MONTHS = (
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
)
PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


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
    match = re.search(r"تاریخ بروزرسانی\s*:\s*([^|]{3,60})", text)
    return match.group(1).strip() if match else ""


def jalali_today(dt):
    # Gregorian -> Jalali conversion, with no extra dependency.
    gy, gm, gd = dt.year, dt.month, dt.day
    g_days = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        355666
        + 365 * gy
        + (gy2 + 3) // 4
        - (gy2 + 99) // 100
        + (gy2 + 399) // 400
        + gd
        + g_days[gm - 1]
    )
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + days % 31
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + (days - 186) % 30
    return jy, jm, jd


def source_date_matches_today(update_date, now):
    if not update_date:
        return False

    normalized = normalize(update_date).translate(PERSIAN_DIGITS).translate(ARABIC_DIGITS)
    match = re.search(r"(\d{1,2})\s+(فروردین|اردیبهشت|خرداد|تیر|مرداد|شهریور|مهر|آبان|آذر|دی|بهمن|اسفند)\s+(\d{4})", normalized)
    if not match:
        return False

    day = int(match.group(1))
    month = JALALI_MONTHS.index(match.group(2)) + 1
    year = int(match.group(3))
    today_year, today_month, today_day = jalali_today(now)
    return (year, month, day) == (today_year, today_month, today_day)


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


def format_price_block(label, item):
    market = item["market"]
    factory = item.get("factory")
    change = item.get("change")

    lines = [
        f"🚗 **{label}**",
        f"💰 بازار: {market} تومان",
    ]
    if factory:
        lines.append(f"🏭 کارخانه: {factory} تومان")
    else:
        lines.append("🏭 کارخانه: —")

    if change and change != "—":
        lines.append(f"📊 تغییر: {change}")

    return "\n".join(lines)


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

    if state.get("last_published_date") == today:
        print(f"CAR PRICES: already published today ({today}).")
        return

    html = fetch_source()
    soup = BeautifulSoup(html, "html.parser")
    update_date = extract_update_date(soup)

    # Never publish yesterday's/stale prices as today's board.
    if not source_date_matches_today(update_date, now):
        print(
            f"CAR PRICES: source is not updated today. "
            f"source={update_date or 'unknown'}"
        )
        return

    found = extract_models(html)

    lines = [
        "🚗 قیمت روز خودرو | NABZ AUTO",
        f"📅 بروزرسانی: {update_date}",
        "",
    ]

    count = 0
    for label, aliases in TARGET_MODELS:
        item = choose_model(found, aliases)
        if item:
            if count:
                lines.append("──────────────")
            lines.append(format_price_block(label, item))
            count += 1

    if count == 0:
        raise RuntimeError("No supported car prices were found")

    lines += [
        "",
        "🔗 @NabzKhabarOfficial",
    ]

    # Keep the mobile layout compact and readable while allowing a larger list.
    text = "\n".join(lines)
    if len(text) > 3900:
        text = "\n".join(text.splitlines()[:1] + text.splitlines()[1:])

    send_telegram(text)
    state["last_published_date"] = today
    state["source_update_date"] = update_date
    state["published_at"] = now.isoformat()
    state["models_count"] = count
    save_state(state)
    print(f"CAR PRICES: published {count} models for {today}.")


if __name__ == "__main__":
    main()
