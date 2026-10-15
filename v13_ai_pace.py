"""NABZ KHABAR: AI pacer (Oct 15 2026). Spread every free daily AI quota over the whole 24 hours.

Oct 14: the AI meter (v13_ai_extra) only RESTED a model after its daily quota was gone. Nothing
spread the quota over the day, so by ~23:00 Tehran it was all used (Gemini 3.5 flash-lite 560
calls, Groq's tokens-per-day full, OpenRouter's 50 free requests gone) and the night had no
editor: every new story was held for "no AI".

Now every AI request is counted per quota day, and a model may only use its share of the day so
far: budget x (hours since its quota reset + HEADROOM_H) / 24. Over its share, the request is not
sent at all: the caller gets a local 429 ("pace"), the pool moves on to the next model, and the
model gets its turn again later. Same free keys, no extra accounts or keys: we only ask less often.
Budgets sit a little under the real free limits seen on Oct 14 (env NABZ_PACE_<KEY> overrides,
0 = no pacing for that model). Counts live in ai_model_health.json under _ai_pace.

Oct 15 (day review):
* Groq's limit is 200k TOKENS a day per model, and one call costs ~2,000 tokens: both Groq models
  hit 199k at ~100 calls by 15:30 Tehran, so a budget of 170 calls never held them back and they
  were gone for the evening. Groq budgets are now 95 calls (fits the token limit).
* A local pace hold was treated by the router as a real provider 429, so the held model also
  got a 10-minute cooldown (Oct 15 12:20 UTC: 10 of 18 models "disabled", 5 stories held for
  "no AI" while the pacer would already have allowed some). A hold now never starts a cooldown
  (_install_no_cooldown wraps v13_ai_router._mark_model_failure at load()).
"""

import os
import re
import time

PACE_KEY = "_ai_pace"
HEADROOM_H = 2.0
BUDGETS = {
    "gemini:gemini-3.5-flash-lite": 450,
    "gemini:gemini-3.1-flash-lite": 250,
    "groq:openai/gpt-oss-120b": 95,   # 200k tokens/day at ~2k tokens a call
    "groq:openai/gpt-oss-20b": 95,
    "openrouter:*": 45,   # OpenRouter's 50 free requests a day are for the whole account
}
PACE_TEXT = ('{"error":{"message":"NabzKhabar local pace limit: this model has used its share of '
             'the quota so far today; it gets more later"}}')
_base = {}     # pace key -> {"day": id, "n": count saved by earlier runs}
_delta = {}    # pace key -> {"day": id, "n": requests in this run}
_held = {}     # pace key -> requests held back in this run
_held_at = {}  # health key -> time of its last local hold (consumed by was_held)


def _pace_key(hkey):
    if hkey.startswith("openrouter:"):
        return "openrouter:*"
    return hkey


def _pace_day(pkey, now=None):
    """(quota day id, seconds since that quota day started). Gemini resets at midnight Pacific,
    Groq (rolling 24 h) and OpenRouter at midnight UTC."""
    now = time.time() if now is None else now
    if pkey.startswith("gemini:"):
        try:
            from datetime import datetime
            from zoneinfo import ZoneInfo
            local = datetime.fromtimestamp(now, ZoneInfo("America/Los_Angeles"))
            start = local.replace(hour=0, minute=0, second=0, microsecond=0)
            return local.strftime("%Y-%m-%d"), now - start.timestamp()
        except Exception:
            pass
    return time.strftime("%Y-%m-%d", time.gmtime(now)), now % 86400


def _pace_budget(pkey):
    env = "NABZ_PACE_" + re.sub(r"[^A-Z0-9]+", "_", pkey.upper()).strip("_")
    try:
        return int(os.getenv(env, "") or BUDGETS.get(pkey, 0))
    except Exception:
        return BUDGETS.get(pkey, 0)


def _pace_used(pkey, day):
    base = _base.get(pkey) or {}
    delta = _delta.get(pkey) or {}
    return (int(base.get("n", 0) or 0) if base.get("day") == day else 0) + \
           (int(delta.get("n", 0) or 0) if delta.get("day") == day else 0)


def pace_allows(hkey, now=None):
    pkey = _pace_key(hkey)
    budget = _pace_budget(pkey)
    if budget <= 0:
        return True
    day, elapsed = _pace_day(pkey, now)
    share = budget * min(1.0, (elapsed / 3600.0 + HEADROOM_H) / 24.0)
    return _pace_used(pkey, day) < share


