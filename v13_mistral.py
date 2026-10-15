"""NABZ KHABAR: Mistral's free tier as one more AI provider (Oct 15 2026).

Owner's own free Mistral account (La Plateforme free plan, no card): a different provider, not an
extra key for an existing one. Its free plan is large (about a billion tokens a month, ~1 request a
second), so it can carry the night when Groq's 200k tokens a day and Gemini's daily requests are
used up. It is used only AFTER Groq and Gemini, before OpenRouter (50 free requests a day):

1. Translation / rewrite (v13_ai_router.gemini_request): when the router reaches OpenRouter,
   Mistral (mistral-small-latest, open-mistral-nemo) is asked first with the same prompt,
   the same JSON check and the same strict content validation. (Oct 15 review: mistral-large-latest
   returned HTTP 403 tier_not_allowed on the free tier and burned the 1 req/s rate limit right
   before mistral-small-latest was called, causing HTTP 429; removed + 1.2s min gap between
   Mistral requests.)
2. Final editor (v13_ai_extra.ask_pool): mistral-small-latest is inserted before OpenRouter.
3. The AI meter counts it (_ai_usage key "mistral:<model>"); it is not paced (no daily cap).

No MISTRAL_API_KEY in the environment = nothing changes. Any error = the bot runs as before.
"""

import os
import sys
import time

MISTRAL_BASE = "https://api.mistral.ai/v1"
TRANSLATE_MODELS = ("mistral-small-latest", "open-mistral-nemo")
EDITOR_MODEL = "mistral-small-latest"
MIN_INTERVAL_SEC = 1.25  # La Plateforme free tier is ~1 req/s across the account
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
        item = ("mistral/" + EDITOR_MODEL, "mistral:" + EDITOR_MODEL, lambda: oa_raw(
            session, MISTRAL_BASE + "/chat/completions", key, EDITOR_MODEL, prompt, max_tokens,
            timeout=timeout))
        pos = next((i for i, x in enumerate(out) if str(x[0]).startswith("openrouter")), len(out))
        out.insert(pos, item)
        return out

    with_mistral._v13_mistral = True
    extra._attempts = with_mistral
    return True


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
    _INSTALLED["done"] = True
    print("V13 MISTRAL ACTIVE: free Mistral after Groq and Gemini, before OpenRouter (translation"
          + (" + editor" if editor else "") + ")", flush=True)
