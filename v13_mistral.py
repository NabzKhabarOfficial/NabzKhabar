"""NABZ KHABAR: Mistral's free tier as one more AI provider (Oct 15 2026).

Owner's own free Mistral account (La Plateforme free plan, no card): a different provider, not an
extra key for an existing one. Its free plan is large (about a billion tokens a month, ~1 request a
second), so it can carry the night when Groq's 200k tokens a day and Gemini's daily requests are
used up. It is used only AFTER Groq and Gemini, before OpenRouter (50 free requests a day):

1. Translation / rewrite (v13_ai_router.gemini_request): when the router reaches OpenRouter,
   Mistral (open-mistral-nemo, ministral-8b-latest) is asked first with the
   same prompt, the same JSON check and the same strict content validation.
2. Final editor (v13_ai_extra.ask_pool): open-mistral-nemo is the last resort, after OpenRouter
   (approvals only, see below), with a 1.5s minimum gap and a single 2.5s retry on transient HTTP 429.
3. Event judge + AI sense check (v13_event_judge.ask): open-mistral-nemo first (see below).
4. The AI meter counts it (_ai_usage key "mistral:<model>"); it is not paced (no daily cap).

Oct 15 (night review): with open-mistral-nemo first, the editor gate scored clear first-tier news
0 and "local" («پنتاگون انتشار گزارش حمله به میناب را عقب انداخت»، «لبنان مجوز بانک صادرات ایران را
لغو کرد», the ex-Shin Bet chief suing Netanyahu), and those wrong verdicts were cached for 24 h.
mistral-small-latest (same free plan, far better at the rubric and at Persian) now goes first,
nemo is only a fallback, and the editor-cache rejections made by nemo are dropped once
(_purge_nemo_rejections) so those stories are judged again by a stronger model.
Same night, next run: mistral-small was in cooldown, so nemo judged again and again cached wrong
rejections for 24 h. nemo and ministral-8b now never act as editor (translation fallback only);
when no strong model answers, the gate fails closed WITHOUT caching, so the story is judged again
on the next run. The purge runs once more (v2).

Oct 15, 22:45 Tehran (root cause of the silent evening, from _ai_usage / _ai_pace): from ~21:00 every
Groq, Gemini and OpenRouter model was over its daily share (Groq gpt-oss 103/90 and 100/90 calls,
its real 200k tokens/day also full; Gemini flash-lite 208/360 and 116/210 at noon Pacific; OpenRouter
36/42), Gemini 3.6/3.8 flash answered 503 (high demand), mistral-small-latest answered 429 to all 61
calls, qwen3-32b does not exist on Groq. Only open-mistral-nemo worked (202/202), with ~1B free tokens a
month. The biggest token eaters on Groq/Gemini were the same-event judge (every post + 45 headlines,
~3k tokens a call) and the AI sense check, which ran on the scarce models first. Now:
* same-event judge + sense check ask open-mistral-nemo FIRST. A sense-check flag still needs a second
  model to agree. A nemo "not a repeat" for a post that shares words with a published headline is
  checked again by the strong pool (Groq/Gemini), so no duplicate slips through on nemo's word alone;
* the strong daily quotas are kept for the translation and the editor;
* editor: nemo is the very last resort, after OpenRouter. Its "publish" verdicts count; its "reject"
  verdicts are never cached and fall to the deterministic rule (hard events and war-zone reports pass,
  the rest waits for a strong model on a later run), because its rejections were wrong (scope "local").
* mistral-small-latest is no longer asked at all (always 429 on this plan).

No MISTRAL_API_KEY in the environment = nothing changes. Any error = the bot runs as before.
"""

import os
import re
import sys
import time

MISTRAL_BASE = "https://api.mistral.ai/v1"
TRANSLATE_MODELS = ("open-mistral-nemo", "ministral-8b-latest")  # mistral-small: 61/61 HTTP 429 on this free plan
EDITOR_MODELS = ("open-mistral-nemo",)  # last resort only: its approvals count, its rejections do not (see notes)
NEMO = "open-mistral-nemo"
JUDGE_HEAD = "You are the duplicate checker"
SENSE_HEAD = "You check a Persian Telegram news post"
MIN_INTERVAL_SEC = 1.5   # La Plateforme free tier is ~1 req/s across the account
RETRY_429_SLEEP_SEC = 2.5
PURGE_MARK = "_mistral_nemo_purge_v2"
_INSTALLED = {"done": False}
_LAST_CALL = {"at": 0.0}


