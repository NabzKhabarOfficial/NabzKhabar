"""NABZ V13 — final guard: the last check on every finished news post (Oct 9 2026).

Every cleanup layer (byline cleaner, neutral wording, text polish) tries to fix the text.
This guard does not fix anything: it looks at the finished title and sentences one last
time and refuses the post when an owner rule is still broken, so a gap in a cleaner can
never reach the channel:

* a media source is still named («به گزارش خبرگزاری ...»، «به نقل از رویترز»، «منبع: ...»,
  or a line whose subject is an outlet that "reported" something);
* loaded wording is still there («رژیم صهیونیستی»، «هلاکت»، «متجاوز»، «صهیونیست»).

A refused post is an editorial block (never a red run), exactly like the relevance gate's
broken-text blocks. Every refusal is logged in docs/guard_log.json (last 100, newest last)
with time, reason, the offending words and the title, so the daily review can see what the
cleaners missed and fix them at the source. Fail-safe: any error in the guard lets the post
through unchanged.

It also fixes one wrong drop on the way in (_install_lane_scope): a ship hit, seized or on fire
in Hormuz / the Persian Gulf / the Red Sea is never "foreign local" news.
"""

import json
import os
import re
import time
from datetime import datetime, timedelta, timezone

LOG_PATH = os.path.join("docs", "guard_log.json")
LOG_MAX = 100
TEHRAN = timezone(timedelta(hours=3, minutes=30))
_S = r"[\s\u200c]"
_P = "\u0600-\u06FF"

LOADED = re.compile(
    r"(?<![" + _P + r"])(?:رژیم" + _S + r"+صهیونیست\S*|رژیم" + _S + r"+اشغالگر|رژیم" + _S + r"+غاصب|"
    r"صهیونیست\S*|هلاکت|هلاک" + _S + r"+شد\S*|(?:ارتش|رژیم|دشمن|نظامیان)" + _S + r"+متجاوز|"
    r"متجاوز" + _S + r"+آمریکا\S*|متجاوزان" + _S + r"+آمریکایی|تجاوز" + _S + r"+نظامی)(?![" + _P + r"])")
# (a bare «متجاوز» is not refused: «بازداشت متجاوز جنسی» is ordinary crime news)
SOURCE_LINE = re.compile(r"(?:^|\n)\s*(?:🔗\s*)?منبع\s*[:：]")


def _media_patterns():
    import v13_byline_cleaner as bc
    via_media = re.compile(bc._VIA + r"\s*[^،,.!؟\n]{0,30}?" + bc._MEDIA)
    direct = re.compile(bc._VIA + r"\s*(?:مهر|فارس)\s*[،,]")
    return via_media, direct, bc._MEDIA_SUBJECT_RE, bc._REPORTING


def problems(title, sentences):
    """List of (reason, matched text) for a finished post; empty when it is clean."""
    found = []
    text = "\n".join([str(title or "")] + [str(s or "") for s in sentences or []])
    m = LOADED.search(text)
    if m:
        found.append(("loaded-wording", m.group(0)))
    if SOURCE_LINE.search(text):
        found.append(("source-line", "منبع:"))
    try:
        via_media, direct, subject, reporting = _media_patterns()
        for rx in (via_media, direct):
            m = rx.search(text)
            if m:
                found.append(("media-source", m.group(0)[:60]))
                break
        for s in sentences or []:
            s = str(s or "")
            if subject.search(s) and not s.lstrip().startswith("خبرنگار") and reporting.search(s):
                found.append(("media-source", s[:60]))
                break
    except Exception:
        pass
    return found


def _log(title, found):
    try:
        try:
            with open(LOG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
        items = data.get("blocked") if isinstance(data.get("blocked"), list) else []
        now = datetime.now(TEHRAN)
        items.append({"at": now.strftime("%Y-%m-%d %H:%M"), "reasons": [r for r, _ in found],
                      "matched": [t for _, t in found], "title": str(title or "")[:160]})
        data["blocked"] = items[-LOG_MAX:]
        today = now.strftime("%Y-%m-%d")
        data["today"] = {"date": today, "blocked": sum(1 for x in data["blocked"] if x["at"].startswith(today))}
        data["updated"] = int(time.time())
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    except Exception as exc:
        print(f"V13 FINAL GUARD: log skipped ({type(exc).__name__}).", flush=True)


# ---------------------------------------------------------------- shipping-lane scope fix
# Oct 9: «اصابت به یک کشتی غول پیکر در تنگه هرمز» was dropped as "foreign local" because the
# Hormuz exception in run_bot only knew words like حمله/موشک/پهپاد. A ship hit, seized, on fire
# or sunk in Iran's shipping lanes is never local news. Duplicates are still caught later by
# the dedup chain; this only stops the wrong "local" drop.
LANES = re.compile(r"(?:تنگه" + _S + r"*هرمز|خلیج" + _S + r"*فارس|دریای" + _S + r"*عمان|دریای" + _S + r"*سرخ|"
                   r"باب" + _S + r"*المندب|hormuz|persian gulf|gulf of oman|red sea|bab el-mandeb)", re.I)
LANE_EVENT = re.compile(r"(?:اصابت|توقیف|هدف" + _S + r"*قرار|انفجار|آتش" + _S + r"*سوزی|آتش" + _S + r"*گرفت|غرق|"
                        r"حمله|سرنگون|شلیک|ربوده|مین|کشتی|نفتکش|نفت" + _S + r"*کش|ناو|seiz|struck|hit|attack|"
                        r"explosion|tanker|vessel|ship)", re.I)


def _install_lane_scope():
    import v13_policy_guard as pg
    previous = pg._foreign_local_only
    if getattr(previous, "_lane_scope", False):
        return

    def lane_scope(candidate):
        try:
            text = " ".join(str(candidate.get(k, "") or "") for k in ("title", "summary", "description"))
            if LANES.search(text) and LANE_EVENT.search(text):
                return False
        except Exception:
            pass
        return previous(candidate)

    lane_scope._lane_scope = True
    pg._foreign_local_only = lane_scope


_INSTALLED = {"done": False}


def install():
    """Chain onto v13_relevance_gate.caption_problem, which v13_post_design calls on every
    finished caption and turns into an editorial block when it returns a reason."""
    if _INSTALLED["done"]:
        return
    import v13_relevance_gate as rg
    previous = rg.caption_problem

    def caption_problem(title, sentences):
        reason = previous(title, sentences)
        if reason:
            return reason
        try:
            found = problems(title, sentences)
        except Exception:
            return ""
        if not found:
            return ""
        _log(title, found)
        print("V13 FINAL GUARD: refused (" + ", ".join(f"{r}: {t}" for r, t in found) + ") -> "
              + str(title or "")[:120], flush=True)
        return "final-guard:" + found[0][0]

    rg.caption_problem = caption_problem
    try:
        _install_lane_scope()
    except Exception as exc:
        print(f"V13 FINAL GUARD: lane scope fix skipped ({type(exc).__name__}).", flush=True)
    _INSTALLED["done"] = True
    print("V13 FINAL GUARD ACTIVE: no post leaves with a media source or loaded wording.", flush=True)
