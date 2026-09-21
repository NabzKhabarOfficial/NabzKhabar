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
    return str(text or "").translate(str.maketrans(PERSIAN_DIGITS + "٠١٢٣٤٥٦٧٨٩", ENGLISH_DIGITS + ENGLISH_DIGITS))


def to_persian_digits(text):
    return str(text or "").translate(str.maketrans(ENGLISH_DIGITS, PERSIAN_DIGITS))


def clean_text(text):
    return re.sub(r"\s+", " ", normalize_digits(text)).strip()


def gregorian_to_jalali(gy, gm, gd):
    g_days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    j_days = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29]

    gy -= 1600
    gm -= 1
    gd -= 1

    g_day_no = 365 * gy + (gy + 3) // 4 - (gy + 99) // 100 + (gy + 399) // 400
    for i in range(gm):
        g_day_no += g_days[i]
    if gm > 1 and ((gy + 1600) % 4 == 0 and ((gy + 1600) % 100 != 0 or (gy + 1600) % 400 == 0)):
        g_day_no += 1
    g_day_no += gd

    j_day_no = g_day_no - 79
    j_np = j_day_no // 12053
    j_day_no %= 12053

    jy = 979 + 33 * j_np + 4 * (j_day_no // 1461)
    j_day_no %= 1461

    if j_day_no >= 366:
        jy += (j_day_no - 1) // 365
        j_day_no = (j_day_no - 1) % 365

    jm = 1
    while jm <= 11 and j_day_no >= j_days[jm - 1]:
        j_day_no -= j_days[jm - 1]
        jm += 1

    return jy, jm, j_day_no + 1


def jalali_date_text(now):
    jy, jm, jd = gregorian_to_jalali(now.year, now.month, now.day)
    return to_persian_digits(f"{jy:04d}/{jm:02d}/{jd:02d}")


def format_decimal(number):
    number = str(number).replace("٬", ",")
    if "." in number:
        integer, fraction = number.split(".", 1)
        return f"{to_persian_digits(integer)}٫{to_persian_digits(fraction)}"
    return to_persian_digits(number)


def format_market_value(value, unit="تومان"):
    value = clean_text(value)
    if not value:
        return ""
    compact = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*م\s*[\.:]?\s*([ند])", value)
    if compact:
        unit_name = "میلیون" if compact.group(2) == "ن" else "میلیارد"
        return f"{format_decimal(compact.group(1))} {unit_name} {unit}".strip()
    explicit = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*(میلیون|میلیارد)\s*(?:تومان)?", value)
    if explicit:
        return f"{format_decimal(explicit.group(1))} {explicit.group(2)} {unit}".strip()
    plain = value.replace(",", "").replace("٬", "").replace(" ", "")
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", plain):
        if "." in plain:
            integer, fraction = plain.split(".", 1)
            formatted = f"{int(integer):,}.{fraction}"
        else:
            formatted = f"{int(plain):,}"
        return f"{formatted} {unit}".strip()
    return f"{value} {unit}".strip()


def format_market_display(value, symbol):
    unit = "دلار" if symbol in {"XAU", "XAG"} else "تومان"
    return format_market_value(value, unit)


def format_change(value):
    value = clean_text(value)
    match = re.search(r"([▲▼])?\s*([+-]?[0-9]+(?:\.[0-9]+)?)\s*٪?", value)
    if not match:
        return ""
    arrow, number = match.group(1) or "", match.group(2)
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
        headers={"User-Agent": "Mozilla/5.0 (compatible; NabzKhabar/1.0; +https://t.me/NabzKhabarOfficial)"},
        timeout=25,
    )
    response.raise_for_status()
    return response.text


def extract_rows(html):
    soup = BeautifulSoup(html, "html.parser")
    rows = {}
    symbols = (
        "USDT|XAUT|XAU|XAG|BTC|ETH|XRP|LTC|EOS|PAXG|BNB|BCH|GOLD18|SILVER999|SILVER925|GOLD24|GOLD18M|"
        "SEKE|SEKEN|SEKER|SEKB|SEKEB86|SEKEB86N|SEKEB86R|SEKG|"
        "USD|EUR|AED|RUB|BHD|MYR|CHF|IQD|SGD|AUD|AFN|KWD|NOK|GBP|SAR|INR|QAR|HKD|AZN|"
        "THB|AMD|TRY|OMR|DKK|JPY|CAD|CNY|SEK"
    )
    for tr in soup.find_all("tr"):
        cells = [clean_text(cell.get_text(" ", strip=True)) for cell in tr.find_all(["th", "td"])]
        if len(cells) < 3:
            continue
        match = re.search(rf"\b({symbols})\b", " ".join(cells), re.I)
        if match:
            rows[match.group(1).upper()] = cells
    return rows


