import json
import os
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from PIL import Image, ImageDraw, ImageFont


TEHRAN = ZoneInfo("Asia/Tehran")
API_URL = "https://www.fotmob.com/api/matches"
HISTORY_FILE = "football_schedule_history.json"
REQUEST_TIMEOUT = 20
FONT_PATH = "Vazirmatn-Bold.ttf"
IMAGE_PATH = "football_schedule.jpg"

LEAGUE_PRIORITY = {
    "Premier League": 100,
    "LaLiga": 98,
    "Serie A": 96,
    "Bundesliga": 95,
    "Ligue 1": 94,
    "UEFA Champions League": 93,
    "Champions League": 93,
    "UEFA Europa League": 92,
    "Europa League": 92,
    "UEFA Conference League": 91,
    "Conference League": 91,
    "Saudi Pro League": 86,
    "Eredivisie": 84,
    "Liga Portugal": 83,
    "Primeira Liga": 83,
    "Süper Lig": 82,
    "Scottish Premiership": 78,
    "Belgian Pro League": 77,
    "EFL Championship": 75,
    "Championship": 75,
    "Major League Soccer": 74,
    "MLS": 74,
    "Brasileirão": 73,
    "Copa Libertadores": 72,
    "AFC Champions League": 71,
    "Persian Gulf Pro League": 88,
}

LEAGUE_FA = {
    "Premier League": "لیگ برتر انگلیس",
    "LaLiga": "لالیگا اسپانیا",
    "Serie A": "سری‌آ ایتالیا",
    "Bundesliga": "بوندس‌لیگا آلمان",
    "Ligue 1": "لیگ ۱ فرانسه",
    "UEFA Champions League": "لیگ قهرمانان اروپا",
    "Champions League": "لیگ قهرمانان اروپا",
    "UEFA Europa League": "لیگ اروپا",
    "Europa League": "لیگ اروپا",
    "UEFA Conference League": "لیگ کنفرانس اروپا",
    "Conference League": "لیگ کنفرانس اروپا",
    "Saudi Pro League": "لیگ حرفه‌ای عربستان",
    "Eredivisie": "اردیویسه هلند",
    "Liga Portugal": "لیگ پرتغال",
    "Primeira Liga": "لیگ پرتغال",
    "Süper Lig": "سوپرلیگ ترکیه",
    "Scottish Premiership": "لیگ برتر اسکاتلند",
    "Belgian Pro League": "لیگ برتر بلژیک",
    "EFL Championship": "چمپیونشیپ انگلیس",
    "Championship": "چمپیونشیپ انگلیس",
    "Major League Soccer": "ام‌ال‌اس آمریکا",
    "MLS": "ام‌ال‌اس آمریکا",
    "Brasileirão": "سری‌آ برزیل",
    "Copa Libertadores": "کوپا لیبرتادورس",
    "AFC Champions League": "لیگ قهرمانان آسیا",
    "Persian Gulf Pro League": "لیگ برتر ایران",
}

# Only use a broad whitelist for the daily channel post. This prevents
# hundreds of low-interest lower-division fixtures from flooding the channel.
LEAGUE_KEYWORDS = tuple(LEAGUE_PRIORITY.keys())

PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def fa_digits(value):
    return str(value).translate(PERSIAN_DIGITS)


def load_history():
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_history(data):
    tmp = HISTORY_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, HISTORY_FILE)


def local_date():
    return datetime.now(TEHRAN).date()


def fetch_matches_for_utc_date(date_value):
    date_str = date_value.strftime("%Y%m%d")
    response = requests.get(
        API_URL,
        params={"date": date_str},
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 Chrome/126 Safari/537.36"
            ),
            "Accept": "application/json,text/plain,*/*",
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    return payload.get("leagues", []) if isinstance(payload, dict) else []


def normalize_match(league, match):
    status = match.get("status") or {}
    utc_value = status.get("utcTime")
    if not utc_value:
        return None

    try:
        kickoff = datetime.fromisoformat(
            utc_value.replace("Z", "+00:00")
        ).astimezone(TEHRAN)
    except Exception:
        return None

    if kickoff.date() != local_date():
        return None

    league_name = str(league.get("name") or "").strip()
    home = str((match.get("home") or {}).get("name") or "").strip()
    away = str((match.get("away") or {}).get("name") or "").strip()

    if not league_name or not home or not away:
        return None

    priority = LEAGUE_PRIORITY.get(league_name)
    if priority is None:
        # Handle small naming differences without accepting every league.
        lower = league_name.lower()
        if any(k.lower() in lower for k in LEAGUE_KEYWORDS):
            priority = 60
        else:
            return None

    started = bool(status.get("started"))
    finished = bool(status.get("finished"))
    cancelled = bool(status.get("cancelled"))

    if cancelled:
        state = "❌ لغو شده"
    elif finished:
        state = "✅ پایان یافته"
    elif started:
        state = "🔴 زنده"
    else:
        state = "⏰ برنامه‌ریزی‌شده"

    return {
        "id": str(match.get("id") or f"{home}-{away}-{utc_value}"),
        "league": league_name,
        "league_fa": LEAGUE_FA.get(league_name, league_name),
        "home": home,
        "away": away,
        "kickoff": kickoff,
        "priority": priority,
        "state": state,
        "started": started,
        "finished": finished,
    }


def get_today_matches():
    today = local_date()
    all_matches = {}

    # Query both UTC calendar dates around Iran's local day boundary.
    for utc_date in (today - timedelta(days=1), today):
        try:
            leagues = fetch_matches_for_utc_date(utc_date)
        except Exception as exc:
            print(f"FOOTBALL: fetch failed for {utc_date}: {exc}")
            continue

        for league in leagues:
            for match in league.get("matches") or []:
                item = normalize_match(league, match)
                if item:
                    all_matches[item["id"]] = item

    matches = list(all_matches.values())
    matches.sort(
        key=lambda x: (
            x["kickoff"],
            -x["priority"],
            x["league_fa"],
            x["home"],
        )
    )
    return matches


