"""NABZ KHABAR: AI quota fix (Oct 14 2026). Free providers only, no quota tricks.

Root cause of the silent night of Oct 13: from 16:58Z every free model (Groq,
Gemini, OpenRouter) answered 429. The bot used far more AI than the free
quotas allow: the final editor judged up to 20 stories per run ONE BY ONE,
each call re-sending the long rubric, 144 runs a day; and once a daily quota
was used up, every model was retried every 10 minutes all night.

This launcher fixes that without touching the other files:
1. Batched editor verdicts: the uncached stories of a run are judged in one
   AI call (up to BATCH_SIZE per call) with the same rubric.
2. Cooldown-aware editor: a model in cooldown is skipped, and failures are
   recorded in the shared health file (same keys as the translation router).
3. Daily-quota rest: a 429 that says the DAILY quota is used up rests that
   model until its reset (Gemini: midnight Pacific) instead of 10 minutes.
4. Shorter translation input: article text sent for translation is capped.
5. A story blocked only because no AI was available (foreign or Persian) is
   an editorial block, not a "failed publication" (no Telegram request was
   made), and is held 20 minutes instead of 6 hours, so it is retried when
   AI is back.
6. AI meter: calls / ok / 429 per model per day (+ last error text) are saved
   in ai_model_health.json under _ai_usage, so quota use is measured.

Run with `python v13_ai_extra.py` (same as `python run_bot.py`, plus the above).
If any part fails to install, the bot runs exactly as before.
"""

import os
import re
import time

TRANSLATION_SOURCE_CHARS = 3500
AI_UNAVAILABLE_TTL_SECONDS = 20 * 60
BATCH_SIZE = 8
BATCH_BODY_CHARS = 300
BATCH_MAX_TOKENS = 1800
BATCH_BUDGET_SECONDS = 60
USAGE_KEY = "_ai_usage"
EVENTS_KEY = "_ai_extra_log"
USAGE_DAYS = 4
EVENTS_MAX = 40
AI_HOSTS = {
    "generativelanguage.googleapis.com": "gemini",
    "api.groq.com": "groq",
    "openrouter.ai": "openrouter",
}
DAILY_429 = re.compile(r"per[ _-]?day|perday|daily|\bTPD\b|\bRPD\b", re.I)
_daily_rest = {}   # health key -> unix time when its daily quota resets
_usage = {}        # health key -> counters for this run
_events = []       # short log of batch results and AI errors for this run
_no_ai_titles = set()  # stories whose rewrite failed only because no AI answered


def _event(text):
    _events.append({"t": int(time.time()), "e": str(text)[:300]})


def _short(resp, n=160):
    return re.sub(r"\s+", " ", str(getattr(resp, "text", "") or ""))[:n]


def _status_of(exc):
    found = re.search(r"HTTP (\d{3})", str(exc))
    return int(found.group(1)) if found else 599


# --------------------------------------------------------------------------
# 1) Translation router: shorter input
# --------------------------------------------------------------------------
def install_router():
    import v13_ai_router as r
    if getattr(r, "_v13_ai_extra", False):
        return
    original_request = r.gemini_request

    def gemini_request(main, title, article_text):
        text = str(article_text or "")
        result = original_request(main, title, text[:TRANSLATION_SOURCE_CHARS] if text else article_text)
        if result is None and title:
            _no_ai_titles.add(str(title))
        return result

    r.gemini_request = gemini_request
    r._v13_ai_extra = True
    print(f"V13 AI EXTRA: translation input capped at {TRANSLATION_SOURCE_CHARS} chars", flush=True)


# --------------------------------------------------------------------------
# 2) Editor: cooldown-aware pool (Groq -> Gemini -> OpenRouter, as before)
# --------------------------------------------------------------------------
def _oa_raw(session, url, key, model, prompt, max_tokens, extra=None, timeout=15):
    payload = {"model": model, "temperature": 0, "max_tokens": max_tokens,
               "messages": [{"role": "user", "content": prompt}],
               "response_format": {"type": "json_object"}}
    payload.update(extra or {})
    resp = session.post(url, timeout=timeout, json=payload,
                        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                 "User-Agent": "NabzKhabar-EditorGate/1.0"})
    if not resp.ok:
        raise RuntimeError(f"HTTP {resp.status_code}: {_short(resp)}")
    content = (resp.json().get("choices") or [{}])[0].get("message", {}).get("content", "")
    if isinstance(content, list):
        content = "".join(str(x.get("text", "")) if isinstance(x, dict) else str(x) for x in content)
    return str(content or "")


