import hashlib
import json
import math
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from PIL import Image, ImageDraw, ImageFont


TEHRAN = ZoneInfo("Asia/Tehran")
# Primary source: ESPN public scoreboard API.
ESPN_API_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
FOTMOB_API_URL = "https://www.fotmob.com/api/matches"
TELEGRAM_API = "https://api.telegram.org/bot{}/{}"
HISTORY_FILE = "football_schedule_history.json"
REQUEST_TIMEOUT = 20
TELEGRAM_TIMEOUT = 30
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
    "Persian Gulf Pro League": 88,
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
    "Persian Gulf Pro League": "لیگ برتر ایران",
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
}

LEAGUE_KEYWORDS = tuple(LEAGUE_PRIORITY.keys())

ESPN_LEAGUES = {
    "eng.1": "Premier League",
    "esp.1": "LaLiga",
    "ita.1": "Serie A",
    "ger.1": "Bundesliga",
    "fra.1": "Ligue 1",
    "uefa.champions": "UEFA Champions League",
    "uefa.europa": "UEFA Europa League",
    "uefa.europa.conf": "UEFA Conference League",
    "sau.1": "Saudi Pro League",
    "ned.1": "Eredivisie",
    "por.1": "Liga Portugal",
    "tur.1": "Süper Lig",
    "sco.1": "Scottish Premiership",
    "usa.1": "Major League Soccer",
    "bra.1": "Brasileirão",
    "mex.1": "Liga MX",
    "fifa.worldq.uefa": "FIFA World Cup Qualifying - UEFA",
    "fifa.worldq.afc": "FIFA World Cup Qualifying - AFC",
}
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


def local_now():
    return datetime.now(TEHRAN)


def local_date():
    return local_now().date()


