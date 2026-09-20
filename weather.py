import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import time

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
    ("کرج", 35.8400, 50.9391),
    ("اهواز", 31.3183, 48.6706),
    ("قم", 34.6416, 50.8746),
    ("کرمانشاه", 34.3142, 47.0650),
    ("ارومیه", 37.5527, 45.0761),
    ("رشت", 37.2808, 49.5832),
    ("زاهدان", 29.4963, 60.8629),
    ("همدان", 34.7982, 48.5146),
    ("کرمان", 30.2839, 57.0834),
    ("یزد", 31.8974, 54.3569),
    ("اردبیل", 38.2498, 48.2933),
    ("بندرعباس", 27.1832, 56.2666),
    ("اراک", 34.0917, 49.6892),
    ("سنندج", 35.3219, 46.9862),
    ("قزوین", 36.2688, 50.0041),
    ("زنجان", 36.6736, 48.4787),
    ("خرم‌آباد", 33.4878, 48.3558),
    ("ساری", 36.5633, 53.0601),
    ("گرگان", 36.8456, 54.4393),
    ("بجنورد", 37.4750, 57.3333),
    ("بیرجند", 32.8663, 59.2211),
    ("بوشهر", 28.9234, 50.8203),
    ("ایلام", 33.6374, 46.4227),
    ("شهرکرد", 32.3256, 50.8644),
    ("یاسوج", 30.6682, 51.5870),
    ("سمنان", 35.5729, 53.3971),
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
    # Dependency-free Gregorian -> Jalali conversion so the weather module
    # stays completely free and does not add another package to the workflow.
    gy, gm, gd = dt.year, dt.month, dt.day
    g_days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    j_days = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29]

    gy2 = gy + 1 if gm > 2 else gy
    days = (
        365 * gy
        + (gy2 + 3) // 4
        - (gy2 + 99) // 100
        + (gy2 + 399) // 400
        - 80
        + gd
    )
    for i in range(gm - 1):
        days += g_days[i]
    if gm > 2 and ((gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0):
        days += 1

    jy = 979 + 33 * (days // 12053)
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

    return f"{jy:04d}/{jm:02d}/{jd:02d}"


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

    # Weather is a daily independent board. A transient network/API failure
    # should not permanently lose the day's publication, so use a small,
    # bounded retry instead of failing immediately.
    last_error = None
    for attempt in range(1, 4):
        try:
            print(
                f"WEATHER: Open-Meteo request attempt {attempt}/3 "
                f"for {len(CITIES)} provinces.",
                flush=True,
            )
            response = requests.get(API_URL, params=params, timeout=30)
            if not response.ok:
                preview = response.text[:500].replace("\\n", " ")
                raise RuntimeError(
                    f"HTTP {response.status_code}: {preview}"
                )
            data = response.json()
            result = data if isinstance(data, list) else [data]
            if len(result) != len(CITIES):
                raise RuntimeError(
                    f"incomplete API response: {len(result)}/{len(CITIES)}"
                )
            return result
        except Exception as exc:
            last_error = exc
            print(
                f"WEATHER: Open-Meteo attempt {attempt}/3 failed: "
                f"{type(exc).__name__}: {exc!r}",
                flush=True,
            )
            if attempt < 3:
                time.sleep(2 * attempt)

    raise RuntimeError(
        f"Open-Meteo failed after 3 attempts: "
        f"{type(last_error).__name__}: {last_error!r}"
    )


def _format_board(data, jalali_date):
    lines = [
        "🌤️ **هواشناسی ۳۱ استان ایران**",
        f"📅 امروز: {jalali_date}",
        "",
        "🌡️ دمای فعلی | 🔺 بیشینه | 🔻 کمینه | 🌧️ احتمال بارش",
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    for idx, (city, _, _) in enumerate(CITIES):
        item = data[idx]
        current = item.get("current") or {}
        daily = item.get("daily") or {}

        code = current.get("weather_code", 0)
        temp = current.get("temperature_2m")
        tmax = (daily.get("temperature_2m_max") or [None])[0]
        tmin = (daily.get("temperature_2m_min") or [None])[0]
        rain_prob = (daily.get("precipitation_probability_max") or [None])[0]

        def fmt(value, suffix="°"):
            return "—" if value is None else f"{float(value):.0f}{suffix}"

        rain = "—" if rain_prob is None else f"{int(round(float(rain_prob)))}٪"

        lines.append(
            f"📍 **{city}** | {fmt(temp)} | "
            f"🔺{fmt(tmax)} 🔻{fmt(tmin)} | "
            f"{_weather_text(code)} | 🌧️{rain}"
        )

    lines.extend(
        [
            "",
            "ℹ️ منبع داده: Open-Meteo",
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
        print(
            f"WEATHER ERROR: {type(exc).__name__}: {exc!r}",
            flush=True,
        )
        return False


if __name__ == "__main__":
    main()
