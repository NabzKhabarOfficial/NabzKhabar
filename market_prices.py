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
    table = str.maketrans(
        PERSIAN_DIGITS + "٠١٢٣٤٥٦٧٨٩",
        ENGLISH_DIGITS + ENGLISH_DIGITS,
    )
    return str(text).translate(table)


def to_persian_digits(text):
    if text is None:
        return ""
    return str(text).translate(str.maketrans(ENGLISH_DIGITS, PERSIAN_DIGITS))


def clean_text(text):
    text = normalize_digits(text or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def format_decimal(number):
    number = str(number).replace("٬", ",")
    if "." in number:
        integer, fraction = number.split(".", 1)
        return f"{to_persian_digits(integer)}٫{to_persian_digits(fraction)}"
    return to_persian_digits(number)


def format_market_value(value):
    """Convert source compact units to clear Persian تومان values."""
    value = clean_text(value)
    if not value:
        return ""

    compact = re.fullmatch(
        r"([0-9]+(?:\.[0-9]+)?)\s*م\s*[\.:]?\s*([ند])",
        value,
    )
    if compact:
        number = format_decimal(compact.group(1))
        unit = compact.group(2)
        label = "میلیون" if unit == "ن" else "میلیارد"
        return f"{number} {label} تومان"

    explicit = re.fullmatch(
        r"([0-9]+(?:\.[0-9]+)?)\s*(میلیون|میلیارد)\s*(?:تومان)?",
        value,
    )
    if explicit:
        return f"{format_decimal(explicit.group(1))} {explicit.group(2)} تومان"

    plain = value.replace(",", "").replace("٬", "").replace(" ", "")
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", plain):
        if "." in plain:
            integer, fraction = plain.split(".", 1)
            formatted = f"{int(integer):,}.{fraction}"
        else:
            formatted = f"{int(plain):,}"
        return f"{to_persian_digits(formatted.replace(',', '٬').replace('.', '٫'))} تومان"

    return f"{to_persian_digits(value)} تومان"


def format_change(value):
    """Return a compact Persian market-change indicator from the source change cell."""
    value = clean_text(value)
    if not value:
        return ""

    match = re.search(r"([▲▼])?\s*([+-]?[0-9]+(?:\.[0-9]+)?)\s*٪?", value)
    if not match:
        return ""

    arrow = match.group(1) or ""
    number = match.group(2)
    try:
        numeric = float(number)
    except ValueError:
        return ""

    if numeric == 0:
        return "⚪ ۰٪"

    if arrow == "▲" or numeric > 0:
        return f"🟢 +{format_decimal(number)}٪"

    return f"🔴 −{format_decimal(number.lstrip('-'))}٪"


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
    symbols = (
        "USDT|XAUT|BTC|ETH|XRP|LTC|EOS|PAXG|BNB|BCH|"
        "GOLD18|SILVER999|GOLD24|GOLD18M|"
        "SEKE|SEKEN|SEKER|SEKB|SEKEB86|SEKEB86N|SEKEB86R|SEKG|"
        "USD|EUR|AED|RUB|BHD|MYR|CHF|IQD|SGD|AUD|AFN|KWD|NOK|"
        "GBP|SAR|INR|QAR|HKD|AZN|THB|AMD|TRY|OMR|DKK|JPY|CAD|CNY|SEK"
    )

    for tr in soup.find_all("tr"):
        cells = [
            clean_text(cell.get_text(" ", strip=True))
            for cell in tr.find_all(["th", "td"])
        ]
        if len(cells) < 3:
            continue

        joined = " ".join(cells)
        match = re.search(rf"\b({symbols})\b", joined, re.I)
        if not match:
            continue

        rows[match.group(1).upper()] = cells

    return rows


def value_for(rows, symbol):
    cells = rows.get(symbol.upper())
    if not cells or len(cells) < 3:
        return None
    return cells[2]


def change_for(rows, symbol):
    cells = rows.get(symbol.upper())
    if not cells or len(cells) < 4:
        return ""
    return format_change(cells[3])


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
        ("🇬🇧", "پوند انگلیس", "GBP"),
        ("🇦🇪", "درهم", "AED"),
        ("🥇", "طلای ۱۸ عیار", "GOLD18"),
        ("✨", "طلای ۲۴ عیار", "GOLD24"),
        ("⚪", "نقره ۹۹۹", "SILVER999"),
        ("🪙", "سکه امامی", "SEKE"),
        ("🔸", "نیم‌سکه", "SEKEN"),
        ("🔹", "ربع‌سکه", "SEKER"),
        ("💲", "تتر", "USDT"),
        ("₿", "بیت‌کوین", "BTC"),
        ("Ξ", "اتریوم", "ETH"),
    ]

    lines = [
        "📊 نرخ لحظه‌ای ارز، طلا و رمزارز",
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    found = 0
    for emoji, label, symbol in wanted:
        value = value_for(rows, symbol)
        if not value:
            continue

        change = change_for(rows, symbol)
        suffix = f"  {change}" if change else ""
        lines.append(f"{emoji} {label}: {format_market_value(value)}{suffix}")
        found += 1

    if found == 0:
        raise RuntimeError("No supported market prices were found on Gheymat Online")

    now = datetime.now(IRAN_TIMEZONE).strftime("%H:%M")
    now = to_persian_digits(now)
    lines += ["", f"🕐 بروزرسانی: {now} به وقت ایران", "#نبض_خبر"]

    send_telegram("\n".join(lines))
    print(f"Market price post sent successfully ({found} assets).")


if __name__ == "__main__":
    main()