def _http_get_json(url, params=None):
    response = requests.get(
        url,
        params=params or {},
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept": "application/json,text/plain,*/*",
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("scoreboard response is not a JSON object")
    return payload


def _fetch_espn_league(league_slug, date_value):
    url = f"{ESPN_API_BASE}/{league_slug}/scoreboard"
    payload = _http_get_json(url, {"dates": date_value.strftime("%Y%m%d")})
    return payload.get("events") or []


def _normalize_espn_event(event, league_slug, league_label):
    competitions = event.get("competitions") or []
    if not competitions:
        return None
    competition = competitions[0] or {}
    competitors = competition.get("competitors") or []
    if len(competitors) < 2:
        return None
    home = next((x for x in competitors if x.get("homeAway") == "home"), competitors[0])
    away = next((x for x in competitors if x.get("homeAway") == "away"), competitors[1])
    home_team = str((home.get("team") or {}).get("displayName") or home.get("displayName") or "").strip()
    away_team = str((away.get("team") or {}).get("displayName") or away.get("displayName") or "").strip()
    if not home_team or not away_team:
        return None
    raw_date = event.get("date") or competition.get("date")
    if not raw_date:
        return None
    try:
        kickoff = datetime.fromisoformat(str(raw_date).replace("Z", "+00:00")).astimezone(TEHRAN)
    except Exception:
        return None
    if kickoff.date() != local_date():
        return None
    status = competition.get("status") or event.get("status") or {}
    status_type = status.get("type") or {}
    state = str(status_type.get("state") or "").lower()
    completed = bool(status_type.get("completed")) or state == "post"
    cancelled = state in {"canceled", "cancelled"} or str(status_type.get("name") or "").upper() == "STATUS_CANCELED"
    started = state == "in" or bool(status.get("period")) or bool(status.get("displayClock"))
    if completed:
        started = True
    if cancelled:
        state_text = "❌ لغو شده"
    elif completed:
        state_text = "✅ پایان یافته"
    elif started:
        state_text = "🔴 زنده"
    else:
        state_text = "⏰ برنامه‌ریزی‌شده"
    def competitor_score(item):
        value = item.get("score")
        try:
            return int(str(value).strip()) if value is not None else None
        except Exception:
            return None
    home_score = competitor_score(home)
    away_score = competitor_score(away)
    score = f"{home_score}-{away_score}" if home_score is not None and away_score is not None else "—"
    return {
        "id": str(event.get("id") or f"{league_slug}-{home_team}-{away_team}-{raw_date}"),
        "league": league_label,
        "league_fa": LEAGUE_FA.get(league_label, league_label),
        "home": home_team,
        "away": away_team,
        "kickoff": kickoff,
        "priority": LEAGUE_PRIORITY.get(league_label, 60),
        "state": state_text,
        "started": started,
        "finished": completed,
        "cancelled": cancelled,
        "home_score": home_score,
        "away_score": away_score,
        "score": score,
    }


def fetch_matches_for_utc_date(date_value):
    """Fetch important fixtures from ESPN, with FotMob as last resort."""
    matches = []
    successful_sources = 0
    for league_slug, league_label in ESPN_LEAGUES.items():
        try:
            events = _fetch_espn_league(league_slug, date_value)
            successful_sources += 1
            for event in events:
                item = _normalize_espn_event(event, league_slug, league_label)
                if item:
                    matches.append(item)
        except Exception as exc:
            print(f"FOOTBALL: ESPN {league_slug} failed for {date_value}: {exc}")
    if successful_sources:
        return matches
    try:
        payload = _http_get_json(FOTMOB_API_URL, {"date": date_value.strftime("%Y%m%d")})
        return payload.get("leagues", []) if isinstance(payload, dict) else []
    except Exception as exc:
        print(f"FOOTBALL: fallback source failed for {date_value}: {exc}")
        return []


def _score_value(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    return None


def extract_score(match, status):
    score_str = status.get("scoreStr") or status.get("score")
    if isinstance(score_str, str):
        # FotMob commonly exposes strings such as "2 - 1".
        parts = score_str.replace("–", "-").replace("—", "-").split("-")
        if len(parts) >= 2:
            home = _score_value(parts[0].strip())
            away = _score_value(parts[1].strip())
            if home is not None and away is not None:
                return home, away

    home_obj = match.get("home") or {}
    away_obj = match.get("away") or {}

    home_score = (
        _score_value(home_obj.get("score"))
        if isinstance(home_obj, dict)
        else None
    )
    away_score = (
        _score_value(away_obj.get("score"))
        if isinstance(away_obj, dict)
        else None
    )

    if home_score is None:
        home_score = _score_value(status.get("homeScore"))
    if away_score is None:
        away_score = _score_value(status.get("awayScore"))

    return home_score, away_score


def normalize_match(league, match):
    status = match.get("status") or {}
    utc_value = status.get("utcTime")
    if not utc_value:
        return None

    try:
        kickoff = datetime.fromisoformat(
            str(utc_value).replace("Z", "+00:00")
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
        lower = league_name.lower()
        if any(k.lower() in lower for k in LEAGUE_KEYWORDS):
            priority = 60
        else:
            return None

    started = bool(status.get("started"))
    finished = bool(status.get("finished"))
    cancelled = bool(status.get("cancelled"))
    home_score, away_score = extract_score(match, status)

    if cancelled:
        state = "❌ لغو شده"
    elif finished:
        state = "✅ پایان یافته"
    elif started:
        state = "🔴 زنده"
    else:
        state = "⏰ برنامه‌ریزی‌شده"

    if home_score is not None and away_score is not None:
        score = f"{home_score}-{away_score}"
    else:
        score = "—"

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
        "cancelled": cancelled,
        "home_score": home_score,
        "away_score": away_score,
        "score": score,
    }


def get_today_matches():
    today = local_date()
    all_matches = {}

    # Iran's local day can straddle two UTC calendar dates.
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
    matches.sort(key=lambda x: (x["kickoff"], -x["priority"], x["league_fa"], x["home"]))
    return matches


# Only high-interest fixtures belong in the public daily table.
# The bot deliberately excludes lower-profile domestic/second-tier games.
IMPORTANT_TEAM_KEYWORDS = (
    "real madrid", "barcelona", "atletico madrid", "manchester united",
    "manchester city", "liverpool", "arsenal", "chelsea", "tottenham",
    "bayern munich", "bayern", "borussia dortmund", "psg", "paris saint-germain",
    "juventus", "inter", "milan", "napoli", "roma", "ajax", "psv",
    "benfica", "porto", "galatasaray", "fenerbahce", "al hilal",
    "al nassr", "persepolis", "esteghlal", "iran",
)

IMPORTANT_LEAGUES = {
    "Premier League", "LaLiga", "Serie A", "Bundesliga", "Ligue 1",
    "UEFA Champions League", "Champions League",
    "UEFA Europa League", "Europa League",
    "UEFA Conference League", "Conference League",
    "Persian Gulf Pro League", "AFC Champions League",
    "Saudi Pro League",
}

def select_matches(matches):
    def importance(item):
        league_bonus = 100 if item["league"] in IMPORTANT_LEAGUES else 0
        teams = f'{item["home"]} {item["away"]}'.lower()
        team_bonus = 40 if any(k in teams for k in IMPORTANT_TEAM_KEYWORDS) else 0
        # Prioritize finals/knockout games and live/finished matches so important
        # results remain visible even after kickoff.
        state_bonus = 20 if item["started"] or item["finished"] else 0
        return league_bonus + team_bonus + state_bonus + item["priority"]

    selected = sorted(
        matches,
        key=lambda x: (-importance(x), x["kickoff"], x["home"])
    )

    # Keep the table intentionally compact: major fixtures only.
    return selected[:12]


def _result_lines(matches):
    finished = [
        m for m in sorted(matches, key=lambda x: x["kickoff"])
        if m["finished"] and not m["cancelled"] and m["score"] != "—"
    ]
    lines = ["📊 نتایج نهایی"]
    if not finished:
        lines.append("هنوز بازی‌ای به پایان نرسیده است.")
        return lines

    for item in finished:
        lines.append(
            f"• {item['home']} {item['score']} {item['away']} | {item['league_fa']}"
        )
    return lines


def build_caption(matches):
    today = local_date()
    results = _result_lines(matches)

    # Telegram photo captions are limited. Keep this caption compact; the
    # complete fixture table is rendered inside the updated football image.
    lines = [
        "⚽ برنامه فوتبال امروز | نبض خبر",
        f"📅 {fa_digits(today.strftime('%Y/%m/%d'))}",
        "🕐 تمام ساعت‌ها به وقت ایران (تهران)",
        "",
    ]
    lines.extend(results)

    if any(m["started"] and not m["finished"] for m in matches):
        lines.extend(["", "🔴 بازی‌های در حال برگزاری با نتیجه لحظه‌ای نمایش داده می‌شوند."])

    lines.extend([
        "",
        "#فوتبال #برنامه_فوتبال #نتایج_فوتبال #نبض_خبر",
        "🔗 کانال نبض خبر: https://t.me/NabzKhabarOfficial",
    ])

    text = "\n".join(lines)
    # Defensive cap: never send an oversized Telegram photo caption.
    if len(text) > 1000:
        base = [
            "⚽ برنامه فوتبال امروز | نبض خبر",
            f"📅 {fa_digits(today.strftime('%Y/%m/%d'))}",
            "🕐 ساعت‌ها به وقت ایران (تهران)",
            "",
            "📊 نتایج نهایی در تصویر و جدول به‌روزرسانی می‌شوند.",
            "",
            "#فوتبال #برنامه_فوتبال #نتایج_فوتبال #نبض_خبر",
            "🔗 کانال نبض خبر: https://t.me/NabzKhabarOfficial",
        ]
        text = "\n".join(base)
    return text


def _font(size):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()


def _short(text, max_len):
    text = str(text or "")
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def create_schedule_image(matches):
    """Generate the daily football table locally and refresh it as scores change."""
    width, height = 1600, 1250
    image = Image.new("RGB", (width, height), (7, 13, 11))
    draw = ImageDraw.Draw(image)

    title_font = _font(72)
    date_font = _font(36)
    row_font = _font(28)
    small_font = _font(24)
    result_font = _font(27)

    # Stadium background.
    draw.rectangle((0, 0, width, 330), fill=(12, 20, 29))
    for x in range(-40, width + 80, 70):
        draw.polygon([(x, 330), (x + 35, 120), (x + 70, 330)], fill=(17, 27, 36))

    for x in (120, 410, 1190, 1480):
        draw.line((x, 25, x - 18, 320), fill=(80, 90, 96), width=5)
        draw.ellipse((x - 31, 18, x + 31, 55), fill=(225, 230, 220))

    # Pitch.
    pitch_top = 280
    draw.polygon(
        [(95, pitch_top), (1505, pitch_top), (1590, height), (10, height)],
        fill=(20, 101, 53),
    )
    stripe_width = 176
    for i in range(-1, 10):
        x1 = 95 + i * stripe_width
        x2 = x1 + stripe_width
        if i % 2 == 0:
            draw.polygon(
                [(x1, pitch_top), (x2, pitch_top), (x2 + 85, height), (x1 + 85, height)],
                fill=(23, 111, 58),
            )

    white = (232, 238, 233)
    draw.line((95, pitch_top, 1505, pitch_top), fill=white, width=5)
    draw.line((800, pitch_top, 800, height), fill=white, width=4)
    draw.ellipse((590, 555, 1010, 975), outline=white, width=5)

    # Football.
    ball_cx, ball_cy, ball_r = 1370, 1040, 95
    draw.ellipse(
        (ball_cx - ball_r, ball_cy - ball_r, ball_cx + ball_r, ball_cy + ball_r),
        fill=(238, 241, 237),
        outline=(38, 46, 43),
        width=6,
    )
    pentagon = []
    for i in range(5):
        a = math.radians(-90 + i * 72)
        pentagon.append((ball_cx + 31 * math.cos(a), ball_cy + 31 * math.sin(a)))
    draw.polygon(pentagon, fill=(25, 30, 28))
    for i in range(5):
        a = math.radians(-90 + i * 72)
        px = ball_cx + 31 * math.cos(a)
        py = ball_cy + 31 * math.sin(a)
        draw.line(
            (px, py, ball_cx + 72 * math.cos(a), ball_cy + 72 * math.sin(a)),
            fill=(50, 57, 53),
            width=4,
        )

    # Editorial panel.
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.rounded_rectangle(
        (55, 250, 1320, 1160),
        radius=30,
        fill=(5, 12, 10, 225),
        outline=(235, 240, 235, 90),
        width=2,
    )
    image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(image)

    draw.text((90, 38), "⚽ برنامه فوتبال امروز", font=title_font, fill="white")
    draw.text((92, 128), "NABZ KHABAR  |  نبض خبر", font=date_font, fill=(210, 225, 216))
    draw.text(
        (92, 178),
        f"{fa_digits(local_date().strftime('%Y/%m/%d'))}  •  ساعت ایران",
        font=date_font,
        fill=(235, 240, 235),
    )

    # Table header.
    draw.rounded_rectangle((82, 285, 1290, 335), radius=10, fill=(29, 54, 37))
    draw.text((110, 296), "ساعت", font=small_font, fill="white")
    draw.text((280, 296), "مسابقه", font=small_font, fill="white")
    draw.text((955, 296), "نتیجه / وضعیت", font=small_font, fill="white")

    visible = sorted(matches, key=lambda x: x["kickoff"])[:18]
    y = 345

    for item in visible:
        row_fill = (18, 31, 24)
        if item["finished"]:
            row_fill = (22, 43, 28)
        elif item["started"]:
            row_fill = (42, 45, 19)

        draw.rounded_rectangle(
            (82, y, 1290, y + 62),
            radius=12,
            fill=row_fill,
            outline=(69, 105, 80),
            width=1,
        )

        time_text = fa_digits(item["kickoff"].strftime("%H:%M"))
        matchup = _short(f'{item["home"]}  🆚  {item["away"]}', 52)

        if item["finished"] and item["score"] != "—":
            result_text = f"✅ {item['score']}"
        elif item["started"] and item["score"] != "—":
            result_text = f"🔴 {item['score']} | زنده"
        elif item["cancelled"]:
            result_text = "❌ لغو"
        else:
            result_text = "⏰ شروع"

        draw.text((110, y + 16), time_text, font=row_font, fill="white")
        draw.text((280, y + 8), matchup, font=row_font, fill=(250, 252, 250))
        draw.text(
            (280, y + 38),
            _short(item["league_fa"], 34),
            font=_font(20),
            fill=(181, 202, 187),
        )
        draw.text((955, y + 18), result_text, font=row_font, fill="white")
        y += 68

    if len(matches) > 18:
        draw.text(
            (92, 1085),
            f"+ {fa_digits(len(matches) - 18)} مسابقه دیگر در جدول کامل کانال",
            font=small_font,
            fill=(185, 205, 191),
        )

    # Results are deliberately placed at the bottom of the visual.
    finished = [
        m for m in sorted(matches, key=lambda x: x["kickoff"])
        if m["finished"] and not m["cancelled"] and m["score"] != "—"
    ]
    if finished:
        draw.text((92, 1115), "📊 نتایج نهایی امروز:", font=result_font, fill="white")
        compact = "  |  ".join(
            f"{_short(m['home'], 18)} {m['score']} {_short(m['away'], 18)}"
            for m in finished[:3]
        )
        draw.text((380, 1115), _short(compact, 62), font=_font(22), fill=(218, 232, 220))

    draw.text((1040, 1200), "@NabzKhabarOfficial", font=small_font, fill="white")

    image.save(IMAGE_PATH, "JPEG", quality=92, optimize=True)
    return IMAGE_PATH


def _telegram_request(method, data=None, files=None):
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        print("FOOTBALL: BOT_TOKEN missing; cannot manage live schedule message.")
        return None

    try:
        response = requests.post(
            TELEGRAM_API.format(token=token, method=method),
            data=data or {},
            files=files,
            timeout=TELEGRAM_TIMEOUT,
        )
        payload = response.json()
        if not response.ok or not payload.get("ok"):
            print(f"FOOTBALL: Telegram {method} failed: {response.status_code} {payload}")
            return None
        return payload.get("result")
    except Exception as exc:
        print(f"FOOTBALL: Telegram {method} exception: {exc}")
        return None


def publish_new_message(image_path, caption):
    result = _telegram_request(
        "sendPhoto",
        data={
            "chat_id": "@NabzKhabarOfficial",
            "caption": caption,
        },
        files={"photo": open(image_path, "rb")},
    )
    if isinstance(result, dict):
        return result.get("message_id")
    return None


def update_existing_message(message_id, image_path, caption):
    media = json.dumps(
        {
            "type": "photo",
            "media": "attach://photo",
            "caption": caption,
        },
        ensure_ascii=False,
    )
    result = _telegram_request(
        "editMessageMedia",
        data={
            "chat_id": "@NabzKhabarOfficial",
            "message_id": str(message_id),
            "media": media,
        },
        files={"photo": open(image_path, "rb")},
    )
    return isinstance(result, dict)


def _snapshot(matches):
    payload = []
    for item in sorted(matches, key=lambda x: x["kickoff"]):
        payload.append(
            (
                item["id"],
                item["state"],
                item["score"],
                item["home_score"],
                item["away_score"],
            )
        )
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def post_daily_football_schedule(send_message, send_photo=None):
    now = local_now()
    day_key = now.strftime("%Y-%m-%d")
    history = load_history()

    # Initial publication happens shortly after midnight Iran time.
    # Every later workflow run on the same day refreshes the same Telegram
    # message, so finished games acquire their final score automatically.
    matches = get_today_matches()
    if not matches:
        print("FOOTBALL: no supported fixtures found; no empty post sent.")
        return False

    selected = select_matches(matches)
    image_path = create_schedule_image(selected)
    caption = build_caption(selected)
    current_snapshot = _snapshot(selected)

    if history.get("last_posted_date") != day_key or not history.get("message_id"):
        # Only create a new daily post during the first 30 minutes of the day.
        if now.hour != 0 or now.minute >= 30:
            return False

        message_id = publish_new_message(image_path, caption)
        if not message_id:
            # Legacy fallback if direct Telegram management is unavailable.
            if send_photo is not None and send_photo(image_path, caption):
                print("FOOTBALL: daily schedule published through core sender.")
                return True
            if send_message(caption):
                return True
            return False

        history.update(
            {
                "last_posted_date": day_key,
                "message_id": message_id,
                "last_snapshot": current_snapshot,
                "last_match_count": len(selected),
                "updated_at": now.isoformat(),
            }
        )
        save_history(history)
        print(
            f"FOOTBALL: daily schedule published | date={day_key} | "
            f"matches={len(selected)} | message_id={message_id}"
        )
        return True

    # Same-day refresh: edit the original post instead of creating another
    # message. This keeps the channel clean and gives the user live scores.
    if history.get("last_snapshot") == current_snapshot:
        return False

    message_id = history.get("message_id")
    if not update_existing_message(message_id, image_path, caption):
        print("FOOTBALL: live result update failed; keeping previous post.")
        return False

    history.update(
        {
            "last_snapshot": current_snapshot,
            "last_match_count": len(selected),
            "updated_at": now.isoformat(),
        }
    )
    save_history(history)

    finished_count = sum(
        1 for item in selected if item["finished"] and item["score"] != "—"
    )
    live_count = sum(1 for item in selected if item["started"] and not item["finished"])
    print(
        f"FOOTBALL: schedule updated | date={day_key} | "
        f"finished={finished_count} | live={live_count} | message_id={message_id}"
    )
    return True
