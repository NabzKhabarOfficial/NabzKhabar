"""NABZ V13 — final guard: the last check on every finished news post (Oct 9 2026).

Every cleanup layer (byline cleaner, neutral wording, text polish) tries to fix the text.
This guard does not fix anything: it looks at the finished title and sentences one last
time and refuses the post when an owner rule is still broken, so a gap in a cleaner can
never reach the channel:

* a media source is still named («به گزارش خبرگزاری ...»، «به نقل از رویترز»، «منبع: ...»,
  or a line whose subject is an outlet that "reported" something);
* loaded wording is still there («رژیم صهیونیستی»، «هلاکت»، «متجاوز»، «صهیونیست»);
* website page chrome is still glued to the lead (section name + a «۰ نفر» counter + the
  headline repeated), or a line is a "related story" teaser such as «: دوباره جنگ می شود ؟».

A refused post is an editorial block (never a red run), exactly like the relevance gate's
broken-text blocks. Every refusal is logged in docs/guard_log.json (last 100, newest last)
with time, reason, the offending words and the title, so the daily review can see what the
cleaners missed and fix them at the source. Fail-safe: any error in the guard lets the post
through unchanged.

Last, an AI sense check (coherence, Oct 10): a free model reads the finished headline and text
and says whether the text contradicts the headline or itself, or is garbled (Oct 10: «آمریکا از
اسرائیل نخواسته ...» followed by «بلکه مشخصاً خواستار حمله اسرائیل بودند»). A flag needs a
second model to agree before the post is refused, so no news is lost to one model's mistake;
if no model answers, the post goes out (the rule checks above have already run).

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
# Named outlets (brands only; generic words like «رسانه» or «تلویزیون» stay allowed).
OUTLET_NAMES = re.compile(r"(?<![" + _P + r"])(?:بلومبرگ|رویترز|الحدث|الجزیره|العربیه|المیادین|اکسیوس|آکسیوس|"
                          r"آسوشیتدپرس|یورونیوز|سی" + _S + r"*ان" + _S + r"*ان|بی" + _S + r"*بی" + _S + r"*سی|"
                          r"فرانس" + _S + r"+پرس|نیویورک" + _S + r"+تایمز|واشنگتن" + _S + r"+پست|"
                          r"وال" + _S + r"+استریت" + _S + r"+ژورنال|فایننشال" + _S + r"+تایمز|تایمز" + _S + r"+اسرائیل|"
                          r"گاردین|اسکای" + _S + r"+نیوز|فاکس" + _S + r"+نیوز|پولیتیکو|اکونومیست|اسپوتنیک|"
                          r"ایسنا|ایرنا|تسنیم|ایلنا|خبرگزاری" + _S + r"+\S+)(?![" + _P + r"])")
VICTIM = re.compile(r"(?:کشته|زخمی|مجروح|بازداشت|دستگیر|ربوده|شهید|ترور|اخراج|توقیف|تعطیل|فیلتر|محکوم|زندانی)")
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
        import v13_byline_cleaner as bc
        sents = [str(x or "") for x in sentences or []]
        if sents and bc.strip_echo(sents[0] + " " + " ".join(sents[1:3]), title) != sents[0] + " " + " ".join(sents[1:3]):
            found.append(("page-chrome", sents[0][:60]))
        for x in sents:
            if bc._TEASER.search(x):
                found.append(("teaser-fragment", x[:60]))
                break
    except Exception:
        pass
    try:
        import v13_byline_cleaner as bc
        sents = [str(x or "") for x in sentences or []]
        head = " ".join(sents[:2])[:400]
        if bc.PUBLISHED_RE.search(head) or bc.DATE_TIME_RE.search(head) or re.search(r"\s>>\s", head):
            found.append(("page-chrome", head[:60]))
        # Owner rule: no outlet or reporter of an outlet anywhere (Oct 10: «خبرنگار آکسیوس»).
        reporter = re.compile(r"خبرنگار" + _S + r"*(?:ان)?" + _S + r"+[^،,.!؟:\n]{0,15}?(?:" + bc._MEDIA + r")")
        for rx in (OUTLET_NAMES, reporter):
            for m in rx.finditer(text):
                around = text[max(0, m.start() - 40): m.end() + 40]
                if VICTIM.search(around):  # «خبرنگار الجزیره کشته شد» is the news itself
                    continue
                found.append(("media-source", m.group(0)[:60]))
                break
            if found and found[-1][0] == "media-source":
                break
    except Exception:
        pass
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


# ---------------------------------------------------------------- AI sense check
COHERENCE_PROMPT = """You check a Persian Telegram news post right before it is published.

HEADLINE: %s

TEXT: %s

Answer one question: can a reader understand this post without being confused?
- "contradiction": the text says the opposite of the headline, or two sentences of the
  text say opposite things about the same fact (e.g. "X did not ask for Y" and then
  "X specifically asked for Y").
- "garbled": broken or cut-off sentences, words glued together, leftover website
  text, so the meaning is unclear.
- "ok": clear and consistent. Different numbers from different officials, a denial
  quoted next to a claim, or "A said X, B said not X" is ok: that is normal reporting.

Answer ONLY JSON: {"verdict":"ok|contradiction|garbled","why":"<max 12 words>"}"""
_BOARD = re.compile(r"نبض" + _S + r"*آموزش|هواشناسی|پیش" + _S + r"*بینی" + _S + r"*هوا|قیمت|برنامه" + _S + r"+(?:بازی|مسابقات)|"
                    r"مهم" + _S + r"*ترین" + _S + r"+خبرهای" + _S + r"+امروز|نتایج|جدول")
_BAD = ("contradiction", "garbled")


def coherence(title, sentences):
    """("ai-contradiction" | "ai-garbled", why) when two free models agree the post is
    confusing, else None. Never raises."""
    try:
        text = " ".join(str(s or "") for s in sentences or []).strip()
        title = str(title or "").strip()
        if len(text.split()) < 12 or len(title) < 12 or _BOARD.search(title):
            return None
        import v13_event_judge as ej
        prompt = COHERENCE_PROMPT % (title[:200], text[:900])
        first = ej.ask(prompt)
        kind = str((first or {}).get("verdict", "")).strip().lower()
        if kind not in _BAD:
            return None
        second = ej.ask(prompt, skip=(first or {}).get("model", ""))
        kind2 = str((second or {}).get("verdict", "")).strip().lower()
        if kind2 not in _BAD:
            print(f"V13 FINAL GUARD: AI sense check: one model said {kind}, the second did not; allowed.", flush=True)
            return None
        return ("ai-" + kind, str(first.get("why", ""))[:80] + " | " + str(first.get("model", "")))
    except Exception as exc:
        print(f"V13 FINAL GUARD: AI sense check skipped ({type(exc).__name__}).", flush=True)
        return None


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
        if not found and os.getenv("NABZ_AI_SENSE_CHECK", "1") != "0":
            flag = coherence(title, sentences)
            if flag:
                found = [flag]
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