def _attempts(main, session, prompt, max_tokens, timeout):
    import v13_editor_gate as g
    groq = os.getenv("GROQ_API_KEY", "").strip()
    gem = str(getattr(main, "AI_API_KEY", "") or os.getenv("AI_API_KEY", "")).strip()
    orouter = os.getenv("OPENROUTER_API_KEY", "").strip()
    out = []  # (label, health key, call -> raw text)
    if groq:
        for m in g.GROQ_MODELS:
            out.append(("groq/" + m, "groq:" + m, lambda m=m: _oa_raw(
                session, "https://api.groq.com/openai/v1/chat/completions", groq, m, prompt, max_tokens,
                {"include_reasoning": False}, timeout=timeout)))
    if gem:
        def _gemini(m):
            resp = session.post(f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent",
                                params={"key": gem}, timeout=timeout,
                                json={"contents": [{"parts": [{"text": prompt}]}],
                                      "generationConfig": {"responseMimeType": "application/json", "temperature": 0}})
            if not resp.ok:
                raise RuntimeError(f"HTTP {resp.status_code}: {_short(resp)}")
            parts = ((resp.json().get("candidates") or [{}])[0].get("content") or {}).get("parts") or [{}]
            return str(parts[0].get("text", "") or "")
        for m in g.GEMINI_MODELS:
            out.append(("gemini/" + m, "gemini:" + m, lambda m=m: _gemini(m)))
    if orouter:
        out.append(("openrouter/free", "openrouter:openrouter/free", lambda: _oa_raw(
            session, "https://openrouter.ai/api/v1/chat/completions", orouter, "openrouter/free", prompt,
            max_tokens, timeout=timeout)))
    return out


def ask_pool(main, prompt, parse, max_tokens=400, budget=40, timeout=15, label="EDITOR GATE"):
    """Ask the free pool in order, skipping models in cooldown. (parsed, provider) or (None, "")."""
    import v13_ai_router as r
    session = getattr(main, "SESSION", None)
    if session is None:
        import requests
        session = requests.Session()
    deadline = time.monotonic() + budget
    health = r._load_health()
    skipped = []
    result = (None, "")
    for name, hkey, call in _attempts(main, session, prompt, max_tokens, timeout):
        if time.monotonic() >= deadline:
            break
        if r._model_disabled(health, hkey):
            skipped.append(name)
            continue
        try:
            parsed = parse(call())
            if parsed:
                result = (parsed, name)
                break
            print(f"V13 {label}: {name} returned no usable verdict", flush=True)
            _event(f"{label} {name}: no usable verdict")
        except Exception as exc:
            status = _status_of(exc)
            print(f"V13 {label}: {name} failed ({exc})", flush=True)
            _event(f"{label} {name}: {exc}")
            if status in (401, 403, 404, 429, 500, 502, 503, 504, 599):
                try:
                    r._mark_model_failure(hkey, status)
                except Exception:
                    pass
                health = r._load_health()
    if skipped:
        print(f"V13 {label}: skipped (cooldown) " + ", ".join(skipped), flush=True)
    return result


def install_editor_gate():
    import v13_editor_gate as g
    if getattr(g, "_v13_ai_extra", False):
        return

    def ai_judge(main, candidate):
        title = g._norm(candidate.get("title", ""))
        body = g._norm(candidate.get("summary", "") or candidate.get("description", "") or candidate.get("article_text", ""))[:900]
        return ask_pool(main, g.PROMPT % (title, body), g._parse, max_tokens=400,
                        budget=g.AI_BUDGET_PER_STORY, timeout=g.AI_TIMEOUT)

    g.ai_judge = ai_judge
    try:
        # English wires write "Aramco office hit" / "refinery struck": count those as war events too
        # ("shares hit a record" stays out: only a hit place/object counts).
        event = g.WAR_EVENT[:-1] + r"|\b(?:was|were|been|office|site|facility|facilities|plant|refinery|airport|port|tanker|ship)\s+hit\b|\bstruck\b(?!\s+(?:an?\s+|the\s+)?(?:deal|agreement|accord|pact|balance|tone|chord)))"
        g.WAR_ZONE = re.compile(event + r"[^.؛]{0,60}" + g.WAR_PLACES + r"|" + g.WAR_PLACES + r"[^.؛]{0,60}" + event, re.I)
    except Exception as exc:
        print(f"V13 AI EXTRA: war-zone verbs not extended ({exc})", flush=True)
    g._v13_ai_extra = True
    print("V13 AI EXTRA: editor gate is cooldown-aware (Groq -> Gemini -> OpenRouter)", flush=True)


