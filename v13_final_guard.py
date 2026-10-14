"""NABZ V13 — final guard: the last check on every finished news post (Oct 9 2026).

Every cleanup layer (byline cleaner, neutral wording, text polish) tries to fix the text.
This guard does not fix anything: it looks at the finished title and sentences one last
time and refuses the post when an owner rule is still broken, so a gap in a cleaner can
never reach the channel:

* a media source is still named («به گزارش خبرگزاری ...»، «به نقل از رویترز»، «منبع: ...»,
  or a line whose subject is an outlet that "reported" something);
* loaded wording is still there («رژیم صهیونیستی»، «هلاکت»، «متجاوز»، «صهیونیست»، «صهیونی»);
* website page chrome is still glued to the lead (section name + a «۰ نفر» counter + the
  headline repeated), or a line is a "related story" teaser such as «: دوباره جنگ می شود ؟»;
* the text is a chain of the site's related-video links (Oct 12: «ده ها اسرائیلی زخمی شدند
  + فیلم خبر مهم سخنگوی دولت ... + فیلم اعتراف مرشایمر ... + فیلم موزه ای ...»).

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

Oct 14 2026 (review of the published posts):
* «خبرنگاران شبکه فلسطین و اسکای نوز عربی ...» went out: the misspelling «اسکای نوز» was in no
  outlet list. Outlet names now accept common spelling variants, and a DETAIL line that names
  an outlet is dropped before the caption is built (_install_outlet_line_drop; the lead stays,
  so the story is still published, without the name).
* «آمریکایی-صهیونی» went out: «صهیونی» is now neutral wording («اسرائیلی», added to the byline
  cleaner's NEUTRAL table at install) and a leftover is refused here.
* The AI sense check refused a Trump post because the text wrote "Donald" instead of
  "Trump": a different name form of the same person is now explicitly ok.

Oct 14 2026, evening (root cause of loaded words that slipped through):
* Every word-edge check in the byline cleaner and in this guard was written as "not followed
  by a character in U+0600-U+06FF". That block also holds the Persian comma «،», semicolon
  «؛» and question mark «؟», so «رژیم صهیونیستی،» or «رویترز،» was neither rewritten nor
  refused. The edges now mean "not followed by a letter" (_letter_edges, applied at install to
  the cleaner's patterns and NEUTRAL table, and used by this guard's own patterns).
* New neutral wording: «قدس اشغالی» -> «بیت‌المقدس», «سرزمین‌های اشغالی» / «فلسطین اشغالی» ->
  «اسرائیل», «رژیم اسرائیل» -> «اسرائیل».
* Arabic letters «ي»/«ى»/«ك» («يسرائیل»، «آسيب») become Persian «ی»/«ک» before anything else.
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
# A "letter" for word edges: \w (all Unicode letters and digits) plus Arabic diacritics. Not the
# whole U+0600-U+06FF block, which also holds the Persian comma, semicolon and question mark.
_P = r"\w\u064B-\u065F\u0670"

LOADED = re.compile(
    r"(?<![" + _P + r"])(?:رژیم" + _S + r"+صهیونیست\S*|رژیم" + _S + r"+اشغالگر|رژیم" + _S + r"+غاصب|"
    r"صهیونیست\S*|صهیونی|هلاکت|هلاک" + _S + r"+شد\S*|(?:ارتش|رژیم|دشمن|نظامیان)" + _S + r"+متجاوز|"
    r"متجاوز" + _S + r"+آمریکا\S*|متجاوزان" + _S + r"+آمریکایی|تجاوز" + _S + r"+نظامی)(?![" + _P + r"])")
# (a bare «متجاوز» is not refused: «بازداشت متجاوز جنسی» is ordinary crime news)
# Named outlets (brands only; generic words like «رسانه» or «تلویزیون» stay allowed).
# Oct 14: spelling variants («اسکای نوز»، «فاکس نوز»، «بلومبرگ»/«بلومبرک»، «آسوشیتد پرس»، «اسکای‌نیوز»).
OUTLET_NAMES = re.compile(r"(?<![" + _P + r"])(?:بلومبر[گک]|رویترز|الحدث|الجزیره|العربیه|المیادین|اکسیوس|آکسیوس|"
                          r"آسوشیتد" + _S + r"*پرس|یورو" + _S + r"*نیوز|سی" + _S + r"*ان" + _S + r"*ان|بی" + _S + r"*بی" + _S + r"*سی|"
                          r"فرانس" + _S + r"+پرس|نیویورک" + _S + r"+تایمز|واشنگتن" + _S + r"+پست|"
                          r"وال" + _S + r"+استریت" + _S + r"+ژورنال|فایننشال" + _S + r"+تایمز|تایمز" + _S + r"+اسرائیل|"
                          r"گاردین|اسکای" + _S + r"*نی?وز|فاکس" + _S + r"*نی?وز|پولیتیکو|اکونومیست|اسپوتنیک|"
                          r"ایسنا|ایرنا|تسنیم|ایلنا|خبرگزاری" + _S + r"+\S+)(?![" + _P + r"])")
VICTIM = re.compile(r"(?:کشته|زخمی|مجروح|بازداشت|دستگیر|ربوده|شهید|ترور|اخراج|توقیف|تعطیل|فیلتر|محکوم|زندانی)")
SOURCE_LINE = re.compile(r"(?:^|\n)\s*(?:🔗\s*)?منبع\s*[:：]")
# A news site's "related videos" strip glued to the text: «... + فیلم <other story> + فیلم ...».
RELATED_LINK = re.compile(r"\+\s*(?:فیلم|ویدئو|ویدیو|عکس|تصاویر|اینفوگرافیک|صوت|فایل" + _S + r"+صوتی)(?![" + _P + r"])")

# Oct 14: loaded words the byline cleaner's NEUTRAL table did not know yet («آمریکایی-صهیونی»,
# «قدس اشغالی»، «جنوب سرزمین های اشغالی»). Added to that table at install time, so they are
# rewritten before this guard looks.
EXTRA_NEUTRAL = (
    ("صهیونی ها", "اسرائیلی‌ها"),
    ("صهیونی‌ها", "اسرائیلی‌ها"),
    ("صهیونی", "اسرائیلی"),
    ("قدس اشغالی", "بیت‌المقدس"),
    ("سرزمین های اشغالی", "اسرائیل"),
    ("فلسطین اشغالی", "اسرائیل"),
    ("رژیم اسرائیل", "اسرائیل"),
)
# Arabic letters from some sources («يسرائیل»، «آسيب»): Persian letters, applied first.
ARABIC_LETTERS = ((re.compile("[\u064a\u0649]"), "\u06cc"), (re.compile("\u0643"), "\u06a9"))
_OLD_EDGES = (r"[\w\u0600-\u06FF]", r"[\u0600-\u06FF]")
_NEW_EDGE = "[" + _P + "]"


def _letter_edges(rx):
    """The same pattern with its "not a Persian character" word edges turned into "not a
    letter" edges, so a word right before «،», «؛» or «؟» still matches."""
    p = rx.pattern
    for old in _OLD_EDGES:
        p = p.replace("(?<!" + old + ")", "(?<!" + _NEW_EDGE + ")").replace("(?!" + old + ")", "(?!" + _NEW_EDGE + ")")
    return rx if p == rx.pattern else re.compile(p, rx.flags)


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
    m = RELATED_LINK.search(text)
    if m:
        found.append(("related-links", text[max(0, m.start() - 30): m.end() + 30]))
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
    try:  # Oct 11: «پایگاه خبری تحلیلی انتخاب (Entekhab.ir) :»، «به گزارش انتخاب،»
        import v13_byline_cleaner as bc
        for rx in (bc._DOMAIN, bc._ANY_VIA, bc._SITE_LEAD):
            m = rx.search(text) if rx is not bc._SITE_LEAD else next(
                (rx.match(x) for x in [str(title or "")] + [str(y or "") for y in sentences or []] if rx.match(x)), None)
            if m:
                found.append(("media-source", m.group(0)[:60]))
                break
        for x in [str(y or "") for y in sentences or []]:
            w = bc._WIDGET.search(x)
            if w:
                found.append(("page-widget", w.group(0)[:60]))
                break
        body = " ".join(str(y or "") for y in sentences or [])
        if body.count("«") != body.count("»"):  # a quote cut in the middle («ممکن است.)
            found.append(("cut-quote", body[-60:]))
        sents = [str(y or "") for y in sentences or []]
        if sents and len(bc._keys(title)) >= 3 and len(bc._keys(sents[0]) & bc._keys(title)) < 2:
            found.append(("off-topic-lead", sents[0][:60]))
        t = str(title or "").strip()
        last = t.split()[-1] if t else ""
        if len(t) >= 165 and len(last) <= 2 and last not in ("او", "ما", "شد", "را"):  # «... با حوثی ها در ار»
            found.append(("cut-title", t[-30:]))
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
        entry = {"at": now.strftime("%Y-%m-%d %H:%M"), "reasons": [r for r, _ in found],
                 "matched": [t for _, t in found], "title": str(title or "")[:160]}
        if items and all(items[-1].get(k) == entry[k] for k in ("at", "reasons", "title")):
            return  # the same refusal twice in one minute (retry of the same candidate)
        items.append(entry)
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


