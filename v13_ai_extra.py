"""NABZ KHABAR: extra free AI providers + outage behaviour (Oct 14 2026).

Why: on Oct 13 every free model (Groq, Gemini, OpenRouter) returned 429 from
16:58Z and the channel stayed silent all night. Three fixes, installed by this
launcher without touching the other files:

1. Two more free providers in BOTH the translation router and the final editor:
   Cerebras (CEREBRAS_API_KEY, OpenAI-compatible) and GitHub Models
   (GH_MODELS_TOKEN or the workflow GITHUB_TOKEN with `models: read`).
   A missing key simply skips the provider.
2. The editor gate now skips models that are in cooldown and records 429/5xx
   in the shared health file, so a dead model is not hit for every story.
3. A story blocked only because no AI was available (ai_unavailable_foreign)
   is held for 20 minutes instead of 6 hours, so it is retried once AI is back.
4. Root cause (Oct 14): the free quotas ran out by evening because the editor
   gate spent one AI call (with the long rubric) per story, up to 20 stories a
   run, 144 runs a day. Now the uncached stories of a run are judged in ONE
   batched call (up to 10 per call), article text sent for translation is
   capped, and a 429 that says the DAILY quota is used up rests that model
   until its reset instead of retrying every 10 minutes all night.
5. AI meter: calls / ok / 429 per provider and day are saved in
   ai_model_health.json (_ai_usage), with the last 429 message, so quota use is
   visible instead of guessed.

Run with `python v13_ai_extra.py` (same as `python run_bot.py`, plus the above).
If anything here fails to install, the bot runs exactly as before.
"""

import os
import re
import time

CEREBRAS_BASE = "https://api.cerebras.ai/v1"
CEREBRAS_PREFERRED = ("gpt-oss-120b", "qwen-3-235b-a22b-instruct-2507", "llama-3.3-70b", "zai-glm-4.6", "qwen-3-32b", "llama3.1-8b")
GITHUB_BASE = "https://models.github.ai/inference"
GITHUB_MODELS = ("openai/gpt-4.1-mini", "openai/gpt-4o-mini")
AI_UNAVAILABLE_TTL_SECONDS = 20 * 60
EXTRA_BUDGET_SECONDS = 30

GITHUB_TIMEOUT = 30
PAYMENT_COOLDOWN_SECONDS = 6 * 3600
TRANSLATION_SOURCE_CHARS = 3500
BATCH_SIZE = 10
BATCH_BODY_CHARS = 320
BATCH_BUDGET_SECONDS = 60
USAGE_KEY = "_ai_usage"
USAGE_DAYS = 4
AI_HOSTS = {
    "generativelanguage.googleapis.com": "gemini",
    "api.groq.com": "groq",
    "openrouter.ai": "openrouter",
    "api.cerebras.ai": "cerebras",
    "models.github.ai": "github",
}
DAILY_429 = re.compile(r"per[ _-]?day|perday|daily|\bTPD\b|\bRPD\b|tokens per day|requests per day", re.I)
_daily_rest = {}   # health key -> unix time when its daily quota resets
_usage = {}        # "provider:model" -> counters for this run

_cerebras_cache = {"at": 0.0, "models": []}
_ctx = {}


def _note_error(hkey, text):
    """Keep the real error text in the health file so the next check can see it."""
    try:
        import v13_ai_router as r
        health = r._load_health()
        health.setdefault(hkey, {})["last_error"] = str(text)[:300]
        r._save_health(health)
    except Exception:
        pass


def github_chat(model, messages, max_tokens=900, json_mode=True):
    """One GitHub Models call with its own plain session. Returns text or raises RuntimeError."""
    import requests
    payload = {"model": model, "messages": messages, "temperature": 0.15, "max_tokens": max_tokens}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    try:
        resp = requests.post(f"{GITHUB_BASE}/chat/completions", json=payload, timeout=GITHUB_TIMEOUT,
                             headers={"Authorization": f"Bearer {github_key()}",
                                      "Content-Type": "application/json",
                                      "Accept": "application/json",
                                      "X-GitHub-Api-Version": "2022-11-28",
                                      "User-Agent": "NabzKhabar-V13/1.0"})
    except Exception as exc:
        _note_error("github:" + model, f"{type(exc).__name__}: {exc}")
        raise RuntimeError(f"network {type(exc).__name__}: {exc}")
    if not resp.ok:
        _note_error("github:" + model, f"HTTP {resp.status_code}: {resp.text[:250]}")
        raise RuntimeError(f"HTTP {resp.status_code}")
    try:
        content = (resp.json().get("choices") or [{}])[0].get("message", {}).get("content", "")
    except Exception as exc:
        _note_error("github:" + model, f"bad body {type(exc).__name__}: {resp.text[:200]}")
        raise RuntimeError(f"bad body {type(exc).__name__}")
    if isinstance(content, list):
        content = "".join(str(x.get("text", "")) if isinstance(x, dict) else str(x) for x in content)
    return str(content or "")