# --------------------------------------------------------------------------
# 3) Batched editor verdicts
# --------------------------------------------------------------------------
BATCH_TAIL = """Stories to judge. Judge EACH story on its own with exactly the rules above; the stories are unrelated to each other.

%s

Return only JSON with one entry per story, in the same order:
{"items": [{"n": 1, "score": 0-10, "happened": true or false, "scope": "world" or "iran_national" or "local", "topic": "سیاست|نظامی|حادثه|اقتصاد|فناوری|سلامت|ورزش|قضایی|آب و هوا|جامعه", "reason": "max 12 words"}]}"""


def _batch_prompt(g, chunk):
    rubric = g.PROMPT.split("Story:")[0].rstrip()
    lines = []
    for i, c in enumerate(chunk, 1):
        title = g._norm(c.get("title", ""))[:220]
        body = g._norm(c.get("summary", "") or c.get("description", "") or c.get("article_text", ""))[:BATCH_BODY_CHARS]
        lines.append(f"{i}. TITLE: {title}\n   TEXT: {body}")
    return rubric + "\n\n" + BATCH_TAIL % "\n".join(lines)


def _parse_batch(raw, size):
    import v13_ai_router as r
    try:
        data = r._clean_json(raw)
    except Exception:
        return None
    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return None
    out = {}
    for pos, item in enumerate(items, 1):
        if not isinstance(item, dict) or "score" not in item:
            continue
        try:
            n = int(item.get("n", pos))
            score = int(round(float(item.get("score"))))
        except Exception:
            continue
        if not 1 <= n <= size:
            continue
        happened = item.get("happened")
        out[n] = {"score": score,
                  "happened": happened is True or str(happened).lower() == "true",
                  "scope": str(item.get("scope", "")).lower(),
                  "topic": str(item.get("topic", "") or ""),
                  "reason": str(item.get("reason", "") or "")[:120]}
    return out or None


def prejudge(main, pool):
    """Fill the editor cache for the uncached, non-vetoed pool stories with batched calls."""
    import v13_editor_gate as g
    todo, keys = [], set()
    for c in list(pool)[:g.POOL_SIZE]:
        if g.deterministic_veto(c):
            continue
        key = g._cache_key(c)
        if key in keys or g._cache_get(key):
            continue
        keys.add(key)
        todo.append(c)
    if len(todo) < 2:
        return 0
    done = 0
    started = time.monotonic()
    for start in range(0, len(todo), BATCH_SIZE):
        if time.monotonic() - started > BATCH_BUDGET_SECONDS:
            break
        chunk = todo[start:start + BATCH_SIZE]
        verdicts, provider = ask_pool(main, _batch_prompt(g, chunk), lambda raw: _parse_batch(raw, len(chunk)),
                                      max_tokens=BATCH_MAX_TOKENS, budget=45, timeout=40, label="EDITOR BATCH")
        if not verdicts:
            print(f"V13 EDITOR BATCH: no batch verdict for {len(chunk)} stories; single judging continues", flush=True)
            _event(f"EDITOR BATCH: no verdict for {len(chunk)} stories")
            break
        for n, verdict in verdicts.items():
            c = chunk[n - 1]
            ok = bool(g.ai_accepts(verdict, c))
            reason = (f"ai {provider} batch score={verdict.get('score')} happened={verdict.get('happened')} "
                      f"scope={verdict.get('scope')}: {verdict.get('reason', '')}")
            g._cache_put(g._cache_key(c), {"ok": ok, "reason": reason, "topic": verdict.get("topic", "")})
            done += 1
        print(f"V13 EDITOR BATCH: {len(verdicts)}/{len(chunk)} stories judged in one call via {provider}", flush=True)
        _event(f"EDITOR BATCH: {len(verdicts)}/{len(chunk)} via {provider}")
    return done