# ---------------------------------------------------------------- Oct 14: fix at the source
def _install_extra_neutral():
    """Letter word edges for the byline cleaner's patterns and NEUTRAL table, EXTRA_NEUTRAL
    added to that table, and Arabic letters made Persian first (neutral() reads the table at
    call time, the cleaner's functions read their patterns at call time)."""
    import v13_byline_cleaner as bc
    if getattr(bc, "_edges_fixed", False):
        return
    bc._NEUTRAL[:] = [(_letter_edges(p), b) for p, b in bc._NEUTRAL]
    have = {p.pattern for p, _ in bc._NEUTRAL}
    for a, b in EXTRA_NEUTRAL:
        pat = _letter_edges(bc._phrase_re(a))
        if pat.pattern not in have:
            bc._NEUTRAL.append((pat, b))
            have.add(pat.pattern)
    bc._NEUTRAL[0:0] = list(ARABIC_LETTERS)
    fixed = 0
    for name in list(vars(bc)):
        value = getattr(bc, name)
        if isinstance(value, re.Pattern):
            new = _letter_edges(value)
            if new is not value:
                setattr(bc, name, new)
                fixed += 1
    bc._edges_fixed = True
    print(f"V13 FINAL GUARD: letter word edges on {fixed} cleaner patterns and the neutral table.", flush=True)


