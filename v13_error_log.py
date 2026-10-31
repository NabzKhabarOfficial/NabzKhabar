"""NABZ V13 - record the real Telegram error for every rejected or ambiguous send.

Until now a failed publication was stored with an empty error, so the cause
of a red run could not be read. This layer watches only the three Telegram
send methods and keeps the last 100 outcomes in ai_model_health.json
(a file the workflow already persists). Tokens and URLs are never stored.

Fail-safe: logging problems never change the send result.
"""

import re
import time

import requests

STORE_KEY = "_telegram_errors"
MAX_ITEMS = 100
_SEND = re.compile(r"/bot[^/]+/(sendPhoto|sendVideo|sendMessage)(?:$|\?)")
_INSTALLED = {"done": False}


def _record(entry):
    try:
        import v13_ai_router
        health = v13_ai_router._load_health()
        items = health.get(STORE_KEY)
        if not isinstance(items, list):
            items = []
        items.append(entry)
        health[STORE_KEY] = items[-MAX_ITEMS:]
        v13_ai_router._save_health(health)
    except Exception as exc:
        print(f"V13 TELEGRAM ERROR LOG: save skipped ({type(exc).__name__})", flush=True)


def describe(response):
    status = getattr(response, "status_code", "?")
    try:
        data = response.json()
        text = str(data.get("description", "")) if isinstance(data, dict) else ""
    except Exception:
        text = str(getattr(response, "text", ""))
    return f"{status}: {text[:300]}"


def install():
    if _INSTALLED["done"]:
        return
    inner = requests.Session.request

    def wrapped(self, method, url, *args, **kwargs):
        match = _SEND.search(str(url))
        if not match:
            return inner(self, method, url, *args, **kwargs)
        name = match.group(1)
        try:
            response = inner(self, method, url, *args, **kwargs)
        except Exception as exc:
            _record({"t": time.time(), "method": name, "outcome": "ambiguous",
                     "error": f"{type(exc).__name__}: {str(exc)[:200]}"})
            raise
        if not getattr(response, "ok", True):
            _record({"t": time.time(), "method": name, "outcome": "rejected",
                     "error": describe(response)})
        return response

    requests.Session.request = wrapped
    _INSTALLED["done"] = True
    print("V13 TELEGRAM ERROR LOG ACTIVE.", flush=True)