def install_batch_gate():
    import v13_editor_gate as g
    if getattr(g, "_v13_batch", False):
        return
    original_gate_pool = g.gate_pool

    def gate_pool(main, pool, target, budget=g.JUDGE_BUDGET, judge_fn=None):
        try:
            prejudge(main, pool)
        except Exception as exc:
            print(f"V13 EDITOR BATCH: skipped ({type(exc).__name__}: {exc})", flush=True)
            _event(f"EDITOR BATCH skipped: {type(exc).__name__}: {exc}")
        return original_gate_pool(main, pool, target, budget, judge_fn)

    g.gate_pool = gate_pool
    g._v13_batch = True
    print(f"V13 AI EXTRA: editor verdicts batched ({BATCH_SIZE} stories per AI call)", flush=True)


# --------------------------------------------------------------------------
# 4) AI meter + daily-quota rest (installed last, so no later layer bypasses it)
# --------------------------------------------------------------------------
def _next_pacific_midnight():
    try:
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("America/Los_Angeles"))
        return (now + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0).timestamp()
    except Exception:
        return time.time() + 6 * 3600


def _ai_target(url, kwargs):
    from urllib.parse import urlparse
    provider = AI_HOSTS.get((urlparse(str(url)).hostname or "").lower())
    if not provider:
        return None
    if provider == "gemini":
        found = re.search(r"/models/([^/:?]+):", str(url))
        model = found.group(1) if found else ""
    else:
        body = kwargs.get("json") if isinstance(kwargs.get("json"), dict) else {}
        model = str(body.get("model", "") or "")
    return f"{provider}:{model}" if model else None


def _meter(response, url, kwargs):
    hkey = _ai_target(url, kwargs)
    if not hkey:
        return
    row = _usage.setdefault(hkey, {"calls": 0, "ok": 0, "429": 0, "other": 0})
    row["calls"] += 1
    code = int(getattr(response, "status_code", 0) or 0)
    if 200 <= code < 300:
        row["ok"] += 1
        return
    text = re.sub(r"\s+", " ", str(getattr(response, "text", "") or ""))[:400]
    if code != 429:
        row["other"] += 1
        row["last_error"] = f"HTTP {code}: {text[:200]}"
        return
    row["429"] += 1
    row["last_429"] = text[:240]
    if DAILY_429.search(text):
        try:
            retry = float(response.headers.get("retry-after", 0) or 0)
        except Exception:
            retry = 0.0
        until = _next_pacific_midnight() if hkey.startswith("gemini:") else time.time() + max(retry, 3600)
        if _daily_rest.get(hkey, 0) < until:
            print(f"V13 AI METER: {hkey} daily quota used up; resting it until "
                  f"{time.strftime('%H:%M UTC', time.gmtime(until))}", flush=True)
        _daily_rest[hkey] = until


def install_ai_meter():
    import requests.sessions as rs
    if getattr(rs.Session.request, "_v13_meter", False):
        return
    original = rs.Session.request

    def request(self, method, url, *args, **kwargs):
        response = original(self, method, url, *args, **kwargs)
        try:
            if str(method).upper() == "POST":
                _meter(response, url, kwargs)
        except Exception:
            pass
        return response

    request._v13_meter = True
    rs.Session.request = request

    import v13_ai_router as r
    if not getattr(r, "_v13_daily_rest", False):
        previous = r._mark_model_failure

        def mark(model, status):
            previous(model, status)
            try:
                if int(status) == 429 and _daily_rest.get(model, 0) > time.time():
                    health = r._load_health()
                    entry = health.setdefault(model, {})
                    entry["disabled_until"] = max(float(entry.get("disabled_until", 0) or 0), _daily_rest[model])
                    entry["daily_quota_rest"] = True
                    r._save_health(health)
            except Exception:
                pass

        r._mark_model_failure = mark
        r._v13_daily_rest = True
    print("V13 AI EXTRA: AI meter on (calls/ok/429 per model per day -> _ai_usage)", flush=True)


