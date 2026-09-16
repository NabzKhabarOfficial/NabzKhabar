import os
from datetime import datetime, timezone

import requests

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHANNEL_ID = "@NabzKhabarOfficial"
API_TOKEN = os.getenv("ALANCHAND_API_TOKEN", "").strip()
API_URL = "https://api.alanchand.com"


def first_value(obj, keys):
    if isinstance(obj, dict):
        for key in keys:
            if key in obj and obj[key] not in (None, ""):
                return obj[key]
        for value in obj.values():
            found = first_value(value, keys)
            if found not in (None, ""):
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = first_value(item, keys)
            if found not in (None, ""):
                return found
    return None


def fmt(value):
    if value is None:
        return "-"
    try:
        number = float(value)
        if number.is_integer():
            return f"{int(number):,}"
        return f"{number:,.2f}"
    except Exception:
        return str(value)


def fetch_prices(kind, symbols):
    response = requests.get(
        API_URL,
        params={"type": kind, "symbols": ",".join(symbols)},
        headers={"Authorization": f"Bearer {API_TOKEN}"},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def extract_symbol(data, symbol):
    if isinstance(data, dict):
        for key, value in data.items():
            if str(key).lower() == symbol.lower():
                return value
        for value in data.values():
            found = extract_symbol(value, symbol)
            if found is not None:
                return found
    elif isinstance(data, list):
        for item in data:
            found = extract_symbol(item, symbol)
            if found is not None:
                return found
    return None


def value_for(data, symbol):
    item = extract_symbol(data, symbol)
    if isinstance(item, dict):
        return first_value(item, ["sell", "sell_price", "price", "value", "rate", "close"])
    return item


def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    response = requests.post(
        url,
        json={"chat_id": CHANNEL_ID, "text": text},
        timeout=20,
    )
    response.raise_for_status()


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing")
    if not API_TOKEN:
        print("ALANCHAND_API_TOKEN is not configured; skipping AlanChand price post.")
        return

    # AlanChand's free test access is limited to one API request per hour.
    # Rotate categories so this workflow stays within that free limit.
    hour = datetime.now(timezone.utc).hour
    mode = hour % 3

    if mode == 0:
        kind = "currency"
        symbols = ["usd", "eur", "gbp", "aed", "try"]
        labels = [("💵", "دلار"), ("💶", "یورو"), ("💷", "پوند"), ("🇦🇪", "درهم"), ("🇹🇷", "لیر")]
        title = "📊 نرخ ارز"
    elif mode == 1:
        kind = "gold"
        symbols = ["sekkeh", "gold18", "mesghal", "ounce"]
        labels = [("🪙", "سکه"), ("🥇", "طلای ۱۸ عیار"), ("🟡", "مثقال طلا"), ("🌍", "اونس طلا")]
        title = "📊 نرخ طلا و سکه"
    else:
        kind = "crypto"
        symbols = ["btc", "eth", "usdt"]
        labels = [("₿", "بیت‌کوین"), ("Ξ", "اتریوم"), ("💲", "تتر")]
        title = "📊 نرخ رمزارز"

    data = fetch_prices(kind, symbols)
    lines = [title, "━━━━━━━━━━━━━━━━━━━━"]

    for (emoji, label), symbol in zip(labels, symbols):
        value = value_for(data, symbol)
        lines.append(f"{emoji} {label}: {fmt(value)}")

    lines += ["", "#نبض_خبر"]
    send_telegram("\n".join(lines))
    print(f"AlanChand {kind} price post sent successfully.")


if __name__ == "__main__":
    main()
