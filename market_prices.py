import re
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHANNEL_ID = "@NabzKhabarOfficial"
PRICES_URL = "https://gheymat.online/prices"


PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
ENGLISH_DIGITS = "0123456789"
IRAN_TIMEZONE = ZoneInfo("Asia/Tehran")


def normalize_digits(text):
    if not text:
        return ""
    table = str.maketrans(PERSIAN_DIGITS + "٠١٢٣٤٥٦٧٨٩", ENGLISH_DIGITS + ENGLISH_DIGITS)
    return str(text).translate(table)


def to_persian_digits(text):
    if text is None:
        return ""
    return str(text).translate(str.maketrans(ENGLISH_DIGITS, PERSIAN_DIGITS))


def clean_text(text):
    text = normalize_digits(text or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def format_market_value(value):
    value = clean_text(value)
    if not value:
        return ""

    compact = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*م\s*[\.:]?\s*([ند])", value)
    if compact:
        number = compact.group(1)
        unit = compact.group(2)
        label = "میلیون" if unit == "ن" else "میلیارد"
        return f"{to_persian_digits(number)} {label} تومان"

    explicit = re.fullmatch(
        r"([0-9]+(?:\.[0-9]+)?)\s*(میلیون|میلیارد)\s*(?:تومان)?",
        value,
    )
    if explicit:
        return f"{to_persian_digits(explicit.group(1))} {explicit.group(2)} تومان"

    plain = value.replace(",", "").replace("٬", "").replace(" ", "")
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", plain):
        if "." in plain:
            integer, fraction = plain.split(".", 1)
            formatted = f"{int(integer):,}.{fraction}"
        else:
            formatted = f"{int(plain):,}"
        return f"{to_persian_digits(formatted.replace(',', '٬'))} تومان"

    return f"{to_persian_digits(value)} تومان"


def fetch_prices():
    response = requests.get(
        PRICES_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; NabzKhabar/1.0; +https://t.me/NabzKhabarOfficial)"
        },
        timeout=25,
    )
    response.raise_for_status()
    return response.text


def extract_rows(html):
    soup = BeautifulSoup(html, "html.parser")
    rows = {}

    for tr in soup.find_all("tr"):
        cells = [clean_text(cell.get_text(" ", strip=True)) for cell in tr.find_all(["th", "td"])]
        if len(cells) < 3:
            continue

        joined = " ".join(cells)
        match = re.search(r"\b(USDT|GOLD18|SEKE|USD|EUR|AED|BTC|ETH)\b", joined, re.I)
        if not match:
            continue

        symbol = match.group(1).upper()
        rows[symbol] = cells

    return rows


def value_for(rows, symbol):
    cells = rows.get(symbol.upper())
    if not cells or len(cells) < 3:
        return None
    return cells[2]


def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    response = requests.post(
        url,
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

    html = fetch_prices()
    rows = extract_rows(html)

    wanted = [
        ("💵", "دلار آمریکا", "USD"),
        ("💶", "یورو", "EUR"),
        ("🇦🇪", "درهم", "AED"),
        ("🥇", "طلای ۱۸ عیار", "GOLD18"),
        ("🪙", "سکه امامی", "SEKE"),
        ("💲", "تتر", "USDT"),
        ("₿", "بیت‌کوین", "BTC"),
    ]

    lines = [
        "📊 نرخ لحظه‌ای ارز، طلا و رمزارز",
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    found = 0
    for emoji, label, symbol in wanted:
        value = value_for(rows, symbol)
        if value:
            lines.append(f"{emoji} {label}: {format_market_value(value)}")
            found += 1

    if found == 0:
        raise RuntimeError("No supported market prices were found on Gheymat Online")

    # Iran uses Asia/Tehran (UTC+3:30) all year; show the post time in Iran local time.
    now = datetime.now(IRAN_TIMEZONE).strftime("%H:%M")
    now = to_persian_digits(now)
    lines += ["", f"🕐 بروزرسانی: {now} به وقت ایران", "#نبض_خبر"]

    send_telegram("\n".join(lines))
    print(f"Market price post sent successfully ({found} assets).")


if __name__ == "__main__":
    main()
