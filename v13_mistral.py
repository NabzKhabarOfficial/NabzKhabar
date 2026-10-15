"""NABZ KHABAR: Mistral's free tier as one more AI provider (Oct 15 2026).

Owner's own free Mistral account (La Plateforme free plan, no card): a different provider, not an
extra key for an existing one. Its free plan is large (about a billion tokens a month, ~1 request a
second), so it can carry the night when Groq's 200k tokens a day and Gemini's daily requests are
used up. It is used only AFTER Groq and Gemini, before OpenRouter (50 free requests a day):

1. Translation / rewrite (v13_ai_router.gemini_request): when the router reaches OpenRouter,
   Mistral (mistral-large-latest, then mistral-small-latest) is asked first with the same prompt,
   the same JSON check and the same strict content validation.
2. Final editor (v13_ai_extra.ask_pool): mistral-small-latest is inserted before OpenRouter.
3. The AI meter counts it (_ai_usage key "mistral:<model>"); it is not paced (no daily cap).

No MISTRAL_API_KEY in the environment = nothing changes. Any error = the bot runs as before.
"""

import os
import sys

MISTRAL_BASE = "https://api.mistral.ai/v1"
TRANSLATE_MODELS = ("mistral-large-latest", "mistral-small-latest")
EDITOR_MODEL = "mistral-small-latest"
_INSTALLED = {"done": False}


def _key():
    return os.getenv("MISTRAL_API_KEY", "").strip()


def _install_router(key):
    import v13_ai_router as r
    previous = r._fallback_provider_request
    if getattr(previous, "_v13_mistral", False):
        return

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
    _install_router(key)
    editor = _install_editor(key)
    _INSTALLED["done"] = True
    print("V13 MISTRAL ACTIVE: free Mistral after Groq and Gemini, before OpenRouter (translation"
          + (" + editor" if editor else "") + ")", flush=True)