def value_for(rows, symbol):
    cells = rows.get(symbol.upper())
    return cells[2] if cells and len(cells) >= 3 else None


def change_for(rows, symbol):
    cells = rows.get(symbol.upper())
    return format_change(cells[3]) if cells and len(cells) >= 4 else ""


def send_telegram(text):
    response = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": CHANNEL_ID, "text": text, "disable_web_page_preview": True},
        timeout=20,
    )
    response.raise_for_status()


def market_line(rows, emoji, label, symbol):
    value = value_for(rows, symbol)
    if not value:
        return None
    change = change_for(rows, symbol)
    return f"{emoji} {label}: {format_market_display(value, symbol)}" + (f"  {change}" if change else "")


def section(rows, title, items):
    lines = [f"▌ {title}", "└────────────────────"]
    for item in items:
        line = market_line(rows, *item)
        if line:
            lines.append(line)
    return lines


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing")

    rows = extract_rows(fetch_prices())
    now = datetime.now(IRAN_TIMEZONE)
    time_text = to_persian_digits(now.strftime("%H:%M"))
    date_text = jalali_date_text(now)

    lines = [
        "#قیمت لحظه ای #طلا ، #دلار و #ارز📝",
        "",
        f"⏰ {to_persian_digits(now.day)} {['ژانویه','فوریه','مارس','آوریل','مه','ژوئن','ژوئیه','اوت','سپتامبر','اکتبر','نوامبر','دسامبر'][now.month-1]} ماه {to_persian_digits(now.year)} - ساعت {time_text}",
        "",
        "ᨒᨒᨒᨒᨒᨒᨒᨒᨒᨒᨒᨒᨒᨒ",
        "",
    ]

    for emoji, label, symbol in [
        ("🇺🇸", "دلار آمریکا", "USD"), ("🇪🇺", "یورو", "EUR"),
        ("🇬🇧", "پوند انگلیس", "GBP"), ("🇹🇷", "لیر ترکیه", "TRY"),
        ("🇦🇺", "دلار استرالیا", "AUD"), ("🇸🇬", "دلار سنگاپور", "SGD"),
        ("🇨🇦", "دلار کانادا", "CAD"), ("🇦🇪", "درهم امارات", "AED"),
        ("🇮🇶", "۱۰۰ دینار عراق", "IQD"), ("🇶🇦", "ریال قطر", "QAR"),
        ("🇦🇫", "افغانی", "AFN"), ("🇨🇳", "یوان چین", "CNY"),
        ("💵", "تتر", "USDT"),
    ]:
        line = market_line(rows, emoji, label, symbol)
        if line:
            lines.append(line)

    lines += ["", "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬", ""]
    for emoji, label, symbol in [
        ("🟡", "طلا ۱۸ عیار", "GOLD18"), ("🟠", "طلا ۲۴ عیار", "GOLD24"),
        ("🟡", "گرم طلا دست۲", "GOLD18M"), ("🟡", "اونس طلا", "XAU"),
        ("🪙", "اونس نقره", "XAG"), ("🪙", "نقره عیار ۹۹۹", "SILVER999"),
        ("🪙", "نقره ۹۲۵", "SILVER925"),
    ]:
        line = market_line(rows, emoji, label, symbol)
        if line:
            lines.append(line)

    lines += ["", "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬", ""]
    for emoji, label, symbol in [
        ("🌕", "سکه امامی", "SEKE"), ("🌕", "سکه بهار", "SEKB"),
        ("🌕", "نیم سکه", "SEKEN"), ("🌕", "ربع سکه", "SEKER"),
        ("🌕", "سکه گرمی", "SEKG"),
    ]:
        line = market_line(rows, emoji, label, symbol)
        if line:
            lines.append(line)

    lines += ["", "@NabzKhabarOfficial", ""]
    send_telegram("\n".join(lines))
    print("NABZ MARKET BOARD sent successfully.")


if __name__ == "__main__":
    main()