def save_usage():
    if not _usage and not _daily_rest and not _events:
        return
    try:
        import v13_ai_router as r
        health = r._load_health()
        usage = health.get(USAGE_KEY) if isinstance(health.get(USAGE_KEY), dict) else {}
        today = usage.setdefault(time.strftime("%Y-%m-%d", time.gmtime()), {})
        for hkey, row in _usage.items():
            dst = today.setdefault(hkey, {"calls": 0, "ok": 0, "429": 0, "other": 0})
            for k in ("calls", "ok", "429", "other"):
                dst[k] = int(dst.get(k, 0) or 0) + int(row.get(k, 0) or 0)
            for k in ("last_429", "last_error"):
                if row.get(k):
                    dst[k] = row[k]
        for old in sorted(usage)[:-USAGE_DAYS]:
            usage.pop(old, None)
        health[USAGE_KEY] = usage
        log = health.get(EVENTS_KEY) if isinstance(health.get(EVENTS_KEY), list) else []
        health[EVENTS_KEY] = (log + _events)[-EVENTS_MAX:]
        for hkey, until in _daily_rest.items():
            entry = health.setdefault(hkey, {})
            entry["disabled_until"] = max(float(entry.get("disabled_until", 0) or 0), until)
            entry["daily_quota_rest"] = True
        r._save_health(health)
        _usage.clear()
        _events.clear()
        print("V13 AI METER: usage saved", flush=True)
    except Exception as exc:
        print(f"V13 AI METER: save warning {type(exc).__name__}: {exc}", flush=True)


# --------------------------------------------------------------------------
# 5) Short hold for "no AI available" blocks
# --------------------------------------------------------------------------
def install_block_ttl(rb):
    long_ttl = float(getattr(rb, "_EDITORIAL_BLOCK_TTL_SECONDS", 6 * 3600))

    def effective_until(v):
        until = float(v.get("until", 0) or 0)
        if str(v.get("reason", "")).startswith("ai_unavailable"):
            at = float(v.get("at", 0) or 0) or (until - long_ttl)
            until = min(until, at + AI_UNAVAILABLE_TTL_SECONDS)
        return until

    def _load_recent_blocks():
        try:
            blocks = rb.v13_ai_router._load_health().get(rb._EDITORIAL_BLOCK_KEY) or {}
            now = time.time()
            return {k: v for k, v in blocks.items() if isinstance(v, dict) and effective_until(v) > now}
        except Exception as exc:
            print(f"V13 EDITORIAL BLOCKS: load warning: {type(exc).__name__}: {exc}")
            return {}

    def _save_recent_blocks(new_blocks):
        if not new_blocks:
            return
        try:
            health = rb.v13_ai_router._load_health()
            blocks = _load_recent_blocks()
            now = time.time()
            for title, reason in new_blocks.items():
                ttl = AI_UNAVAILABLE_TTL_SECONDS if str(reason).startswith("ai_unavailable") else long_ttl
                blocks[title] = {"until": now + ttl, "at": now, "reason": reason}
            if len(blocks) > rb._EDITORIAL_BLOCK_MAX:
                newest = sorted(blocks.items(), key=lambda kv: kv[1].get("until", 0))[-rb._EDITORIAL_BLOCK_MAX:]
                blocks = dict(newest)
            health[rb._EDITORIAL_BLOCK_KEY] = blocks
            rb.v13_ai_router._save_health(health)
        except Exception as exc:
            print(f"V13 EDITORIAL BLOCKS: save warning: {type(exc).__name__}: {exc}")

    rb._load_recent_blocks = _load_recent_blocks
    rb._save_recent_blocks = _save_recent_blocks
    print(f"V13 AI EXTRA: no-AI blocks held {AI_UNAVAILABLE_TTL_SECONDS // 60} min (others {int(long_ttl // 3600)} h)", flush=True)


def _safe(label, fn):
    try:
        fn()
    except Exception as exc:
        print(f"V13 AI EXTRA: {label} install skipped: {type(exc).__name__}: {exc}", flush=True)


if __name__ == "__main__":
    import atexit
    import run_bot as rb  # module-level patches of run_bot apply; its __main__ block does not run
    _safe("router", install_router)
    _safe("editor gate", install_editor_gate)
    _safe("batch gate", install_batch_gate)
    _safe("block ttl", lambda: install_block_ttl(rb))
    try:
        import daily_boards
        daily_boards.run()
    except Exception as exc:
        print(f"DAILY BOARDS: launcher error: {type(exc).__name__}: {exc}", flush=True)
    rb._patch_history_rescue_pipeline()
    rb._install_v13_stack()
    _safe("ai meter", install_ai_meter)
    atexit.register(save_usage)
    print("V13 ENGINE LAUNCH: v13_ai_extra -> run_bot -> v13_standalone.main()", flush=True)
    try:
        result = rb.main.main()
    finally:
        for title in _no_ai_titles:
            rb._editorial_blocks_this_run.setdefault(rb._norm_title(title), "ai_unavailable_local")
        rb._reclassify_editorial_blocks()
        save_usage()
    if result is False:
        raise SystemExit(1)
