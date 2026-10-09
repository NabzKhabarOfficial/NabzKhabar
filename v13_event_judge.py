"""NABZ V13 — AI same-event judge (Oct 2026).

Root cause of the repeats (Erbil drone strike x3, Kramatorsk bus strike x3):
every rule-based guard compares *words*. Several outlets retell one event with
different words, angles and casualty figures, often first in English, so word
rules always leave a gap.

This layer is the last check before anything is posted. It shows a free AI
model the final Persian headline + lead and every headline the channel posted
in the last 24 hours, and asks one question: is this the same real-world
event? Only a clear "repeat" is blocked. Genuine developments stay allowed
(owner's rule): a different actor's reaction, a claim of responsibility,
arrests, an official result, a clearly higher toll announced as an update.

* Runs only after the word/place guards found nothing, and only for a post
  that is about to go out, so it costs one or two free calls per run.
* Free providers only: Groq, then Gemini flash-lite.
* Fail-safe: if every provider fails, the older guards have already run.
* Every verdict is logged to ai_model_health.json (_event_judge_log).
"""

import hashlib
import json
import os
import re
import time

WINDOW = 24 * 3600
MAX_PUBLISHED = 45
BUDGET_SECONDS = 25
HTTP_TIMEOUT = 10
LOG_KEY = "_event_judge_log"
LOG_ITEMS = 60
SOURCES = ("_daily_items", "_published_heads", "_published_incidents", "_published_stories")

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELS = ("openai/gpt-oss-120b", "openai/gpt-oss-20b")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent"
GEMINI_MODELS = ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite")

PROMPT = """You are the duplicate checker of a Persian Telegram news channel.
The channel must NEVER post the same news event twice.

NEW POST (about to be published):
%s

ALREADY PUBLISHED in the last 24 hours:
%s

Does the NEW POST report the same real-world event as one of the published items,
even with different wording, angle, language, source or casualty figures?

- "repeat": the same specific incident / attack / accident / decision / statement /
  report, retold, summarized, re-framed (e.g. "part of a wave of attacks") or with
  slightly different numbers. The same person's same statement again is a repeat.
- "update": the same incident with a genuinely new development: a clearly higher
  official toll announced as an update, a claim of responsibility, arrests, an
  official investigation result.
- "reaction": a DIFFERENT actor's reaction, condemnation or statement about a
  published event.
- "new": a different event. A new strike on another day, in another place, or a new
  wave of attacks is new. Ongoing topics (Hormuz, Gaza, Ukraine, Yemen war) are not
  repeats by themselves; only the same specific happening is.

Answer ONLY JSON: {"verdict":"repeat|update|reaction|new","match":<published item number or 0>,"why":"<max 12 words>"}"""

_LIST_LINE = re.compile(r"^\s*(?:[0-9۰-۹]+[\.\)]\s|[0-9]\ufe0f?\u20e3)")
# Daily boards (weather, cars, sports, lessons) are new every day by design.
_BOARD = re.compile(r"نبض آموزش|هواشناسی|پیش ?بینی هوا|قیمت (?:روز )?خودرو|برنامه (?:بازی|مسابقات)|مهم ?ترین خبرهای امروز")


def _dd():
    import v13_story_dedup as dd
    return dd


def _head(caption):
    try:
        import v13_incident_dedup as inc
        return inc._head(caption)
    except Exception:
        return _dd().story_text(caption)[:300]


def _is_list_post(caption):
    """Digests and boards list many items; they are not single news posts."""
    lines = [l for l in str(caption or "").splitlines() if l.strip()]
    return sum(1 for l in lines if _LIST_LINE.match(l)) >= 3


def published(health, now=None):
    """Headlines posted in the last WINDOW seconds, newest first, near-identical ones merged."""
    now = now or time.time()
    dd = _dd()
    rows = []
    for key in SOURCES:
        for x in health.get(key) or []:
            if not isinstance(x, dict):
                continue
            title = re.sub(r"\s+", " ", str(x.get("title", "") or "")).strip()
            t = float(x.get("t", 0) or 0)
            if len(title) >= 12 and now - t <= WINDOW and not _BOARD.search(title):
                rows.append((t, title[:110]))
    rows.sort(key=lambda r: -r[0])
    out, seen = [], []
    for t, title in rows:
        fp = dd.fingerprint(title)
        if any(fp and (fp <= s or s <= fp) for s in seen):
            continue
        seen.append(fp)
        out.append({"t": t, "title": title})
        if len(out) >= MAX_PUBLISHED:
            break
    return out


def _post(url, **kw):
    import requests
    return requests.post(url, timeout=HTTP_TIMEOUT, **kw)


def _parse(raw):
    try:
        import v13_ai_router
        return v13_ai_router._clean_json(raw)
    except Exception:
        m = re.search(r"\{.*\}", str(raw or ""), re.S)
        return json.loads(m.group(0)) if m else None


