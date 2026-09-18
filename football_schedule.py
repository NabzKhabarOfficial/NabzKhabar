import json
import math
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from PIL import Image, ImageDraw, ImageFont


TEHRAN = ZoneInfo("Asia/Tehran")
API_BASE = "https://v3.football.api-sports.io"
API_KEY_ENV = "API_FOOTBALL_KEY"
HISTORY_FILE = "football_schedule_history.json"
BOT_TOKEN_ENV = "BOT_TOKEN"
CHANNEL = "@NabzKhabarOfficial"
REQUEST_TIMEOUT = 20
TELEGRAM_TIMEOUT = 30
FONT_PATH = "Vazirmatn-Bold.ttf"
SCHEDULE_IMAGE = "football_schedule.jpg"
RESULTS_IMAGE = "football_results.jpg"
FOOTBALL_PHOTO_URL = "https://upload.wikimedia.org/wikipedia/commons/1/10/Wembley_Stadium_at_night.jpg"

PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

LEAGUE_PRIORITY = {
    ("Premier League", "England"): 100,
    ("LaLiga", "Spain"): 98,
    ("Serie A", "Italy"): 96,
    ("Bundesliga", "Germany"): 95,
    ("Ligue 1", "France"): 94,
    ("UEFA Champions League", ""): 93,
    ("Champions League", ""): 93,
    ("UEFA Europa League", ""): 92,
    ("Europa League", ""): 92,
    ("UEFA Conference League", ""): 91,
    ("Conference League", ""): 91,
    ("Persian Gulf Pro League", "Iran"): 90,
    ("Saudi Pro League", "Saudi-Arabia"): 86,
    ("Eredivisie", "Netherlands"): 84,
    ("Liga Portugal", "Portugal"): 83,
    ("Primeira Liga", "Portugal"): 83,
    ("Süper Lig", "Turkey"): 82,
    ("AFC Champions League", ""): 81,
}

LEAGUE_FA = {
    ("Premier League", "England"): "لیگ برتر انگلیس",
    ("LaLiga", "Spain"): "لالیگا اسپانیا",
    ("Serie A", "Italy"): "سری‌آ ایتالیا",
    ("Bundesliga", "Germany"): "بوندس‌لیگا آلمان",
    ("Ligue 1", "France"): "لیگ ۱ فرانسه",
    ("UEFA Champions League", ""): "لیگ قهرمانان اروپا",
    ("Champions League", ""): "لیگ قهرمانان اروپا",
    ("UEFA Europa League", ""): "لیگ اروپا",
    ("Europa League", ""): "لیگ اروپا",
    ("UEFA Conference League", ""): "لیگ کنفرانس اروپا",
    ("Conference League", ""): "لیگ کنفرانس اروپا",
    ("Persian Gulf Pro League", "Iran"): "لیگ برتر ایران",
    ("Saudi Pro League", "Saudi-Arabia"): "لیگ حرفه‌ای عربستان",
    ("Eredivisie", "Netherlands"): "اردیویسه هلند",
    ("Liga Portugal", "Portugal"): "لیگ پرتغال",
    ("Primeira Liga", "Portugal"): "لیگ پرتغال",
    ("Süper Lig", "Turkey"): "سوپرلیگ ترکیه",
    ("AFC Champions League", ""): "لیگ قهرمانان آسیا",
}

IMPORTANT_LEAGUES = {tuple(k.lower() for k in key) for key in LEAGUE_PRIORITY}

IMPORTANT_TEAMS = {
    "real madrid", "barcelona", "atletico madrid", "manchester united",
    "manchester city", "liverpool", "arsenal", "chelsea", "tottenham",
    "bayern munich", "bayern münchen", "borussia dortmund",
    "paris saint-germain", "psg", "juventus", "inter milan",
    "ac milan", "milan", "napoli", "roma", "ajax", "psv eindhoven",
    "benfica", "porto", "galatasaray", "fenerbahce", "al hilal",
    "al nassr", "persepolis", "esteghlal",
}