def cerebras_key():
    return os.getenv("CEREBRAS_API_KEY", "").strip()


def github_key():
    return (os.getenv("GH_MODELS_TOKEN", "") or os.getenv("GITHUB_TOKEN", "")).strip()


def cerebras_models(session):
    key = cerebras_key()
    if not key:
        return []
    now = time.time()
    if _cerebras_cache["models"] and now - _cerebras_cache["at"] < 3600:
        return list(_cerebras_cache["models"])
    found = []
    try:
        r = session.get(f"{CEREBRAS_BASE}/models", timeout=8,
                        headers={"Authorization": f"Bearer {key}", "User-Agent": "NabzKhabar-V13/1.0"})
        if r.ok:
            found = [str(x.get("id", "")).strip() for x in (r.json() or {}).get("data", []) if x.get("id")]
        else:
            print(f"V13 AI EXTRA: Cerebras model list HTTP {r.status_code}", flush=True)
    except Exception as exc:
        print(f"V13 AI EXTRA: Cerebras model list error {exc}", flush=True)
    if found:
        ordered = [m for m in CEREBRAS_PREFERRED if m in found]
        ordered += [m for m in found if m not in ordered]
    else:
        ordered = list(CEREBRAS_PREFERRED[:3])
    ordered = ordered[:4]
    _cerebras_cache.update(at=now, models=ordered)
    print("V13 AI EXTRA: Cerebras models: " + ", ".join(ordered), flush=True)
    return list(ordered)


# --------------------------------------------------------------------------
# 1) Translation router
# --------------------------------------------------------------------------
def install_router():
    import v13_ai_router as r
    if getattr(r, "_v13_ai_extra", False):
        return
    original_fpr = r._fallback_provider_request
    original_request = r.gemini_request

    def _github(main):
        c = _ctx
        if not c or c.get("github_done"):
            return None
        c["github_done"] = True
        key = github_key()
        if not key:
            return None
        health = r._load_health()
        system = "خروجی فقط یک JSON معتبر با دو کلید title و summary باشد؛ هیچ متن دیگری تولید نکن."
        for model in GITHUB_MODELS:
            hkey = "github:" + model
            if r._model_disabled(health, hkey):
                print(f"V13 AI ROUTER: GitHub/{model} is in cooldown; skipping.", flush=True)
                continue
            try:
                raw = github_chat(model, [{"role": "system", "content": system},
                                          {"role": "user", "content": c["prompt"]}], max_tokens=1200)
                data = r._clean_json(raw)
            except Exception as exc:
                status = _status_of(exc)
                print(f"V13 AI ROUTER: GitHub/{model} failed ({exc}); failing over.", flush=True)
                r._mark_model_failure(hkey, status)
                health = r._load_health()
                continue
            validated = r._validate(main, c["title"], c["source"], data, c["foreign"])
            if validated:
                r._mark_model_success(hkey)
                print(f"V13 AI ROUTER: SUCCESS via GitHub/{model}", flush=True)
                return validated
            print(f"V13 AI ROUTER: GitHub/{model} failed V13 content validation.", flush=True)
            r._record_quality_failure(hkey)
        return None

    def fpr(main, provider, models, base_url, api_key, prompt, title, source, foreign, deadline=None):
        if provider == "Groq":
            _ctx.clear()
            _ctx.update(prompt=prompt, title=title, source=source, foreign=foreign,
                        deadline=deadline, github_done=False)
            key = cerebras_key()
            if key:
                res = original_fpr(main, "Cerebras", cerebras_models(main.SESSION), CEREBRAS_BASE, key,
                                   prompt, title, source, foreign, deadline)
                if res:
                    return res
        res = original_fpr(main, provider, models, base_url, api_key, prompt, title, source, foreign, deadline)
        if res:
            return res
        if provider == "OpenRouter":
            return _github(main)
        return None

    def gemini_request(main, title, article_text):
        _ctx.clear()
        res = original_request(main, title, str(article_text or "")[:TRANSLATION_SOURCE_CHARS] or article_text)
        if res is None and _ctx and not _ctx.get("github_done"):
            res = _github(main)
            if res:
                print("V13 AI EXTRA: rescued by GitHub Models", flush=True)
        return res

    r._fallback_provider_request = fpr
    r.gemini_request = gemini_request
    r._v13_ai_extra = True
    print("V13 AI EXTRA: router order Cerebras -> Groq -> Gemini -> OpenRouter -> GitHub Models "
          f"(Cerebras={'READY' if cerebras_key() else 'MISSING'}, GitHub={'READY' if github_key() else 'MISSING'})", flush=True)


