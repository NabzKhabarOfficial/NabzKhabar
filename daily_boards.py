"""Independent daily boards for the NabzKhabar channel.

Weather, car prices and the education tip are not news: they bypass every V13
news gate and are sent once per Tehran day. Weather and car prices are sent as
designed image cards (daily_cards); if rendering or the photo upload fails the
classic text board is sent instead. Each board is isolated so a failure in one
never affects the others or the news engine.

State lives in files the workflow already persists:
  weather_history.json   (weather + education keys)
  car_prices_history.json
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

TEHRAN = ZoneInfo("Asia/Tehran")
WEATHER_HOUR = 7      # morning board
CAR_PRICES_HOUR = 11  # source usually updates late morning
EDUCATION_HOUR = 19   # evening tip
STATE_FILE = Path("weather_history.json")
CHANNEL_ID = "@NabzKhabarOfficial"


def _log(msg):
    print(f"DAILY BOARDS: {msg}", flush=True)


def _plain(text):
    # Messages are sent without parse_mode, so Markdown markers would show literally.
    return str(text).replace("**", "")


def _load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def send_photo(path, caption):
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        _log("BOT_TOKEN is not configured")
        return False
    try:
        with open(path, "rb") as fh:
            r = requests.post(
                f"https://api.telegram.org/bot{token}/sendPhoto",
                data={"chat_id": CHANNEL_ID, "caption": caption[:1000]},
                files={"photo": ("board.jpg", fh, "image/jpeg")},
                timeout=60,
            )
        if r.ok:
            return True
        _log(f"sendPhoto failed: {r.status_code} {r.text[:300]}")
    except Exception as exc:
        _log(f"sendPhoto error: {type(exc).__name__}: {exc}")
    return False


# ------------------------------------------------------------------ weather
def _weather_rows(weather, data):
    rows = []
    for idx, (city, _, _) in enumerate(weather.CITIES):
        item = data[idx]
        cur = item.get("current") or {}
        daily = item.get("daily") or {}

        def first(key):
            v = (daily.get(key) or [None])[0]
            return None if v is None else float(v)

        rows.append({
            "city": city,
            "temp": cur.get("temperature_2m"),
            "code": int((daily.get("weather_code") or [cur.get("weather_code", 0)])[0] or 0),
            "tmin": first("temperature_2m_min"),
            "tmax": first("temperature_2m_max"),
            "rain": first("precipitation_probability_max"),
        })
    return rows


def _weather_caption(rows, jalali, fa):
    vals = [r for r in rows if r["tmin"] is not None and r["tmax"] is not None]
    lines = [f"🌤 هواشناسی امروز ایران | {fa(jalali)}", ""]
    if vals:
        hot = max(vals, key=lambda r: r["tmax"])
        cold = min(vals, key=lambda r: r["tmin"])
        hot_t = fa(format(hot["tmax"], ".0f"))
        cold_t = fa(format(cold["tmin"], ".0f"))
        lines.append(f"🔥 گرم‌ترین: {hot['city']} {hot_t}°")
        lines.append(f"❄️ سردترین: {cold['city']} {cold_t}°")
    rainy = [r["city"] for r in sorted(rows, key=lambda r: -(r["rain"] or 0)) if (r["rain"] or 0) >= 50][:4]
    if rainy:
        lines.append("🌧 احتمال بارش بالا: " + "، ".join(rainy))
    lines += ["", "📢 @NabzKhabarOfficial"]
    return "\n".join(lines)


def _run_weather(now):
    import daily_cards
    import weather
    today = now.date().isoformat()
    history = weather._load_history()
    if history.get("last_published_date") == today:
        _log(f"weather already published today ({today})")
        return
    data = weather._fetch_weather()
    jalali = weather._jalali_date(now)
    rows = _weather_rows(weather, data)
    sent = False
    with tempfile.TemporaryDirectory() as tmp:
        card = daily_cards.render_weather(rows, jalali, os.path.join(tmp, "weather.jpg"), weather._weather_text)
        if card:
            sent = send_photo(card, _weather_caption(rows, jalali, daily_cards.fa))
            _log("weather card sent" if sent else "weather card failed, falling back to text")
    if not sent:
        sent = weather._send_weather_message(_plain(weather._format_board(data, jalali)))
    if not sent:
        _log("weather publication failed")
        return
    history = weather._load_history()
    history.update({"last_published_date": today, "last_published_jalali_date": jalali,
                    "published_at": now.isoformat()})
    weather._save_history(history)
    _log(f"weather published for {jalali}")


# ------------------------------------------------------------------ car prices
def _run_car_prices(now):
    import car_prices
    import daily_cards
    from bs4 import BeautifulSoup
    today = now.strftime("%Y-%m-%d")
    state = car_prices.load_state()
    if state.get("last_published_date") == today:
        _log(f"car prices already published today ({today})")
        return
    html = car_prices.fetch_source()
    update_date = car_prices.extract_update_date(BeautifulSoup(html, "html.parser"))
    if not car_prices.source_date_matches_today(update_date, now):
        _log(f"car source not updated today (source={update_date or 'unknown'})")
        return
    found = car_prices.extract_models(html)
    items = []
    for label, aliases in car_prices.TARGET_MODELS:
        item = car_prices.choose_model(found, aliases)
        if item:
            items.append((label, item.get("market"), item.get("factory"), item.get("change")))
    if not items:
        raise RuntimeError("no supported car prices found")
    sent = False
    with tempfile.TemporaryDirectory() as tmp:
        card = daily_cards.render_cars(items, update_date, os.path.join(tmp, "cars.jpg"))
        if card:
            caption = (f"🚗 قیمت روز خودرو | {daily_cards.fa(update_date.split(' امروز')[0])}\n"
                       f"{daily_cards.fa(len(items))} مدل پرطرفدار · بازار و کارخانه\n\n📢 @NabzKhabarOfficial")
            sent = send_photo(card, caption)
            _log("car card sent" if sent else "car card failed, falling back to text")
    if not sent:
        text, count = car_prices.build_board(update_date, found)
        if count:
            car_prices.send_telegram(text)
            sent = True
    if not sent:
        return
    state = car_prices.load_state()
    state.update({"last_published_date": today, "source_update_date": update_date,
                  "published_at": now.isoformat(), "models_count": len(items)})
    car_prices.save_state(state)
    _log(f"car prices published: {len(items)} models")


# ------------------------------------------------------------------ education
def _run_education(now):
    import education
    import weather
    today = now.date().isoformat()
    state = _load_json(STATE_FILE)
    if state.get("education_last_date") == today:
        _log(f"education already published today ({today})")
        return
    posts = education.EDUCATIONAL_POSTS
    item = posts[now.toordinal() % len(posts)]
    tips = "\n".join(f"• {tip}" for tip in item["tips"])
    text = (
        f"🎓 نبض آموزش | {item['title']}\n\n"
        f"{item['body']}\n\n"
        f"💡 ۳ نکته کاربردی:\n"
        f"{tips}\n\n"
        f"━━━━━━━━━━━━━━\n"
        f"{item.get('tag', '')}\n"
        f"📢 @NabzKhabarOfficial"
    )
    if not weather._send_weather_message(text):
        _log("education publication failed")
        return
    state = _load_json(STATE_FILE)
    state["education_last_date"] = today
    state["education_title"] = item["title"]
    _save_json(STATE_FILE, state)
    _log(f"education published: {item['title']}")


BOARDS = (
    ("weather", WEATHER_HOUR, _run_weather),
    ("car prices", CAR_PRICES_HOUR, _run_car_prices),
    ("education", EDUCATION_HOUR, _run_education),
)


def run(now=None):
    now = now or datetime.now(TEHRAN)
    for name, hour, fn in BOARDS:
        if now.hour < hour:
            continue
        try:
            fn(now)
        except Exception as exc:
            _log(f"{name} skipped: {type(exc).__name__}: {exc}")