def _install_outlet_line_drop():
    """A detail line that names an outlet is dropped before the caption is built (the lead is
    always kept). bc.install's wrapper looks strip_media up at call time, so this applies."""
    import v13_byline_cleaner as bc
    previous = bc.strip_media
    if getattr(previous, "_outlet_drop", False):
        return

    def strip_media(text):
        out = previous(text)
        try:
            sents = bc._split_sentences(out)
            if len(sents) < 2:
                return out
            kept = [sents[0]] + [s for s in sents[1:] if not OUTLET_NAMES.search(s)]
            if len(kept) != len(sents):
                print(f"V13 FINAL GUARD: dropped {len(sents) - len(kept)} detail line(s) naming an outlet.", flush=True)
            return " ".join(kept)
        except Exception:
            return out

    strip_media._outlet_drop = True
    bc.strip_media = strip_media


# ---------------------------------------------------------------- AI sense check
COHERENCE_PROMPT = """You check a Persian Telegram news post right before it is published.

HEADLINE: %s

TEXT: %s

Answer one question: can a reader understand this post without being confused?
- "contradiction": the text says the opposite of the headline, or two sentences of the
  text say opposite things about the same fact (e.g. "X did not ask for Y" and then
  "X specifically asked for Y").
- "garbled": broken or cut-off sentences, words glued together, leftover website
  text (e.g. a list of other stories' headlines), so the meaning is unclear.
- "ok": clear and consistent. Different numbers from different officials, a denial
  quoted next to a claim, or "A said X, B said not X" is ok: that is normal reporting.
  A different name form or spelling of the same person or place (first name vs family
  name, a title instead of the name, two transliterations) is ok, never a contradiction.

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
    for fix in (_install_extra_neutral, _install_outlet_line_drop):
        try:
            fix()
        except Exception as exc:
            print(f"V13 FINAL GUARD: {fix.__name__} skipped ({type(exc).__name__}: {exc}).", flush=True)
    try:  # Oct 12: links, section breadcrumb and the repeated headline before the lead; whole-word tags
        import v13_chrome_scrub
        v13_chrome_scrub.install()
    except Exception as exc:
        print(f"V13 CHROME SCRUB: not installed ({type(exc).__name__}: {exc})", flush=True)
    _INSTALLED["done"] = True
    print("V13 FINAL GUARD ACTIVE: no post leaves with a media source or loaded wording.", flush=True)