# --------------------------------------------------------------------------
# 2) Final editor gate: more providers, cooldown-aware
# --------------------------------------------------------------------------
def _status_of(exc):
    found = re.search(r"HTTP (\d{3})", str(exc))
    return int(found.group(1)) if found else 599


def _oa_raw(session, url, key, model, prompt, max_tokens, extra=None, timeout=15):
    """OpenAI-compatible call that returns the raw text (raises 'HTTP nnn' on error)."""
    payload = {"model": model, "temperature": 0, "max_tokens": max_tokens,
               "messages": [{"role": "user", "content": prompt}],
               "response_format": {"type": "json_object"}}
    payload.update(extra or {})
    resp = session.post(url, timeout=timeout, json=payload,
                        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                 "User-Agent": "NabzKhabar-EditorGate/1.0"})
    if not resp.ok:
        raise RuntimeError(f"HTTP {resp.status_code}")
    content = (resp.json().get("choices") or [{}])[0].get("message", {}).get("content", "")
    if isinstance(content, list):
        content = "".join(str(x.get("text", "")) if isinstance(x, dict) else str(x) for x in content)
    return str(content or "")


def _gate_attempts(main, session, prompt, max_tokens, timeout):
    import v13_editor_gate as g
    groq = os.getenv("GROQ_API_KEY", "").strip()
    gem = str(getattr(main, "AI_API_KEY", "") or os.getenv("AI_API_KEY", "")).strip()
    orouter = os.getenv("OPENROUTER_API_KEY", "").strip()
    cere = cerebras_key()
    attempts = []  # (label, health key, call -> raw text)
    if cere:
        for m in cerebras_models(session):
            attempts.append(("cerebras/" + m, "cerebras:" + m, lambda m=m: _oa_raw(
                session, f"{CEREBRAS_BASE}/chat/completions", cere, m, prompt, max(1200, max_tokens), timeout=timeout)))
    if groq:
        for m in g.GROQ_MODELS:
            attempts.append(("groq/" + m, "groq:" + m, lambda m=m: _oa_raw(
                session, "https://api.groq.com/openai/v1/chat/completions", groq, m, prompt, max_tokens,
                {"include_reasoning": False}, timeout=timeout)))
    if gem:
        def _gemini(m):
            resp = session.post(f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent",
                                params={"key": gem}, timeout=timeout,
                                json={"contents": [{"parts": [{"text": prompt}]}],
                                      "generationConfig": {"responseMimeType": "application/json", "temperature": 0}})
            if not resp.ok:
                raise RuntimeError(f"HTTP {resp.status_code}")
            parts = ((resp.json().get("candidates") or [{}])[0].get("content") or {}).get("parts") or [{}]
            return str(parts[0].get("text", "") or "")
        for m in g.GEMINI_MODELS:
            attempts.append(("gemini/" + m, "gemini:" + m, lambda m=m: _gemini(m)))
    if orouter:
        attempts.append(("openrouter/free", "openrouter:openrouter/free", lambda: _oa_raw(
            session, "https://openrouter.ai/api/v1/chat/completions", orouter, "openrouter/free", prompt,
            max_tokens, timeout=timeout)))
    if github_key():
        for m in GITHUB_MODELS:
            attempts.append(("github/" + m, "github:" + m, lambda m=m: github_chat(
                m, [{"role": "user", "content": prompt}], max_tokens=max_tokens)))
    return attempts


