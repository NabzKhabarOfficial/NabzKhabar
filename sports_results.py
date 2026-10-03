"""End-of-day results for the morning "important matches" board.

The morning board (daily_boards._run_sports) remembers exactly which matches it
announced. After the last of them has finished, and not before 21:00 Tehran,
one results card is sent with the final scores of those same matches. Results
come from the public varzesh3 per-match API, which keeps working after midnight
(the "today" feed rolls over at 00:00 Tehran).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

import requests

import daily_sports

TEHRAN = daily_sports.TEHRAN
MATCH_API = "https://web-api.varzesh3.com/v1.0/livescore/{kind}/matches/{id}"
KINDS = {1: "football", 2: "futsal", 3: "volleyball", 4: "basketball", 5: "handball"}
RESULTS_HOUR = 21          # "end of the day": never earlier than this on the match day
MATCH_LENGTH = timedelta(hours=2, minutes=15)   # first check after the last kick-off
GIVE_UP_AFTER = timedelta(hours=4)              # post what is final if a match never closes
KEEP_DAYS = 3
FINISHED = 7
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0 Safari/537.36",
           "Referer": "https://www.varzesh3.com/", "Accept": "application/json"}


def _log(msg):
    print(f"SPORTS RESULTS: {msg}", flush=True)


def _start(m):
    try:
        return datetime.fromisoformat(str(m.get("scheduledStartOn")).replace("Z", "+00:00")).astimezone(TEHRAN)
    except Exception:
        return None


def remember(state, day, data, rows):
    """Store the matches the morning board actually showed (id, sport, teams, time)."""
    wanted = {(r["host"], r["guest"], r["start"].isoformat()) for r in rows}
    leagues = {lg.get("id"): lg for lg in data.get("leagues") or []}
    matches = []
    for m in data.get("matches") or []:
        start = _start(m)
        if start is None:
            continue
        key = (daily_sports._norm(m.get("hostName")), daily_sports._norm(m.get("guestName")), start.isoformat())
        if key not in wanted or not m.get("id"):
            continue
        row = next(r for r in rows if (r["host"], r["guest"], r["start"].isoformat()) == key)
        matches.append({
            "id": int(m["id"]), "sport_id": int(m.get("sport") or 1),
            "host": row["host"], "guest": row["guest"], "start": start.isoformat(),
            "time": row["time"], "league": row["league"], "stage": row.get("stage", ""),
            "sport": row["sport"], "iran": row["iran"],
            "league_full": daily_sports._norm((leagues.get(m.get("leagueId")) or {}).get("title", "")),
        })
    matches.sort(key=lambda x: x["start"])
    boards = dict(state.get("sports_boards") or {})
    boards[day] = {"matches": matches, "results_sent": False}
    state["sports_boards"] = {k: boards[k] for k in sorted(boards)[-KEEP_DAYS:]}
    return len(matches)


def fetch_match(match, session=None):
    s = session or requests
    kind = KINDS.get(int(match.get("sport_id") or 1), "football")
    r = s.get(MATCH_API.format(kind=kind, id=match["id"]), timeout=15, headers=HEADERS)
    r.raise_for_status()
    return r.json()


def _num(v):
    try:
        return int(str(v).strip())
    except Exception:
        return None


def parse_result(match, data):
    """-> dict(status, host_score, guest_score, pens) from the per-match API."""
    status = int(data.get("status") or 0)
    if int(match.get("sport_id") or 1) == 3:
        pts = data.get("points") or {}
    else:
        pts = data.get("goals") or {}
    pens = data.get("penalties") or {}
    h, g = _num(pts.get("host")), _num(pts.get("guest"))
    ph, pg = _num(pens.get("host")), _num(pens.get("guest"))
    return {"status": status, "h": h, "g": g,
            "pens": (ph, pg) if ph is not None and pg is not None and (ph or pg) else None}


def due(board, now):
    """Earliest moment the results card may be checked/sent for this board."""
    starts = [datetime.fromisoformat(m["start"]) for m in board.get("matches") or []]
    if not starts:
        return None, None
    first_day = min(starts).astimezone(TEHRAN)
    floor = first_day.replace(hour=RESULTS_HOUR, minute=0, second=0, microsecond=0)
    last = max(starts)
    return max(floor, last + MATCH_LENGTH), last + GIVE_UP_AFTER


def card_rows(board, results):
    rows = []
    for m in board["matches"]:
        res = results.get(m["id"])
        if not res or res["status"] != FINISHED or res["h"] is None or res["g"] is None:
            continue
        # Persian digits are laid out right-to-left on the card, so host-first puts the
        # host's number on the right, under the host's name.
        score = f"{res['h']} - {res['g']}"
        if res.get("pens"):
            score = f"({res['pens'][0]}-{res['pens'][1]}) " + score
        rows.append({**m, "start": datetime.fromisoformat(m["start"]), "finished": True, "live": False,
                     "score": score, "broadcast": "", "res": res})
    return rows


def _line(r, fa):
    res = r["res"]
    txt = f"{r['host']} {fa(res['h'])} - {fa(res['g'])} {r['guest']}"
    if res.get("pens"):
        txt += f" (پنالتی {fa(res['pens'][0])}-{fa(res['pens'][1])})"
    return txt


def caption(rows, jalali, fa):
    lines = [f"🏁 نتایج مسابقات مهم امروز | {fa(jalali)}", ""]
    iran = [r for r in rows if r.get("iran")]
    for r in iran[:4]:
        res = r["res"]
        side_h = "ایران" in r["host"]
        mine, other = (res["h"], res["g"]) if side_h else (res["g"], res["h"])
        mark = "✅" if mine > other else ("❌" if mine < other else "➖")
        if res.get("pens"):
            ph, pg = res["pens"]
            mark = "✅" if (ph > pg) == side_h else "❌"
        lines.append(f"🇮🇷 {mark} {_line(r, fa)} | {r['sport']}")
    if iran:
        lines.append("")
    others = [r for r in rows if not r.get("iran")]
    for r in others[:6]:
        lines.append(f"⚽️ {_line(r, fa)}" if r["sport"] == "فوتبال" else f"🏅 {_line(r, fa)}")
    if len(others) > 6:
        lines.append(f"… و {fa(len(others) - 6)} نتیجه دیگر در تصویر")
    lines += ["", "📢 @NabzKhabarOfficial"]
    return "\n".join(lines)


def pending(state, now):
    """Boards whose results are due now: list of (day, board, give_up)."""
    out = []
    for day, board in sorted((state.get("sports_boards") or {}).items()):
        if board.get("results_sent") or not board.get("matches"):
            continue
        ready, give_up = due(board, now)
        if ready and now >= ready:
            out.append((day, board, now >= give_up))
    return out
