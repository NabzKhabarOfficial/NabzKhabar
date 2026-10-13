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

_cerebras_cache = {"at": 0.0, "models": []}
_ctx = {}


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
        deadline = c.get("deadline")
        if deadline is None or time.monotonic() >= deadline - 5:
            deadline = time.monotonic() + EXTRA_BUDGET_SECONDS
        return original_fpr(main, "GitHub", GITHUB_MODELS, GITHUB_BASE, key,
                            c["prompt"], c["title"], c["source"], c["foreign"], deadline)

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
        res = original_request(main, title, article_text)
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


def install_editor_gate():
    import v13_editor_gate as g
    import v13_ai_router as r
    if getattr(g, "_v13_ai_extra", False):
        return

    def ai_judge(main, candidate):
        session = getattr(main, "SESSION", None)
        if session is None:
            import requests
            session = requests.Session()
        title = g._norm(candidate.get("title", ""))
        body = g._norm(candidate.get("summary", "") or candidate.get("description", "") or candidate.get("article_text", ""))[:900]
        prompt = g.PROMPT % (title, body)
        deadline = time.monotonic() + g.AI_BUDGET_PER_STORY
        groq = os.getenv("GROQ_API_KEY", "").strip()
        gem = str(getattr(main, "AI_API_KEY", "") or os.getenv("AI_API_KEY", "")).strip()
        orouter = os.getenv("OPENROUTER_API_KEY", "").strip()
        cere = cerebras_key()
        gh = github_key()
        attempts = []  # (label, health key, call)
        if cere:
            for m in cerebras_models(session):
                attempts.append(("cerebras/" + m, "cerebras:" + m, lambda m=m: g._openai_style(
                    session, f"{CEREBRAS_BASE}/chat/completions", cere, m, prompt, {"max_tokens": 1200})))
        if groq:
            for m in g.GROQ_MODELS:
                attempts.append(("groq/" + m, "groq:" + m, lambda m=m: g._openai_style(
                    session, "https://api.groq.com/openai/v1/chat/completions", groq, m, prompt,
                    {"include_reasoning": False})))
        if gem:
            def _gemini(m):
                resp = session.post(f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent",
                                    params={"key": gem}, timeout=g.AI_TIMEOUT,
                                    json={"contents": [{"parts": [{"text": prompt}]}],
                                          "generationConfig": {"responseMimeType": "application/json", "temperature": 0}})
                if not resp.ok:
                    raise RuntimeError(f"HTTP {resp.status_code}")
                parts = ((resp.json().get("candidates") or [{}])[0].get("content") or {}).get("parts") or [{}]
                return g._parse(parts[0].get("text", ""))
            for m in g.GEMINI_MODELS:
                attempts.append(("gemini/" + m, "gemini:" + m, lambda m=m: _gemini(m)))
        if orouter:
            attempts.append(("openrouter/free", "openrouter:openrouter/free", lambda: g._openai_style(
                session, "https://openrouter.ai/api/v1/chat/completions", orouter, "openrouter/free", prompt)))
        if gh:
            for m in GITHUB_MODELS:
                attempts.append(("github/" + m, "github:" + m, lambda m=m: g._openai_style(
                    session, f"{GITHUB_BASE}/chat/completions", gh, m, prompt)))
        health = r._load_health()
        skipped = []
        for name, hkey, call in attempts:
            if time.monotonic() >= deadline:
                break
            if r._model_disabled(health, hkey):
                skipped.append(name)
                continue
            try:
                verdict = call()
                if verdict:
                    if skipped:
                        print("V13 EDITOR GATE: skipped (cooldown) " + ", ".join(skipped), flush=True)
                    return verdict, name
                print(f"V13 EDITOR GATE: {name} returned no usable verdict", flush=True)
            except Exception as exc:
                status = _status_of(exc)
                print(f"V13 EDITOR GATE: {name} failed ({exc})", flush=True)
                if status in (401, 403, 404, 429, 500, 502, 503, 504, 599):
                    try:
                        r._mark_model_failure(hkey, status)
                    except Exception:
                        pass
                    health = r._load_health()
        if skipped:
            print("V13 EDITOR GATE: skipped (cooldown) " + ", ".join(skipped), flush=True)
        return None, ""

    g.ai_judge = ai_judge
    g._v13_ai_extra = True
    print("V13 AI EXTRA: editor gate order Cerebras -> Groq -> Gemini -> OpenRouter -> GitHub Models, cooldown-aware", flush=True)


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


def install_all(rb):
    for label, fn in (("router", install_router), ("editor gate", install_editor_gate),
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