def ask_pool(main, prompt, parse, max_tokens=400, budget=40, timeout=15, label="EDITOR GATE"):
    """Free pool in order, skipping models in cooldown. Returns (parsed, provider) or (None, "")."""
    import v13_ai_router as r
    session = getattr(main, "SESSION", None)
    if session is None:
        import requests
        session = requests.Session()
    deadline = time.monotonic() + budget
    health = r._load_health()
    skipped = []
    result = (None, "")
    for name, hkey, call in _gate_attempts(main, session, prompt, max_tokens, timeout):
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
        except Exception as exc:
            status = _status_of(exc)
            print(f"V13 {label}: {name} failed ({exc})", flush=True)
            if status in (401, 402, 403, 404, 429, 500, 502, 503, 504, 599):
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
    g._v13_ai_extra = True
    print("V13 AI EXTRA: editor gate order Cerebras -> Groq -> Gemini -> OpenRouter -> GitHub Models, cooldown-aware", flush=True)


# --------------------------------------------------------------------------
# 2b) Batched editor verdicts: one AI call for up to BATCH_SIZE stories
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
    """Fill the editor cache for every uncached, non-vetoed pool story with batched calls."""
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
                                      max_tokens=3000, budget=45, timeout=40, label="EDITOR BATCH")
        if not verdicts:
            print(f"V13 EDITOR BATCH: no batch verdict for {len(chunk)} stories; single judging continues", flush=True)
            break
        for n, verdict in verdicts.items():
            c = chunk[n - 1]
            ok = bool(g.ai_accepts(verdict, c))
            reason = (f"ai {provider} batch score={verdict.get('score')} happened={verdict.get('happened')} "
                      f"scope={verdict.get('scope')}: {verdict.get('reason', '')}")
            g._cache_put(g._cache_key(c), {"ok": ok, "reason": reason, "topic": verdict.get("topic", "")})
            done += 1
        print(f"V13 EDITOR BATCH: {len(verdicts)}/{len(chunk)} stories judged in one call via {provider}", flush=True)
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
        return original_gate_pool(main, pool, target, budget, judge_fn)

    g.gate_pool = gate_pool
    g._v13_batch = True
    print(f"V13 AI EXTRA: editor verdicts batched ({BATCH_SIZE} stories per AI call)", flush=True)