def _key():
    return os.getenv("MISTRAL_API_KEY", "").strip()


def _pace_rps():
    wait = MIN_INTERVAL_SEC - (time.monotonic() - _LAST_CALL["at"])
    if wait > 0:
        time.sleep(wait)
    _LAST_CALL["at"] = time.monotonic()


def _install_rps_guard():
    import requests.sessions as rs
    if getattr(rs.Session.request, "_v13_mistral_rps", False):
        return
    original = rs.Session.request

    def request(self, method, url, *args, **kwargs):
        if "api.mistral.ai" in str(url):
            _pace_rps()
            resp = original(self, method, url, *args, **kwargs)
            if getattr(resp, "status_code", 0) == 429:
                # Transient per-second rate limit on La Plateforme: wait once and retry
                time.sleep(RETRY_429_SLEEP_SEC)
                _LAST_CALL["at"] = time.monotonic()
                resp = original(self, method, url, *args, **kwargs)
            return resp
        return original(self, method, url, *args, **kwargs)

    request._v13_mistral_rps = True
    rs.Session.request = request


def _install_router(key):
    import v13_ai_router as r
    previous = r._fallback_provider_request
    if getattr(previous, "_v13_mistral", False):
        return
    orig_oa = r._openai_compatible_json
    if not getattr(orig_oa, "_v13_mistral_json", False):
        def oa_json(main, provider, base_url, api_key, model, prompt, max_output_tokens=500):
            # Mistral supports response_format={"type": "json_object"} like OpenRouter
            if str(provider).lower() == "mistral":
                return orig_oa(main, "openrouter", base_url, api_key, model, prompt, max_output_tokens=max_output_tokens)
            return orig_oa(main, provider, base_url, api_key, model, prompt, max_output_tokens=max_output_tokens)

        oa_json._v13_mistral_json = True
        r._openai_compatible_json = oa_json

    def fallback(main, provider, models, base_url, api_key, prompt, title, source, foreign, deadline=None):
        if str(provider).lower() == "openrouter":
            got = previous(main, "Mistral", TRANSLATE_MODELS, MISTRAL_BASE, key, prompt, title, source,
                           foreign, deadline)
            if got:
                return got
        return previous(main, provider, models, base_url, api_key, prompt, title, source, foreign, deadline)

    fallback._v13_mistral = True
    r._fallback_provider_request = fallback


def _install_editor(key):
    extra = sys.modules.get("__main__")
    attempts = getattr(extra, "_attempts", None)
    oa_raw = getattr(extra, "_oa_raw", None)
    if not callable(attempts) or not callable(oa_raw) or not hasattr(extra, "ask_pool"):
        return False
    hosts = getattr(extra, "AI_HOSTS", None)
    if isinstance(hosts, dict):
        hosts["api.mistral.ai"] = "mistral"
    if getattr(attempts, "_v13_mistral", False):
        return True

    def with_mistral(main, session, prompt, max_tokens, timeout):
        out = attempts(main, session, prompt, max_tokens, timeout)
        pos = len(out)  # after OpenRouter: nemo is the editor's very last resort (approvals only)
        for m in reversed(EDITOR_MODELS):
            item = ("mistral/" + m, "mistral:" + m, lambda m=m: oa_raw(
                session, MISTRAL_BASE + "/chat/completions", key, m, prompt, max_tokens,
                timeout=timeout))
            out.insert(pos, item)
        return out

    with_mistral._v13_mistral = True
    extra._attempts = with_mistral
    return True


def _mistral_ask(ej, key, prompt, model):
    tag = f"mistral/{model}"
    try:
        r = ej._post(MISTRAL_BASE + "/chat/completions",
                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                     json={"model": model, "temperature": 0, "max_tokens": 350,
                           "response_format": {"type": "json_object"},
                           "messages": [{"role": "user", "content": prompt}]})
        if r.ok:
            data = ej._parse(r.json()["choices"][0]["message"]["content"])
            if isinstance(data, dict) and data.get("verdict"):
                return dict(data, model=tag)
        print(f"V13 EVENT JUDGE: {tag} HTTP {r.status_code}.", flush=True)
    except Exception as exc:
        print(f"V13 EVENT JUDGE: {tag} error ({type(exc).__name__}).", flush=True)
    return None


