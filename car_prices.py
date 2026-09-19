import os
import re
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHANNEL_ID = "@NabzKhabarOfficial"

SOURCE_URL = "https://1car.ir/price"
HISTORY_FILE = "car_price_history.json"
IRAN_TZ = ZoneInfo("Asia/Tehran")
REQUEST_TIMEOUT = 25
TELEGRAM_TIMEOUT = 30
MAX_MESSAGE = 3900

# Domestic + Iranian assembly brands. Imported-only brands are intentionally
# excluded from this dedicated consumer price board.
DOMESTIC_ASSEMBLY_BRANDS = {
    "آریسان", "اطلس", "پژو", "تارا", "دنا", "رانا", "سورن", "سمند", "ری را",
    "سهند", "ساینا", "شاهین", "کوییک", "پراید", "پارس نوآ", "زامیاد",
    "سایپا", "ایران خودرو", "پارس خودرو",
    "ام وی ام", "فونیکس", "اکستریم", "چری", "آریزو",
    "مدیران خودرو", "کرمان موتور", "کرمان خودرو", "جک", "کی ام سی",
    "بهمن", "بهمن خودرو", "فیدلیتی", "دیگنیتی", "ریسپکت", "مزدا", "کاپرا",
    "لاماری", "آرین", "آرین موتور", "فردا", "فردا موتور",
    "مکث موتور", "مکث", "شایان دیزل", "دیار خودرو", "رامک خودرو",
    "سوزوکی", "هایما", "چانگان", "سیتروئن", "اوشان", "اوتار",
    "بی وای دی", "بایک", "بی ای سی", "فونیکس",
}

PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
ENGLISH_DIGITS = "0123456789"


def normalize_digits(text):
    return str(text or "").translate(
        str.maketrans(PERSIAN_DIGITS + ARABIC_DIGITS, ENGLISH_DIGITS * 2)
    )


def to_persian_digits(text):
    return str(text or "").translate(
        str.maketrans(ENGLISH_DIGITS, PERSIAN_DIGITS)
    )