def ask(prompt, skip=""):
    """One verdict from the free pool, or None. `skip` = a model already asked."""
    deadline = time.monotonic() + BUDGET_SECONDS
    groq = os.getenv("GROQ_API_KEY", "").strip()
    gem = os.getenv("AI_API_KEY", "").strip()
    if groq:
        for model in GROQ_MODELS:
            if f"groq/{model}" == skip:
                continue
            if time.monotonic() >= deadline:
                return None
            try:
                r = _post(GROQ_URL, headers={"Authorization": f"Bearer {groq}",
                                             "Content-Type": "application/json"},
                          json={"model": model, "temperature": 0, "max_tokens": 400,
                                "include_reasoning": False,
                                "response_format": {"type": "json_object"},
                                "messages": [{"role": "user", "content": prompt}]})
                if r.ok:
                    data = _parse(r.json()["choices"][0]["message"]["content"])
                    if isinstance(data, dict) and data.get("verdict"):
                        return dict(data, model=f"groq/{model}")
                print(f"V13 EVENT JUDGE: groq/{model} HTTP {r.status_code}.", flush=True)
            except Exception as exc:
                print(f"V13 EVENT JUDGE: groq/{model} error ({type(exc).__name__}).", flush=True)
    if gem:
        for model in GEMINI_MODELS:
            if f"gemini/{model}" == skip:
                continue
            if time.monotonic() >= deadline:
                return None
            try:
                r = _post(GEMINI_URL % model, params={"key": gem},
                          json={"contents": [{"parts": [{"text": prompt}]}],
                                "generationConfig": {"responseMimeType": "application/json",
                                                     "temperature": 0, "maxOutputTokens": 300}})
                if r.ok:
                    raw = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                    data = _parse(raw)
                    if isinstance(data, dict) and data.get("verdict"):
                        return dict(data, model=f"gemini/{model}")
                print(f"V13 EVENT JUDGE: gemini/{model} HTTP {r.status_code}.", flush=True)
            except Exception as exc:
                print(f"V13 EVENT JUDGE: gemini/{model} error ({type(exc).__name__}).", flush=True)
    return None


def related(head, title):
    """Cheap sanity check: do the two headlines share the event or several words?"""
    try:
        import v13_incident_dedup as inc
        if inc.match_strength(inc.signature(head), inc.signature(title)):
            return True
    except Exception:
        pass
    dd = _dd()
    shared = (dd.fingerprint(head) & dd.fingerprint(title)) - dd.COMMON
    return len(shared) >= 3


def _is_repeat(verdict):
    return str((verdict or {}).get("verdict", "")).strip().lower() in ("repeat", "duplicate", "same")


def _log(health, entry):
    log = health.get(LOG_KEY)
    if not isinstance(log, list):
        log = []
    log.append(entry)
    health[LOG_KEY] = log[-LOG_ITEMS:]


def judge(caption):
    """Return the earlier published item when the AI says this is a repeat, else None."""
    if _is_list_post(caption) or _BOARD.search(str(caption or "")):
        return None
    head = _head(caption).strip()
    if len(head) < 12:
        return None
    router, health = _dd()._health()
    items = published(health)
    if not items:
        return None
    listing = "\n".join(f"{i}. {x['title']}" for i, x in enumerate(items, 1))
    verdict = ask(PROMPT % (head[:400], listing))
    entry = {"t": int(time.time()), "head": head[:110],
             "id": hashlib.sha1(head.encode("utf-8")).hexdigest()[:10]}
    if not verdict:
        entry["verdict"] = "unavailable"
        print("V13 EVENT JUDGE: no free model answered; earlier guards stand.", flush=True)
        _log(health, entry)
        router._save_health(health)
        return None
    kind = str(verdict.get("verdict", "")).strip().lower()
    try:
        n = int(str(verdict.get("match", 0)).strip() or 0)
    except Exception:
        n = 0
    match = items[n - 1] if 1 <= n <= len(items) else None
    entry.update({"verdict": kind, "match": match["title"] if match else "",
                  "why": str(verdict.get("why", ""))[:100], "model": verdict.get("model", "")})
    if _is_repeat(verdict) and match and not related(head, match["title"]):
        # No important news may be lost to one model's mistake: a "repeat" that
        # shares nothing visible with the earlier headline needs a second model.
        second = ask(PROMPT % (head[:400], listing), skip=entry["model"])
        entry["confirm"] = (second or {}).get("model", "none") + ":" + str((second or {}).get("verdict", "-"))
        if not _is_repeat(second):
            kind = "unconfirmed-repeat"
            entry["verdict"] = kind
    _log(health, entry)
    router._save_health(health)
    if kind in ("repeat", "duplicate", "same") and match:
        print(f"V13 EVENT JUDGE: repeat -> {head[:80]} | earlier: {match['title'][:80]} "
              f"({entry['why']})", flush=True)
        return {"title": match["title"], "t": match["t"], "kind": "ai_same_event"}
    print(f"V13 EVENT JUDGE: {kind or 'new'} -> allowed ({entry['why']}).", flush=True)
    return None


_INSTALLED = {"done": False}


def install():
    if _INSTALLED["done"]:
        return
    dd = _dd()
    inner = dd.find_duplicate

    def find_duplicate(caption):
        match = inner(caption)
        if match:
            return match
        try:
            return judge(caption)
        except Exception as exc:
            print(f"V13 EVENT JUDGE: skipped ({type(exc).__name__}: {exc}).", flush=True)
            return None

    dd.find_duplicate = find_duplicate
    _INSTALLED["done"] = True
    print("V13 EVENT JUDGE ACTIVE: AI compares every post with the last 24h of headlines.", flush=True)