def select_matches(matches):
    # Professional daily post: prioritize major competitions, while still
    # allowing a reasonable number of other notable fixtures.
    major = sorted(
        matches,
        key=lambda x: (-x["priority"], x["kickoff"], x["home"])
    )

    # Keep at most 32 fixtures in one post.
    return major[:32]


def build_message(matches):
    today = local_date()
    lines = [
        "⚽ برنامه فوتبال امروز | نبض خبر",
        f"📅 {fa_digits(today.strftime('%Y/%m/%d'))}",
        "🕐 تمام ساعت‌ها به وقت ایران (تهران)",
        "",
        "┌────────┬────────────────────────────────────────┐",
        "│  ساعت  │ مسابقه                                  │",
        "├────────┼────────────────────────────────────────┤",
    ]

    for item in sorted(matches, key=lambda x: x["kickoff"]):
        time_text = fa_digits(item["kickoff"].strftime("%H:%M"))
        matchup = f'{item["home"]} 🆚 {item["away"]}'
        if len(matchup) > 39:
            matchup = matchup[:38] + "…"

        # Avoid relying on RTL spacing for the table itself.
        lines.append(f"│ {time_text} │ {matchup:<39} │")

        status = item["state"]
        lines.append(f"│        │ 🏆 {item['league_fa']} | {status:<18} │")

    lines.extend([
        "└────────┴────────────────────────────────────────┘",
        "",
        "📌 مسابقات بر اساس ساعت ایران مرتب شده‌اند.",
        "🔴 = در حال برگزاری   ⏰ = زمان شروع   ✅ = پایان‌یافته",
        "",
        "#فوتبال #برنامه_فوتبال #نبض_خبر",
        "",
        "🔗 کانال نبض خبر: https://t.me/NabzKhabarOfficial",
    ])
    return "\n".join(lines)


def create_schedule_image(matches):
    width, height = 1600, 900
    image = Image.new("RGB", (width, height), (13, 19, 28))
    draw = ImageDraw.Draw(image)
    try:
        title_font = ImageFont.truetype(FONT_PATH, 82)
        date_font = ImageFont.truetype(FONT_PATH, 42)
        row_font = ImageFont.truetype(FONT_PATH, 34)
        small_font = ImageFont.truetype(FONT_PATH, 27)
    except Exception:
        title_font = date_font = row_font = small_font = ImageFont.load_default()

    for i in range(0, width, 160):
        draw.line((i, 0, i + 300, height), fill=(28, 42, 58), width=3)
    draw.ellipse((1130, -180, 1770, 460), outline=(60, 83, 105), width=5)
    draw.ellipse((1240, -70, 1660, 350), outline=(60, 83, 105), width=3)

    draw.text((80, 60), "برنامه فوتبال امروز", font=title_font, fill="white")
    draw.text((82, 160), "NABZ KHABAR  |  نبض خبر", font=date_font, fill=(185, 205, 225))
    draw.text((82, 220), f"{fa_digits(local_date().strftime('%Y/%m/%d'))}  •  ساعت ایران", font=date_font, fill=(220, 230, 240))

    y = 310
    visible = sorted(matches, key=lambda x: x["kickoff"])[:8]
    for item in visible:
        if y > 785:
            break
        draw.rounded_rectangle((70, y, 1530, y + 105), radius=22, fill=(23, 33, 46), outline=(52, 70, 88), width=2)
        draw.text((112, y + 27), fa_digits(item["kickoff"].strftime("%H:%M")), font=row_font, fill="white")
        matchup = f'{item["home"]}  -  {item["away"]}'
        if len(matchup) > 55:
            matchup = matchup[:52] + "..."
        draw.text((360, y + 18), matchup, font=row_font, fill="white")
        draw.text((360, y + 62), item["league_fa"], font=small_font, fill=(180, 195, 210))
        y += 118

    if len(matches) > 8:
        draw.text((80, 825), f"+ {fa_digits(len(matches) - 8)} مسابقه دیگر در جدول کانال", font=small_font, fill=(180, 195, 210))
    draw.text((1190, 825), "@NabzKhabarOfficial", font=small_font, fill="white")
    image.save(IMAGE_PATH, "JPEG", quality=94, optimize=True)
    return IMAGE_PATH


def post_daily_football_schedule(send_message, send_photo=None):
    now = datetime.now(TEHRAN)
    day_key = now.strftime("%Y-%m-%d")
    history = load_history()

    # Post during the first 30 minutes of each Iran calendar day. The
    # workflow runs every 10 minutes, so this tolerates a missed single run.
    if now.hour != 0 or now.minute >= 30:
        return False

    if history.get("last_posted_date") == day_key:
        print(f"FOOTBALL: schedule already posted for {day_key}")
        return False

    matches = get_today_matches()
    if not matches:
        print("FOOTBALL: no supported fixtures found; no empty post sent.")
        return False

    selected = select_matches(matches)
    message = build_message(selected)
    image_path = create_schedule_image(selected)

    if send_photo is not None:
        if not send_photo(image_path, message):
            print("FOOTBALL: photo publication failed; falling back to text.")
            if not send_message(message):
                return False
    elif not send_message(message):
        print("FOOTBALL: Telegram publication failed.")
        return False

    history["last_posted_date"] = day_key
    history["last_match_count"] = len(selected)
    history["updated_at"] = now.isoformat()
    save_history(history)

    print(
        f"FOOTBALL: daily schedule published | "
        f"date={day_key} | matches={len(selected)}"
    )
    return True
