"""Independent daily boards for the NabzKhabar channel.

Weather, car prices and the education tip are not news: they bypass every V13
news gate and are sent once per Tehran day. Each board is isolated so a failure
in one never affects the others or the news engine.

State lives in files the workflow already persists:
  weather_history.json   (weather + education keys)
  car_prices_history.json
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TEHRAN = ZoneInfo("Asia/Tehran")
WEATHER_HOUR = 7      # morning board
CAR_PRICES_HOUR = 11  # source usually updates late morning
EDUCATION_HOUR = 19   # evening tip
STATE_FILE = Path("weather_history.json")


def _log(msg):
    print(f"DAILY BOARDS: {msg}", flush=True)


def _plain(text):
    # Messages are sent without parse_mode, so Markdown markers would show literally.
    return str(text).replace("**", "")


def _run_weather(now):
    import weather
    original = weather._send_weather_message
    weather._send_weather_message = lambda text: original(_plain(text))
    try:
        weather.main()
    finally:
        weather._send_weather_message = original


def _run_car_prices(now):
    import car_prices
    car_prices.main()


def _load_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _run_education(now):
    import education
    import weather
    today = now.date().isoformat()
    state = _load_state()
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
    state = _load_state()
    state["education_last_date"] = today
    state["education_title"] = item["title"]
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
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
