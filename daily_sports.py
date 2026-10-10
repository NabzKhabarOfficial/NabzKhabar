"""Daily "important matches today" board for the NabzKhabar channel.

Source: the public varzesh3 live-score API (Persian names, Tehran times and
the anten.ir live-stream link with the commentator's name). Only important
matches are kept: Iran's national teams, the big Iranian clubs, the top
European leagues and cups, and decisive matches of big tournaments.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote
from zoneinfo import ZoneInfo

import requests

API = "https://web-api.varzesh3.com/v1.0/livescore/today"
TEHRAN = ZoneInfo("Asia/Tehran")
MAX_ROWS = 16
SPORT_NAMES = {1: "فوتبال", 2: "فوتسال", 3: "والیبال", 4: "بسکتبال", 5: "هندبال"}

TOP_LEAGUES = (
    "لیگ برتر انگلیس", "لالیگا اسپانیا", "سری آ ایتالیا", "بوندسلیگا", "بوندس لیگا",
    "لوشامپیونه", "لیگ 1 فرانسه", "لیگ قهرمانان اروپا", "لیگ اروپا", "لیگ کنفرانس",
    "لیگ قهرمانان آسیا", "لیگ نخبگان آسیا", "جام جهانی", "مقدماتی جام جهانی",
    "جام ملت های آسیا", "جام ملت های اروپا", "لیگ ملت های اروپا (a)", "کوپا آمریکا",
    "سوپر جام اروپا", "جام باشگاه های جهان", "لیگ برتر ایران", "لیگ برتر خلیج فارس",
    "جام حذفی ایران", "سوپرجام ایران", "لیگ ملت های والیبال", "قهرمانی جهان", "المپیک",
)
EXCLUDE_LEAGUE = ("زنان", "امید", "جوانان", "نوجوانان", "دسته دوم", " 2 ", "لیگ یک", "لیگ دو", "پیش فصل", "دوستانه بانوان")
BIG_STAGE = ("ناگویا", "بازی های آسیایی", "المپیک", "جام جهانی", "قهرمانی جهان")
KNOCKOUT = ("حذفی", "نیمه نهایی", "فینال", "یک چهارم")
BIG_CLUBS = (
    "پرسپولیس", "استقلال", "سپاهان", "تراکتور", "رئال مادرید", "بارسلونا", "منچستر سیتی",
    "منچستر یونایتد", "لیورپول", "آرسنال", "چلسی", "بایرن", "اینتر", "میلان", "یوونتوس",
    "پاری سن ژرمن", "اتلتیکو مادرید", "تاتنهام", "دورتموند", "ناپولی",
)


def _norm(text):
    text = str(text or "").replace("\u200c", " ").replace("ي", "ی").replace("ك", "ک")
    return re.sub(r"\s+", " ", text).strip()


def fetch(session=None):
    s = session or requests
    r = s.get(API, timeout=15, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0 Safari/537.36",
        "Referer": "https://www.varzesh3.com/", "Accept": "application/json"})
    r.raise_for_status()
    return r.json()


def _iran(m):
    return "ایران" in _norm(m.get("hostName")) + " " + _norm(m.get("guestName"))


def importance(match, league_title):
    """0 = skip, higher = more important."""
    lt = " " + _norm(league_title).lower() + " "
    teams = _norm(match.get("hostName")) + " " + _norm(match.get("guestName"))
    iran = _iran(match)
    if iran and "زنان" not in lt and "بانوان" not in teams:
        return 5
    if any(c in teams for c in BIG_CLUBS) and not any(x in lt for x in ("زنان", "امید", "جوانان", "نوجوانان")):
        return 4
    if any(b in lt for b in BIG_STAGE):
        return 3 if any(k in lt for k in KNOCKOUT) else 0
    if any(x in lt for x in EXCLUDE_LEAGUE):
        return 0
    if any(t.lower() in lt for t in TOP_LEAGUES):
        return 2
    return 0


def _broadcast(url):
    url = unquote(str(url or ""))
    if "anten.ir" not in url:
        return ""
    m = re.search(r"\(گزارش[-\s]([^)]+)\)", url)
    return "آنتن" + (" · " + m.group(1).replace("-", " ").strip() if m else "")


def visual_score(host, guest):
    """Score text for the image card, in VISUAL left-to-right order (guest - host).

    The card draws the score without Persian letters, so it is laid out left-to-right, while
    the team line "host – guest" is right-to-left with the host on the right. Writing the
    guest first puts each number on the same side as its team (fixed Oct 11 2026: the cards
    showed every result the wrong way round)."""
    return f"{guest} - {host}"


def _score(m):
    if m.get("sport") == 3:
        h, g = m.get("hostPoint", ""), m.get("guestPoint", "")
    else:
        h, g = m.get("hostGoals", ""), m.get("guestGoals", "")
    if str(h) == "" or str(g) == "":
        return ""
    return visual_score(h, g)


def select(data, now=None):
    now = now or datetime.now(TEHRAN)
    leagues = {lg.get("id"): lg for lg in data.get("leagues") or []}
    rows = []
    for m in data.get("matches") or []:
        lg = leagues.get(m.get("leagueId")) or {}
        title = _norm(lg.get("title", ""))
        imp = importance(m, title)
        if not imp:
            continue
        try:
            start = datetime.fromisoformat(str(m.get("scheduledStartOn")).replace("Z", "+00:00")).astimezone(TEHRAN)
        except Exception:
            continue
        if start < now - timedelta(hours=2) or start > now + timedelta(hours=22):
            continue
        status = int(m.get("status") or 0)
        rows.append({
            "start": start,
            "time": start.strftime("%H:%M"),
            "league": re.sub(r"\s*-\s*(?:هفته|گروهی|حذفی).*$", "", title) or title,
            "stage": (re.search(r"-\s*(.+)$", title) or [None, ""])[1],
            "sport": SPORT_NAMES.get(int(m.get("sport") or 1), "ورزش"),
            "host": _norm(m.get("hostName")),
            "guest": _norm(m.get("guestName")),
            "iran": _iran(m),
            "importance": imp,
            "live": bool(m.get("isLive")) or status == 2,
            "finished": status == 7,
            "score": _score(m) if (status in (2, 7) or m.get("isLive")) else "",
            "broadcast": _broadcast(m.get("liveStreamSource")),
        })
    rows.sort(key=lambda r: (-r["importance"], r["start"]))
    rows = rows[:MAX_ROWS]
    rows.sort(key=lambda r: r["start"])
    return rows


def caption(rows, jalali, fa):
    lines = [f"🏟 برنامه مسابقات مهم امروز | {fa(jalali)}", ""]
    iran = [r for r in rows if r["iran"]]
    for r in iran[:4]:
        lines.append(f"🇮🇷 {r['host']} - {r['guest']} | {r['sport']} | ساعت {fa(r['time'])}")
    if iran:
        lines.append("")
    lines.append(f"{fa(len(rows))} بازی مهم با ساعت پخش به وقت تهران")
    lines += ["", "📢 @NabzKhabarOfficial"]
    return "\n".join(lines)