def pace_count(hkey, now=None):
    pkey = _pace_key(hkey)
    if _pace_budget(pkey) <= 0:
        return
    day, _ = _pace_day(pkey, now)
    row = _delta.get(pkey)
    if not row or row.get("day") != day:
        row = _delta[pkey] = {"day": day, "n": 0}
    row["n"] += 1


def was_held(hkey, within=60.0):
    """True (once) when this model's last request was held back locally just now."""
    t = _held_at.pop(str(hkey or ""), 0)
    return bool(t) and time.time() - t <= within


def _install_no_cooldown():
    """A local pace hold is not a provider failure: it must never start a router cooldown."""
    import v13_ai_router as r
    previous = r._mark_model_failure
    if getattr(previous, "_v13_pace_aware", False):
        return

    def mark(model, status):
        try:
            if int(status) == 429 and was_held(model):
                return
        except Exception:
            pass
        previous(model, status)

    mark._v13_pace_aware = True
    r._mark_model_failure = mark


def load():
    """Counts saved by earlier runs. A quota day with no pace count yet (first run with the pacer)
    starts from the AI meter's count of the same UTC day, so a half-used quota is not re-spent."""
    try:
        _install_no_cooldown()
    except Exception as exc:
        print(f"V13 AI PACE: cooldown guard not installed ({type(exc).__name__})", flush=True)
    try:
        import v13_ai_router as r
        health = r._load_health()
        saved = health.get(PACE_KEY)
        if isinstance(saved, dict):
            _base.update({k: v for k, v in saved.items() if isinstance(v, dict)})
        usage = health.get("_ai_usage") if isinstance(health.get("_ai_usage"), dict) else {}
        today = time.strftime("%Y-%m-%d", time.gmtime())
        seed = {}
        for hkey, row in (usage.get(today) or {}).items():
            pkey = _pace_key(str(hkey))
            if pkey.startswith("gemini:") or pkey not in BUDGETS or not isinstance(row, dict):
                continue  # Gemini's quota day is Pacific, not UTC
            seed[pkey] = seed.get(pkey, 0) + int(row.get("ok", 0) or 0) + int(row.get("other", 0) or 0)  # a 429 used no quota
        for pkey, n in seed.items():
            if (_base.get(pkey) or {}).get("day") != today:
                _base[pkey] = {"day": today, "n": n}
    except Exception as exc:
        print(f"V13 AI PACE: load warning ({type(exc).__name__})", flush=True)


def save(health):
    saved = health.get(PACE_KEY) if isinstance(health.get(PACE_KEY), dict) else {}
    for pkey, row in _delta.items():
        old = saved.get(pkey) if isinstance(saved.get(pkey), dict) else {}
        if old.get("day") != row["day"]:
            old = _base.get(pkey) or {}  # first run of the day: start from the meter's seed
        n = int(old.get("n", 0) or 0) if old.get("day") == row["day"] else 0
        saved[pkey] = {"day": row["day"], "n": n + int(row["n"])}
    for pkey, row in _base.items():  # seeds of models not called in this run are kept too
        if pkey not in saved:
            saved[pkey] = dict(row)
    health[PACE_KEY] = saved
    _delta.clear()


def _pace_response(url):
    import requests
    from requests.structures import CaseInsensitiveDict
    resp = requests.models.Response()
    resp.status_code = 429
    resp._content = PACE_TEXT.encode("utf-8")
    resp.encoding = "utf-8"
    resp.headers = CaseInsensitiveDict({"Content-Type": "application/json"})
    resp.url = str(url)
    resp.reason = "Local pace limit"
    resp._v13_local_pace = True
    return resp


def check(hkey, url):
    """None = send the request (it is counted); a local 429 response = held back."""
    if not hkey:
        return None
    if not pace_allows(hkey):
        pkey = _pace_key(hkey)
        if pkey not in _held:
            day, _ = _pace_day(pkey)
            print(f"V13 AI PACE: {pkey} used {_pace_used(pkey, day)}/{_pace_budget(pkey)} of today's quota "
                  "(more than its share so far); held back, the next model is asked", flush=True)
        _held[pkey] = _held.get(pkey, 0) + 1
        _held_at[str(hkey)] = time.time()
        return _pace_response(url)
    pace_count(hkey)
    return None


def pending():
    return bool(_delta)


def summary():
    return ", ".join(f"{k} held {v}x" for k, v in sorted(_held.items()))