# --------------------------------------------------------------------------
# 2c) AI meter + daily-quota rest
# --------------------------------------------------------------------------
def _next_pacific_midnight():
    try:
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("America/Los_Angeles"))
        nxt = (now + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
        return nxt.timestamp()
    except Exception:
        return time.time() + 6 * 3600


def _ai_target(url, kwargs):
    from urllib.parse import urlparse
    host = (urlparse(str(url)).hostname or "").lower()
    provider = AI_HOSTS.get(host)
    if not provider:
        return None, None
    if provider == "gemini":
        found = re.search(r"/models/([^/:?]+):", str(url))
        model = found.group(1) if found else ""
    else:
        body = kwargs.get("json") if isinstance(kwargs.get("json"), dict) else {}
        model = str(body.get("model", "") or "")
    if not model:
        return None, None
    return provider, model


def install_ai_meter():
    import atexit
    import requests.sessions as rs
    if getattr(rs.Session.request, "_v13_meter", False):
        return
    original = rs.Session.request

    def request(self, method, url, *args, **kwargs):
        response = original(self, method, url, *args, **kwargs)
        try:
            if str(method).upper() != "POST":
                return response
            provider, model = _ai_target(url, kwargs)
            if not provider:
                return response
            hkey = f"{provider}:{model}"
            row = _usage.setdefault(hkey, {"calls": 0, "ok": 0, "429": 0, "other": 0})
            row["calls"] += 1
            code = int(getattr(response, "status_code", 0) or 0)
            if 200 <= code < 300:
                row["ok"] += 1
            elif code == 429:
                row["429"] += 1
                text = str(getattr(response, "text", "") or "")[:600]
                row["last_429"] = re.sub(r"\s+", " ", text)[:240]
                if DAILY_429.search(text):
                    retry = 0.0
                    try:
                        retry = float(response.headers.get("retry-after", 0) or 0)
                    except Exception:
                        retry = 0.0
                    until = _next_pacific_midnight() if provider == "gemini" else time.time() + max(retry, 3600)
                    if _daily_rest.get(hkey, 0) < until:
                        print(f"V13 AI METER: {hkey} daily quota used up; resting it until "
                              f"{time.strftime('%H:%M UTC', time.gmtime(until))}", flush=True)
                    _daily_rest[hkey] = until
            else:
                row["other"] += 1
        except Exception:
            pass
        return response

    request._v13_meter = True
    rs.Session.request = request
    atexit.register(save_usage)
    print("V13 AI EXTRA: AI meter on (calls/ok/429 per model per day -> _ai_usage)", flush=True)


def save_usage():
    if not _usage and not _daily_rest:
        return
    try:
        import v13_ai_router as r
        health = r._load_health()
        usage = health.get(USAGE_KEY) if isinstance(health.get(USAGE_KEY), dict) else {}
        day = time.strftime("%Y-%m-%d", time.gmtime())
        today = usage.setdefault(day, {})
        for hkey, row in _usage.items():
            dst = today.setdefault(hkey, {"calls": 0, "ok": 0, "429": 0, "other": 0})
            for k in ("calls", "ok", "429", "other"):
                dst[k] = int(dst.get(k, 0) or 0) + int(row.get(k, 0) or 0)
            if row.get("last_429"):
                dst["last_429"] = row["last_429"]
        for old in sorted(usage)[:-USAGE_DAYS]:
            usage.pop(old, None)
        health[USAGE_KEY] = usage
        for hkey, until in _daily_rest.items():
            entry = health.setdefault(hkey, {})
            entry["disabled_until"] = max(float(entry.get("disabled_until", 0) or 0), until)
            entry["daily_quota_rest"] = True
        r._save_health(health)
        _usage.clear()
    except Exception as exc:
        print(f"V13 AI METER: save warning {type(exc).__name__}: {exc}", flush=True)


# --------------------------------------------------------------------------
# 3) Short hold for "no AI available" blocks
# --------------------------------------------------------------------------
def install_block_ttl(rb):
    long_ttl = float(getattr(rb, "_EDITORIAL_BLOCK_TTL_SECONDS", 6 * 3600))

    def effective_until(v):
        until = float(v.get("until", 0) or 0)
        if v.get("reason") == "ai_unavailable_foreign":
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
                ttl = AI_UNAVAILABLE_TTL_SECONDS if reason == "ai_unavailable_foreign" else long_ttl
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


def install_payment_cooldown():
    """HTTP 402 (no free quota on the account): rest 6 hours. HTTP 429 that says the daily
    quota is used up: rest until the provider's daily reset (see the AI meter)."""
    import v13_ai_router as r
    if getattr(r, "_v13_payment_cooldown", False):
        return
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
            if int(status) == 402:
                health = r._load_health()
                entry = health.setdefault(model, {})
                entry["disabled_until"] = max(float(entry.get("disabled_until", 0) or 0), time.time() + PAYMENT_COOLDOWN_SECONDS)
                entry["last_error"] = "HTTP 402 payment required (no free quota on this account)"
                r._save_health(health)
        except Exception:
            pass

    r._mark_model_failure = mark
    r._v13_payment_cooldown = True


def install_all(rb):
    for label, fn in (("ai meter", install_ai_meter), ("batch gate", install_batch_gate), ("402 cooldown", install_payment_cooldown), ("router", install_router), ("editor gate", install_editor_gate),
                      ("block ttl", lambda: install_block_ttl(rb))):
        try:
            fn()
        except Exception as exc:
            print(f"V13 AI EXTRA: {label} install skipped: {type(exc).__name__}: {exc}", flush=True)


if __name__ == "__main__":
    import run_bot as rb  # module-level patches of run_bot apply; its __main__ block does not run
    install_all(rb)
    try:
        import daily_boards
        daily_boards.run()
    except Exception as exc:
        print(f"DAILY BOARDS: launcher error: {type(exc).__name__}: {exc}", flush=True)
    rb._patch_history_rescue_pipeline()
    rb._install_v13_stack()
    print("V13 ENGINE LAUNCH: v13_ai_extra -> run_bot -> v13_standalone.main()", flush=True)
    try:
        result = rb.main.main()
    finally:
        rb._reclassify_editorial_blocks()
    if result is False:
        raise SystemExit(1)