# Only these clubs are eligible for the daily football post.
# Being in a major league is NOT enough by itself.
MAJOR_TEAMS_BY_LEAGUE = {
    ("Premier League", "England"): {
        "arsenal", "chelsea", "liverpool", "manchester city",
        "manchester united", "tottenham",
    },
    ("LaLiga", "Spain"): {"real madrid", "barcelona", "atletico madrid"},
    ("Serie A", "Italy"): {"inter milan", "ac milan", "milan", "juventus", "napoli", "roma"},
    ("Bundesliga", "Germany"): {"bayern munich", "bayern münchen", "borussia dortmund"},
    ("Ligue 1", "France"): {"paris saint-germain", "psg"},
    ("Eredivisie", "Netherlands"): {"ajax", "psv eindhoven"},
    ("Liga Portugal", "Portugal"): {"benfica", "porto"},
    ("Primeira Liga", "Portugal"): {"benfica", "porto"},
    ("Süper Lig", "Turkey"): {"galatasaray", "fenerbahce"},
    ("Saudi Pro League", "Saudi-Arabia"): {"al hilal", "al nassr"},
    ("Persian Gulf Pro League", "Iran"): {"persepolis", "esteghlal"},
}


def fa_digits(value):
    return str(value).translate(PERSIAN_DIGITS)


def now_tehran():
    return datetime.now(TEHRAN)


def today_key():
    return now_tehran().strftime("%Y-%m-%d")


def load_history():
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            value = json.load(f)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def save_history(data):
    tmp = HISTORY_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, HISTORY_FILE)


def _font(size):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()


