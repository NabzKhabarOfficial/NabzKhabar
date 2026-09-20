import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

API_URL = "https://api.open-meteo.com/v1/forecast"
HISTORY_FILE = Path("weather_history.json")
TIMEZONE = "Asia/Tehran"

# Major Iranian cities. The list is intentionally small so the daily board stays
# readable while one batched API request covers all locations.
CITIES = [
    ("تهران", 35.6892, 51.3890),
    ("مشهد", 36.2605, 59.6168),
    ("اصفهان", 32.6546, 51.6680),
    ("شیراز", 29.5918, 52.5837),
    ("تبریز", 38.0962, 46.2738),
    ("اهواز", 31.3183, 48.6706),
    ("رشت", 37.2808, 49.5832),
    ("کرمانشاه", 34.3142, 47.0650),
    ("کرمان", 30.2839, 57.0834),
    ("بندرعباس", 27.1832, 56.2666),
]

WEATHER_CODES = {
    0: "صاف",
    1: "عمدتاً صاف",
    2: "نیمه‌ابری",
    3: "ابری",
    45: "مه‌آلود",
    48: "مه یخ‌زن",
    51: "نم‌نم باران",
    53: "نم‌نم باران",
    55: "نم‌نم باران",
    56: "نم‌نم باران یخ‌زن",
    57: "نم‌نم باران یخ‌زن",
    61: "بارانی",
    63: "بارانی",
    65: "باران شدید",
    66: "باران یخ‌زن",
    67: "باران یخ‌زن شدید",
    71: "برف",
    73: "برف",
    75: "برف شدید",
    77: "دانه‌های برف",
    80: "رگبار",
    81: "رگبار",
    82: "رگبار شدید",
    85: "رگبار برف",
    86: "رگبار برف شدید",
    95: "رعدوبرق",
    96: "رعدوبرق و تگرگ",
    99: "رعدوبرق و تگرگ شدید",
}


def _load_history():
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_history(data):
    HISTORY_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _jalali_date(dt):
    # Keep the board date aligned with the same Persian-calendar convention
    # used by the other daily independent publishers.
    try:
        from khayyam import JalaliDate
        return str(JalaliDate(dt.date()))
    except Exception:
        return dt.strftime("%Y-%m-%d")


def _weather_text(code):
    return WEATHER_CODES.get(int(code), "نامشخص")


def _fetch_weather():
    params = {
        "latitude": ",".join(str(lat) for _, lat, _ in CITIES),
        "longitude": ",".join(str(lon) for _, _, lon in CITIES),
        "current": "temperature_2m,weather_code,wind_speed_10m",
        "daily": (
            "weather_code,temperature_2m_max,temperature_2m_min,"
            "precipitation_probability_max,precipitation_sum"
        ),
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
        "timezone": TIMEZONE,
        "forecast_days": 1,
    }
    response = requests.get(API_URL, params=params, timeout=25)
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, list) else [data]


def _format_board(data, jalali_date):
    lines = [
        "🌤️ **هواشناسی امروز ایران**",
        f"📅 {jalali_date}",
        "",
    ]

    for idx, (city, _, _) in enumerate(CITIES):
        item = data[idx]
        current = item.get("current") or {}
        daily = item.get("daily") or {}

        code = current.get("weather_code")
        temp = current.get("temperature_2m")
        wind = current.get("wind_speed_10m")

        tmax = (daily.get("temperature_2m_max") or [None])[0]
        tmin = (daily.get("temperature_2m_min") or [None])[0]
        rain_prob = (daily.get("precipitation_probability_max") or [None])[0]

        def fmt_temp(value):
            return "—" if value is None else f"{float(value):.0f}°"

        rain = "—" if rain_prob is None else f"{int(round(float(rain_prob)))}٪"
        wind_text = "—" if wind is None else f"{float(wind):.0f} km/h"

        lines.extend(
            [
                f"📍 **{city}**",
                f"   🌡️ اکنون: {fmt_temp(temp)} | {_weather_text(code or 0)}",
                f"   🔺 بیشینه: {fmt_temp(tmax)} | 🔻 کمینه: {fmt_temp(tmin)}",
                f"   🌧️ احتمال بارش: {rain} | 💨 باد: {wind_text}",
                "────────────────────",
            ]
        )

    lines.extend(
        [
            "",
            "ℹ️ داده‌های هواشناسی: Open-Meteo",
            "",
            "@NabzKhabarOfficial",
        ]
    )
    return "\n".join(lines)


def main(send_message=None):
    now = datetime.now(ZoneInfo(TIMEZONE))
    today = now.date().isoformat()
    history = _load_history()

    if history.get("last_published_date") == today:
        print(f"WEATHER: already published today ({today}).", flush=True)
        return False

    if send_message is None:
        print("WEATHER: Telegram sender is not configured.", flush=True)
        return False

    try:
        data = _fetch_weather()
        if len(data) != len(CITIES):
            print(
                f"WEATHER: incomplete response ({len(data)}/{len(CITIES)} cities).",
                flush=True,
            )
            return False

        jalali_date = _jalali_date(now)
        text = _format_board(data, jalali_date)

        if not send_message(text):
            print("WEATHER: Telegram publication failed.", flush=True)
            return False

        history["last_published_date"] = today
        history["last_published_jalali_date"] = jalali_date
        history["published_at"] = now.isoformat()
        _save_history(history)

        print(f"WEATHER: published daily board for {jalali_date}.", flush=True)
        return True
    except Exception as exc:
        print(f"WEATHER ERROR: {exc}", flush=True)
        return False


if __name__ == "__main__":
    main()