def clean(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def jalali_date(now):
    # Gregorian -> Jalali, deterministic and dependency-free.
    gy, gm, gd = now.year, now.month, now.day
    g_days = [31,28,31,30,31,30,31,31,30,31,30,31]
    j_days = [31,31,31,31,31,31,30,30,30,30,30,29]
    gy -= 1600
    gm -= 1
    gd -= 1
    gdn = 365 * gy + (gy + 3)//4 - (gy + 99)//100 + (gy + 399)//400
    for i in range(gm):
        gdn += g_days[i]
    if gm > 1 and ((gy + 1600) % 4 == 0 and ((gy + 1600) % 100 != 0 or (gy + 1600) % 400 == 0)):
        gdn += 1
    gdn += gd
    jdn = gdn - 79
    jnp = jdn // 12053
    jdn %= 12053
    jy = 979 + 33*jnp + 4*(jdn//1461)
    jdn %= 1461
    if jdn >= 366:
        jy += (jdn - 1)//365
        jdn = (jdn - 1)%365
    jm = 1
    while jm <= 11 and jdn >= j_days[jm-1]:
        jdn -= j_days[jm-1]
        jm += 1
    return jy, jm, jdn + 1


def jalali_text(now):
    y, m, d = jalali_date(now)
    return f"{y:04d}/{m:02d}/{d:02d}"


def format_price(value):
    value = clean(normalize_digits(value)).replace("٬", ",")
    if not value or value in {"—", "-", "ناموجود"}:
        return "—"
    # Keep ranges intact, while normalizing every numeric token.
    def repl(match):
        raw = match.group(0).replace(",", "").replace("٬", "")
        try:
            return f"{int(raw):,}"
        except Exception:
            return raw
    value = re.sub(r"\d[\d,٬]*", repl, value)
    return to_persian_digits(value)


def is_supported_brand(brand):
    b = clean(brand).replace("قیمت ", "")
    return any(
        b == x or b.startswith(x + " ") or x in b
        for x in DOMESTIC_ASSEMBLY_BRANDS
    )


def fetch_page():
    r = requests.get(
        SOURCE_URL,
        headers={"User-Agent": "Mozilla/5.0 (compatible; NabzKhabar/1.0)"},
        timeout=REQUEST_TIMEOUT,
    )
    r.raise_for_status()
    return r.text


def parse_update_date(soup):
    text = clean(soup.get_text(" ", strip=True))
    m = re.search(r"تاریخ بروزرسانی\s*:\s*[^\d۰-۹]*([۰-۹0-9]{1,4}\s+[^\d۰-۹]+\s+[۰-۹0-9]{1,2}\s+[^\d۰-۹]+\s+[۰-۹0-9]{2,4})", text)
    if not m:
        # Fallback to the first heading containing "تاریخ بروزرسانی".
        for node in soup.find_all(string=re.compile("تاریخ بروزرسانی")):
            line = clean(node.parent.get_text(" ", strip=True))
            mm = re.search(r"([۰-۹0-9]{4}\s+\S+\s+[۰-۹0-9]{1,2})", line)
            if mm:
                return clean(mm.group(1))
    return clean(m.group(1)) if m else ""


def normalize_date_text(value):
    value = clean(value)
    value = value.replace("شنبه","").replace("یکشنبه","").replace("دوشنبه","").replace("سه‌شنبه","").replace("چهارشنبه","").replace("پنجشنبه","").replace("جمعه","")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def parse_rows(html):
    soup = BeautifulSoup(html, "html.parser")
    sections = []
    current_brand = None

    # 1Car uses h3 brand headings followed by a table.
    for node in soup.find_all(["h3", "table"]):
        if node.name == "h3":
            title = clean(node.get_text(" ", strip=True))
            if title.startswith("قیمت "):
                current_brand = title.replace("قیمت ", "", 1).strip()
            continue

        if not current_brand or not is_supported_brand(current_brand):
            continue

        rows = node.find_all("tr")
        for tr in rows:
            cells = [clean(x.get_text(" ", strip=True)) for x in tr.find_all(["th", "td"])]
            if len(cells) < 4:
                continue
            header = " ".join(cells).lower()
            if "نام خودرو" in header:
                continue
            name, year, market, factory = cells[:4]
            if not name or not re.search(r"\d", normalize_digits(market)):
                continue
            sections.append({
                "brand": current_brand,
                "name": name,
                "year": year,
                "market": format_price(market),
                "factory": format_price(factory),
            })

    # Stable de-duplication.
    seen = set()
    out = []
    for row in sections:
        key = (row["brand"], row["name"], row["year"], row["market"], row["factory"])
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def load_history():
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_history(data):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def build_messages(rows, date_text, source_date):
    grouped = {}
    for row in rows:
        grouped.setdefault(row["brand"], []).append(row)

    blocks = []
    for brand, items in grouped.items():
        lines = [f"🚘 {brand}"]
        for item in items:
            year = f" | {to_persian_digits(item['year'])}" if item["year"] else ""
            lines.append(
                f"• {item['name']}{year}\n"
                f"  بازار: {item['market']} تومان\n"
                f"  کارخانه: {item['factory']} تومان"
            )
        blocks.append("\n".join(lines))

    header = (
        f"📰 قیمت روز خودرو | {to_persian_digits(date_text.replace('/', ' / '))}\n\n"
        "📊 قیمت بازار و کارخانه خودروهای داخلی و مونتاژی\n"
        "منبع داده: 1Car\n\n"
    )
    footer = "\n\n🔗 @NabzKhabarOfficial"

    messages = []
    current = header
    for block in blocks:
        candidate = current + block + footer
        if len(candidate) > MAX_MESSAGE and current != header:
            messages.append(current.rstrip() + footer)
            current = header + block + "\n"
        else:
            current = candidate.rstrip(footer) + "\n\n"
    if current.strip() != header.strip():
        messages.append(current.rstrip() + footer)

    # Number the parts only when split into multiple Telegram messages.
    if len(messages) > 1:
        total = len(messages)
        numbered = []
        for i, msg in enumerate(messages, 1):
            msg = msg.replace(
                header,
                header.replace("📰 قیمت روز خودرو", f"📰 قیمت روز خودرو | بخش {to_persian_digits(str(i))}/{to_persian_digits(str(total))}"),
                1,
            )
            numbered.append(msg)
        return numbered
    return messages


def send_message(text):
    r = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={
            "chat_id": CHANNEL_ID,
            "text": text,
            "disable_web_page_preview": True,
        },
        timeout=TELEGRAM_TIMEOUT,
    )
    r.raise_for_status()


def main(send_func=None):
    if not BOT_TOKEN and send_func is None:
        raise RuntimeError("BOT_TOKEN is missing")

    now = datetime.now(IRAN_TZ)
    today = jalali_text(now)
    history = load_history()

    # Exactly once per Jalali day. If source is stale or parsing fails, retry
    # automatically on the next 10-minute workflow run.
    if history.get("posted_date") == today:
        print(f"CAR PRICES: already posted for {today}")
        return False

    html = fetch_page()
    soup = BeautifulSoup(html, "html.parser")
    source_date = normalize_date_text(parse_update_date(soup))
    expected = normalize_date_text(
        f"{to_persian_digits(str(jalali_date(now)[0]))} "
        f"{['فروردین','اردیبهشت','خرداد','تیر','مرداد','شهریور','مهر','آبان','آذر','دی','بهمن','اسفند'][jalali_date(now)[1]-1]} "
        f"{to_persian_digits(str(jalali_date(now)[2]))}"
    )

    # Do not publish yesterday's/stale board as today's data.
    if source_date and normalize_date_text(source_date) != expected:
        print(f"CAR PRICES: source is stale | source={source_date} | expected={expected}")
        return False

    rows = parse_rows(html)
    if len(rows) < 10:
        raise RuntimeError(f"CAR PRICES: suspiciously small dataset ({len(rows)} rows)")

    messages = build_messages(rows, today, source_date)
    if not messages:
        raise RuntimeError("CAR PRICES: no publishable messages")

    sender = send_func or send_message
    for message in messages:
        sender(message)

    history = {
        "posted_date": today,
        "source_date": source_date,
        "rows": len(rows),
        "messages": len(messages),
        "source": SOURCE_URL,
    }
    save_history(history)
    print(f"CAR PRICES: published {len(rows)} rows in {len(messages)} Telegram messages")
    return True


if __name__ == "__main__":
    main()