def _load_football_photo(width, height):
    """Load a free/public-domain football stadium photo for the visual header."""
    try:
        response = requests.get(FOOTBALL_PHOTO_URL, timeout=10)
        response.raise_for_status()
        from io import BytesIO

        photo = Image.open(BytesIO(response.content)).convert("RGB")
        src_w, src_h = photo.size
        target_ratio = width / height
        src_ratio = src_w / src_h
        if src_ratio > target_ratio:
            crop_w = int(src_h * target_ratio)
            left = (src_w - crop_w) // 2
            photo = photo.crop((left, 0, left + crop_w, src_h))
        else:
            crop_h = int(src_w / target_ratio)
            top = max(0, (src_h - crop_h) // 2)
            photo = photo.crop((0, top, src_w, top + crop_h))
        return photo.resize((width, height), Image.Resampling.LANCZOS)
    except Exception as exc:
        print(f"FOOTBALL: header photo unavailable, using local design: {exc}")
        return None


def _norm(value):
    return " ".join(str(value or "").lower().replace("-", " ").split())


def _league_key(item):
    return (_norm(item["league"]), _norm(item["country"]))


def _team_is_major(name):
    return _norm(name) in IMPORTANT_TEAMS


def _major_team_in_league(item):
    teams = MAJOR_TEAMS_BY_LEAGUE.get(_league_key(item))
    if teams is None:
        # European competitions have no single domestic country key.
        return _team_is_major(item["home"]) or _team_is_major(item["away"])
    return _norm(item["home"]) in teams or _norm(item["away"]) in teams


def _important(item):
    supported = (
        _league_key(item) in IMPORTANT_LEAGUES
        or (_norm(item["league"]), "") in IMPORTANT_LEAGUES
    )
    return supported and _major_team_in_league(item)


def fetch_today():
    key = os.getenv(API_KEY_ENV, "").strip()
    if not key:
        print("FOOTBALL: API_FOOTBALL_KEY is missing.")
        return []

    try:
        response = requests.get(
            f"{API_BASE}/fixtures",
            params={"date": today_key(), "timezone": "Asia/Tehran"},
            headers={"x-apisports-key": key, "Accept": "application/json"},
            timeout=REQUEST_TIMEOUT,
        )
        payload = response.json()
        if not response.ok or payload.get("errors"):
            print(f"FOOTBALL: API-Football failed: {response.status_code} {payload.get('errors')}")
            return []
    except Exception as exc:
        print(f"FOOTBALL: API-Football request failed: {exc}")
        return []

    matches = []
    for raw in payload.get("response") or []:
        fixture = raw.get("fixture") or {}
        teams = raw.get("teams") or {}
        league = raw.get("league") or {}
        status = fixture.get("status") or {}
        goals = raw.get("goals") or {}
        try:
            kickoff = datetime.fromisoformat(
                str(fixture.get("date")).replace("Z", "+00:00")
            ).astimezone(TEHRAN)
        except Exception:
            continue

        home = str((teams.get("home") or {}).get("name") or "").strip()
        away = str((teams.get("away") or {}).get("name") or "").strip()
        league_name = str(league.get("name") or "").strip()
        country = str(league.get("country") or "").strip()
        fixture_id = fixture.get("id")

        if (
            not fixture_id
            or not home
            or not away
            or not league_name
            or kickoff.strftime("%Y-%m-%d") != today_key()
        ):
            continue

        item = {
            "id": str(fixture_id),
            "league": league_name,
            "league_fa": LEAGUE_FA.get((league_name, country), LEAGUE_FA.get((league_name, ""), league_name)),
            "home": home,
            "away": away,
            "kickoff": kickoff.isoformat(),
            "priority": LEAGUE_PRIORITY.get((league_name, country), LEAGUE_PRIORITY.get((league_name, ""), 0)),
            "home_score": goals.get("home"),
            "away_score": goals.get("away"),
            "status": str(status.get("short") or "").upper(),
        }
        if _important(item):
            matches.append(item)

    print(f"FOOTBALL: API-Football fixtures={len(payload.get('response') or [])} important={len(matches)}")
    return matches


def select_matches(matches):
    def score(item):
        # Major-club presence is mandatory; this bonus orders
        # the already-filtered fixtures by competition importance.
        major_bonus = 1000 if _major_team_in_league(item) else 0
        return major_bonus + item["priority"]

    ranked = sorted(matches, key=lambda x: (-score(x), x["kickoff"], x["home"]))

    # Never pad the list with ordinary fixtures. Publish at most 8.
    return [item for item in ranked if _major_team_in_league(item)][:8]


def kickoff_text(item):
    return fa_digits(datetime.fromisoformat(item["kickoff"]).strftime("%H:%M"))


def create_table_image(matches, final=False):
    width, height = 1600, 1250
    image = Image.new("RGB", (width, height), (7, 13, 11))
    draw = ImageDraw.Draw(image)

    # Use a free/public-domain football stadium photograph as the hero image.
    # If the image host is unavailable, fall back to the local football design.
    hero_h = 330
    hero = _load_football_photo(width, hero_h)
    if hero is not None:
        image.paste(hero, (0, 0))
        hero_overlay = Image.new("RGBA", (width, hero_h), (0, 0, 0, 115))
        image = Image.alpha_composite(image.convert("RGBA"), hero_overlay).convert("RGB")
        draw = ImageDraw.Draw(image)
    else:
        draw.rectangle((0, 0, width, hero_h), fill=(12, 20, 29))
        for x in range(-40, width + 80, 70):
            draw.polygon([(x, hero_h), (x + 35, 120), (x + 70, hero_h)], fill=(17, 27, 36))
    pitch_top = 280
    draw.polygon(
        [(95, pitch_top), (1505, pitch_top), (1590, height), (10, height)],
        fill=(20, 101, 53),
    )
    for i in range(-1, 10):
        x1 = 95 + i * 176
        x2 = x1 + 176
        if i % 2 == 0:
            draw.polygon(
                [(x1, pitch_top), (x2, pitch_top), (x2 + 85, height), (x1 + 85, height)],
                fill=(23, 111, 58),
            )

    white = (232, 238, 233)
    draw.line((95, pitch_top, 1505, pitch_top), fill=white, width=5)
    draw.line((800, pitch_top, 800, height), fill=white, width=4)
    draw.ellipse((590, 555, 1010, 975), outline=white, width=5)

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rounded_rectangle(
        (55, 250, 1545, height - 35),
        radius=30,
        fill=(5, 12, 10, 230),
        outline=(235, 240, 235, 90),
        width=2,
    )
    image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(image)

    title = "📊 نتایج نهایی مسابقات امروز" if final else "⚽ برنامه مسابقات مهم امروز"
    draw.text((90, 38), title, font=_font(62), fill="white")
    draw.text((92, 125), "NABZ KHABAR  |  نبض خبر", font=_font(34), fill=(210, 225, 216))
    draw.text(
        (92, 175),
        f'{fa_digits(now_tehran().strftime("%Y/%m/%d"))}  •  ساعت ایران',
        font=_font(34),
        fill=(235, 240, 235),
    )

    draw.rounded_rectangle((82, 285, 1518, 345), radius=14, fill=(29, 54, 37))
    draw.text((120, 302), "ساعت", font=_font(24), fill="white")
    draw.text((315, 302), "مسابقه", font=_font(24), fill="white")
    draw.text((1170, 302), "نتیجه", font=_font(24), fill="white")

    y = 345
    for item in sorted(matches, key=lambda x: x["kickoff"]):
        draw.rounded_rectangle(
            (82, y, 1518, y + 70),
            radius=12,
            fill=(22, 43, 28) if final else (18, 31, 24),
            outline=(69, 105, 80),
            width=1,
        )
        draw.rounded_rectangle((105, y + 12, 255, y + 58), radius=12, fill=(36, 68, 45))
        draw.text((135, y + 20), kickoff_text(item), font=_font(27), fill="white")
        draw.text(
            (315, y + 8),
            f'{item["home"]}  🆚  {item["away"]}',
            font=_font(27),
            fill=(250, 252, 250),
        )
        draw.text(
            (315, y + 38),
            item["league_fa"][:34],
            font=_font(19),
            fill=(181, 202, 187),
        )
        if final:
            score = (
                f'{item["home_score"]}-{item["away_score"]}'
                if item["home_score"] is not None and item["away_score"] is not None
                else ("لغو" if item["status"] in {"CANC", "ABD"} else "نتیجه ثبت نشد")
            )
        else:
            score = "⏰"
        draw.rounded_rectangle((1125, y + 12, 1495, y + 58), radius=12, fill=(24, 51, 32))
        draw.text((1170, y + 20), fa_digits(score), font=_font(27), fill="white")
        y += 78

    draw.text((1160, height - 55), "@NabzKhabarOfficial", font=_font(24), fill="white")
    path = RESULTS_IMAGE if final else SCHEDULE_IMAGE
    image.save(path, "JPEG", quality=92, optimize=True)
    return path


def build_caption(matches, final=False):
    date = fa_digits(now_tehran().strftime("%Y/%m/%d"))
    lines = [
        "📊 نتایج نهایی مسابقات مهم امروز | نبض خبر" if final else "⚽ برنامه مسابقات مهم امروز | نبض خبر",
        f"📅 {date}",
        "🕐 تمام ساعت‌ها به وقت ایران (تهران)",
        "🎯 فقط مسابقات مهم و منتخب",
        "",
    ]

    if final:
        for item in sorted(matches, key=lambda x: x["kickoff"]):
            if item["home_score"] is not None and item["away_score"] is not None:
                result = f'{item["home"]} {item["home_score"]}-{item["away_score"]} {item["away"]}'
            elif item["status"] in {"CANC", "ABD"}:
                result = f'{item["home"]} — لغو شد — {item["away"]}'
            else:
                result = f'{item["home"]} — نتیجه ثبت نشد — {item["away"]}'
            lines.append(f"• {result} | {item['league_fa']}")
    else:
        for item in sorted(matches, key=lambda x: x["kickoff"]):
            lines.append(
                f'• {kickoff_text(item)}  │  {item["home"]}  🆚  {item["away"]} | {item["league_fa"]}'
            )

    lines += [
        "",
        "#فوتبال #نتایج_فوتبال #نبض_خبر",
        "🔗 کانال نبض خبر: https://t.me/NabzKhabarOfficial",
    ]
    return "\n".join(lines)[:1024]


def send_photo(image_path, caption):
    token = os.getenv(BOT_TOKEN_ENV, "").strip()
    if not token:
        print("FOOTBALL: BOT_TOKEN missing.")
        return False

    try:
        with open(image_path, "rb") as photo:
            response = requests.post(
                f"https://api.telegram.org/bot{token}/sendPhoto",
                data={"chat_id": CHANNEL, "caption": caption},
                files={"photo": photo},
                timeout=TELEGRAM_TIMEOUT,
            )
        payload = response.json()
        if response.ok and payload.get("ok"):
            return True
        print(f"FOOTBALL: Telegram sendPhoto failed: {response.status_code} {payload}")
    except Exception as exc:
        print(f"FOOTBALL: Telegram sendPhoto failed: {exc}")
    return False


def _serialize(item):
    return dict(item)


def _same_day_fixture_ids(items):
    return [str(item["id"]) for item in items]


def _final_matches_from_morning(morning, fresh):
    wanted = set(_same_day_fixture_ids(morning))
    by_id = {str(item["id"]): item for item in fresh}
    return [by_id[item_id] for item_id in _same_day_fixture_ids(morning) if item_id in by_id]


def post_daily_football_schedule(send_message, send_photo=None):
    """
    Final lightweight football flow:
      1) One morning post with the important matches of the day.
      2) One end-of-day post containing final results for exactly those matches.
    No live scores, no message editing, no repeated refreshes, no secondary API.
    """
    now = now_tehran()
    day = today_key()
    history = load_history()

    # Morning publication: first successful workflow run of the Iran calendar day.
    if history.get("morning_posted_date") != day:
        matches = select_matches(fetch_today())
        if not matches:
            print("FOOTBALL: no important matches today; no morning post.")
            return False

        image = create_table_image(matches, final=False)
        caption = build_caption(matches, final=False)
        if not send_photo(image, caption):
            print("FOOTBALL: morning schedule publication failed.")
            return False

        history.update({
            "morning_posted_date": day,
            "morning_matches": [_serialize(x) for x in matches],
            "final_posted_date": None,
        })
        save_history(history)
        print(f"FOOTBALL: morning schedule published | date={day} | matches={len(matches)}")
        return True

    # End-of-day publication: one fresh API call, once only, using the morning list.
    # 23:00-23:59 Tehran is the publication window; no live polling is performed.
    if now.hour < 23 or history.get("final_posted_date") == day:
        return False

    morning = history.get("morning_matches") or []
    if not morning:
        history["final_posted_date"] = day
        save_history(history)
        return False

    fresh = fetch_today()
    final_matches = _final_matches_from_morning(morning, fresh)
    if len(final_matches) != len(morning):
        print(
            f"FOOTBALL: final result set incomplete "
            f"({len(final_matches)}/{len(morning)}); will retry next run."
        )
        return False

    image = create_table_image(final_matches, final=True)
    caption = build_caption(final_matches, final=True)
    if not send_photo(image, caption):
        print("FOOTBALL: final results publication failed; will retry next run.")
        return False

    history["final_posted_date"] = day
    history["final_results"] = [_serialize(x) for x in final_matches]
    history["final_posted_at"] = now.isoformat()
    save_history(history)
    print(f"FOOTBALL: final results published | date={day} | matches={len(final_matches)}")
    return True