def _related_to_published(ej, prompt):
    """True when the NEW POST of a same-event prompt shares words with any listed headline."""
    try:
        head = prompt.split("NEW POST (about to be published):", 1)[1].split("ALREADY PUBLISHED", 1)[0].strip()
        listing = prompt.split("ALREADY PUBLISHED in the last 24 hours:", 1)[1].split("Does the NEW POST", 1)[0]
        for line in listing.splitlines():
            title = re.sub(r"^\s*\d+\.\s*", "", line).strip()
            if title and ej.related(head, title):
                return True
    except Exception:
        return True  # unsure: let the strong pool look
    return False


def _install_event_judge(key):
    try:
        import v13_event_judge as ej
    except Exception:
        return False
    orig_ask = getattr(ej, "ask", None)
    if not callable(orig_ask) or getattr(orig_ask, "_v13_mistral", False):
        return True

    def ask_with_mistral(prompt, skip=""):
        text = str(prompt or "")
        cheap_first = text.startswith(JUDGE_HEAD) or text.startswith(SENSE_HEAD)
        if cheap_first and skip != f"mistral/{NEMO}":
            got = _mistral_ask(ej, key, prompt, NEMO)
            if got:
                verdict = str(got.get("verdict", "")).strip().lower()
                if (text.startswith(JUDGE_HEAD) and verdict not in ("repeat", "duplicate", "same")
                        and _related_to_published(ej, text)):
                    strong = orig_ask(prompt, skip=skip)
                    if strong:
                        return strong
                return got
        got = orig_ask(prompt, skip=skip)
        if got:
            return got
        for model in TRANSLATE_MODELS:
            tag = f"mistral/{model}"
            if tag == skip or (cheap_first and model == NEMO):
                continue
            got = _mistral_ask(ej, key, prompt, model)
            if got:
                return got
        return None

    ask_with_mistral._v13_mistral = True
    ej.ask = ask_with_mistral
    return True


def _install_nemo_editor_rules():
    """nemo's editor approvals count; its rejections are not cached and fall to the deterministic rule."""
    import v13_editor_gate as g
    if getattr(g, "_v13_nemo_rules", False):
        return
    prev_put, prev_judge = g._cache_put, g.ai_judge

    def cache_put(key, entry):
        if isinstance(entry, dict) and not entry.get("ok") and NEMO in str(entry.get("reason", "")):
            return  # judged again on a later run, when a strong model may answer
        return prev_put(key, entry)

    def ai_judge(main, candidate):
        verdict, provider = prev_judge(main, candidate)
        if verdict and NEMO in str(provider) and not g.ai_accepts(verdict, candidate):
            print(f"V13 MISTRAL: nemo reject not trusted -> deterministic rule: {str(candidate.get('title', ''))[:80]}",
                  flush=True)
            return None, ""
        return verdict, provider

    g._cache_put = cache_put
    g.ai_judge = ai_judge
    g._v13_nemo_rules = True


def _purge_nemo_rejections():
    """One time: editor-gate cache rejections made by open-mistral-nemo are dropped (see notes)."""
    try:
        import v13_ai_router as r
        health = r._load_health()
        if health.get(PURGE_MARK):
            return 0
        cache = health.get("_editor_gate_cache") or {}
        bad = [k for k, v in cache.items()
               if isinstance(v, dict) and not v.get("ok") and "open-mistral-nemo" in str(v.get("reason", ""))]
        for k in bad:
            cache.pop(k, None)
        health["_editor_gate_cache"] = cache
        health[PURGE_MARK] = int(time.time())
        r._save_health(health)
        print(f"V13 MISTRAL: {len(bad)} editor rejection(s) by open-mistral-nemo dropped from the cache "
              "(judged again by a stronger model)", flush=True)
        return len(bad)
    except Exception as exc:
        print(f"V13 MISTRAL: nemo cache purge skipped ({type(exc).__name__})", flush=True)
        return 0


def install():
    if _INSTALLED["done"]:
        return
    key = _key()
    if not key:
        print("V13 MISTRAL: no MISTRAL_API_KEY; not used", flush=True)
        return
    _install_rps_guard()
    _install_router(key)
    editor = _install_editor(key)
    ej = _install_event_judge(key)
    try:
        _install_nemo_editor_rules()
    except Exception as exc:
        print(f"V13 MISTRAL: nemo editor rules not installed ({type(exc).__name__}: {exc})", flush=True)
    _purge_nemo_rejections()
    _INSTALLED["done"] = True
    print("V13 MISTRAL ACTIVE: nemo first for duplicate/sense checks; after Groq and Gemini for translation"
          + (" + editor" if editor else "") + (" + event_judge" if ej else "") + ")", flush=True)
