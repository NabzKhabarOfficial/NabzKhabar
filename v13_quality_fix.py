"""NABZ KHABAR: quality fixes from the Oct 17 review of every post published that day (13:40 Tehran).

* Loaded wording still went out: «سوختن در آتش اعتماد به ارتش تروریست آمریکا»، «بیش از ۳۴۰ کودک را به
  شهادت رسانده». Every AI translation / rewrite now gets neutral wording (ارتش تروریست آمریکا -> ارتش آمریکا,
  به شهادت رساند -> کشت, به شهادت رسیدند / شهید شدند -> کشته شدند), and a post that still calls an army or a
  country "terrorist" is refused by the final guard ("loaded-wording").
* A lead starting with «در حالی که ...» (a dangling clause, the headline's subject missing) is refused like
  «این در حالی است که» ("dangling-lead").
* The same headline went out twice, 30 minutes apart («هشدار سرپرست وزارت دفاع به آمریکا درباره تأثیر قدرت
  موشکی ایران»): the same-event judge now calls it a repeat without asking any AI when every meaningful word of
  a published headline (5+ words) is in the new headline and it adds at most 2 words (an update adds more).
Any error = the bot runs as before.
"""

import re

NEUTRAL = (
    (re.compile(r"ارتش\s+(?:تروریست(?:ی)?|تروریستی)\s+(آمریکا|اسرائیل|ایالات\s+متحده)"), r"ارتش \1"),
    (re.compile(r"(آمریکا|اسرائیل)ی?\s+تروریست(?![\u0600-\u06FF])"), r"\1"),
    (re.compile(r"به\s+شهادت\s+رسانده"), "کشته"),
    (re.compile(r"به\s+شهادت\s+رساندند"), "کشتند"),
    (re.compile(r"به\s+شهادت\s+رساند"), "کشت"),
    (re.compile(r"به\s+شهادت\s+رسیدند"), "کشته شدند"),
    (re.compile(r"به\s+شهادت\s+رسید"), "کشته شد"),
    (re.compile(r"شهید\s+شدند"), "کشته شدند"),
)
LOADED = re.compile(r"ارتش\s+تروریست|تروریست(?:ی)?\s+(?:آمریکا|اسرائیل)|(?:آمریکا|اسرائیل)ی?\s+تروریست(?![\u0600-\u06FF])")
DANGLING = re.compile(r"^\s*در\s+حالی\s+که\s")
MIN_WORDS = 5
_DONE = {"v": False}


def neutral(text):
    text = str(text or "")
    for rx, good in NEUTRAL:
        text = rx.sub(good, text)
    return text


def _install_router():
    import v13_ai_router as r
    prev = r._validate
    if getattr(prev, "_v13_neutral", False):
        return

    def validate(main, original_title, source, data, foreign):
        if isinstance(data, dict):
            data = dict(data)
            for k in ("title", "summary"):
                data[k] = neutral(data.get(k, ""))
        return prev(main, original_title, source, data, foreign)

    validate._v13_neutral = True
    r._validate = validate


def _install_guard():
    import v13_relevance_gate as rg
    import v13_final_guard as fg
    prev = rg.caption_problem
    if getattr(prev, "_v13_quality", False):
        return

    def caption_problem(title, sentences):
        reason = prev(title, sentences)
        if reason:
            return reason
        try:
            if fg._BOARD.search(str(title or "")):
                return ""
            sents = [str(x or "") for x in sentences or []]
            found = []
            m = LOADED.search(" ".join([str(title or "")] + sents))
            if m:
                found.append(("loaded-wording", m.group(0)))
            if sents and DANGLING.search(sents[0]):
                found.append(("dangling-lead", sents[0][:60]))
        except Exception:
            return ""
        if not found:
            return ""
        fg._log(title, found)
        print("V13 FINAL GUARD: refused (" + ", ".join(f"{a}: {b}" for a, b in found) + f") -> {str(title or '')[:120]}",
              flush=True)
        return "final-guard:" + found[0][0]

    caption_problem._v13_quality = True
    rg.caption_problem = caption_problem


def same_headline(ej, prompt):
    """Item number of a published headline whose meaningful words are all in the new post, else 0."""
    try:
        head = prompt.split("NEW POST (about to be published):", 1)[1].split("ALREADY PUBLISHED", 1)[0].strip()
        listing = prompt.split("ALREADY PUBLISHED in the last 24 hours:", 1)[1].split("Does the NEW POST", 1)[0]
        dd = ej._dd()
        common = getattr(dd, "COMMON", set())
        first = head.splitlines()[0] if head.splitlines() else head
        hf = set(dd.fingerprint(first)) - set(common)
        for line in listing.splitlines():
            m = re.match(r"^\s*(\d+)\.\s*(.+)$", line)
            if not m:
                continue
            tf = set(dd.fingerprint(m.group(2))) - set(common)
            if len(tf) >= MIN_WORDS and tf <= hf and len(hf - tf) <= 2:  # a real update adds words
                return int(m.group(1))
    except Exception:
        return 0
    return 0


def _install_judge():
    import v13_event_judge as ej
    prev = ej.ask
    if getattr(prev, "_v13_same_headline", False):
        return

    def ask(prompt, skip=""):
        text = str(prompt or "")
        if text.startswith("You are the duplicate checker"):
            n = same_headline(ej, text)
            if n:
                return {"verdict": "repeat", "match": n, "why": "same headline words (rule)", "model": "rule/same-headline"}
        return prev(prompt, skip=skip)

    ask._v13_same_headline = True
    ej.ask = ask


def install():
    if _DONE["v"]:
        return
    for fix in (_install_router, _install_guard, _install_judge):
        try:
            fix()
        except Exception as exc:
            print(f"V13 QUALITY FIX: {fix.__name__} not installed ({type(exc).__name__}: {exc})", flush=True)
    _DONE["v"] = True
    print("V13 QUALITY FIX ACTIVE: neutral wording, dangling «در حالی که» leads, same-headline repeats", flush=True)
