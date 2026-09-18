"""
NABZ KHABAR V13 — FREE AI ROUTER
Dynamic free-tier model discovery with ordered multi-layer failover
No paid service, no billing dependency.
"""

import json
import re
import time

# Ordered free-tier candidates. The router discovers which of these are actually available for this API key.
MODEL_CANDIDATES = (
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
)
API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
AI_HEALTH_FILE = "ai_model_health.json"
MODEL_COOLDOWN_SECONDS = 15 * 60
AI_DISCOVERY_TIMEOUT = 10
AI_REQUEST_TIMEOUT = 15
_DISCOVERY_CACHE = None


def _persian_ratio(text):
    text = str(text or "")
    letters = re.findall(r"[A-Za-z\u0600-\u06ff]", text)
    if not letters:
        return 1.0
    return sum("\u0600" <= ch <= "\u06ff" for ch in letters) / len(letters)


def _clean_json(raw):
    raw = str(raw or "").strip()
    raw = re.sub(r"^\s*\`\`\`(?:json)?\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s*\`\`\`\s*$", "", raw)
    return json.loads(raw.strip())



def _load_health():
    try:
        with open(AI_HEALTH_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_health(health):
    try:
        with open(AI_HEALTH_FILE, "w", encoding="utf-8") as handle:
            json.dump(health, handle, ensure_ascii=False, indent=2, sort_keys=True)
    except Exception as exc:
        print(f"V13 AI ROUTER: health save error: {exc}")


def _model_disabled(health, model):
    try:
        until = float(health.get(model, {}).get("disabled_until", 0))
        return until > time.time()
    except Exception:
        return False


def _mark_model_failure(model, status):
    health = _load_health()
    entry = health.setdefault(model, {})
    now = int(time.time())
    cooldown = MODEL_COOLDOWN_SECONDS if status == 429 else 5 * 60
    entry["disabled_until"] = now + cooldown
    entry["last_failure"] = now
    entry["last_status"] = int(status)
    _save_health(health)
    print(f"V13 AI ROUTER: {model} circuit-open for {cooldown}s after HTTP {status}.")


def _mark_model_success(model):
    health = _load_health()
    if model in health:
        health.pop(model, None)
        _save_health(health)


def _available_models(main):
    """Return approved candidate models, caching discovery for the current run."""
    global _DISCOVERY_CACHE
    try:
        if _DISCOVERY_CACHE is not None:
            health = _load_health()
            healthy = [m for m in _DISCOVERY_CACHE if not _model_disabled(health, m)]
            if healthy:
                print("V13 AI ROUTER: using cached model discovery: " + ", ".join(healthy))
                return healthy
        
        response = main.SESSION.get(
            API_BASE,
            params={"key": main.AI_API_KEY, "pageSize": 100},
            timeout=AI_DISCOVERY_TIMEOUT,
        )
        if not response.ok:
            print(f"V13 AI ROUTER: model discovery HTTP {response.status_code}; using known candidates.")
            _DISCOVERY_CACHE = list(MODEL_CANDIDATES)
            return list(MODEL_CANDIDATES)
        data = response.json() or {}
        available = set()
        for item in data.get("models", []):
            name = str(item.get("name", "")).strip()
            short = name.split("/", 1)[1] if name.startswith("models/") else name
            actions = item.get("supportedGenerationMethods", []) or []
            if short and "generateContent" in actions:
                available.add(short)
        ordered = [m for m in MODEL_CANDIDATES if m in available]
        health = _load_health()
        healthy = [m for m in ordered if not _model_disabled(health, m)]
        if healthy:
            _DISCOVERY_CACHE = ordered
            print("V13 AI ROUTER: discovered available models: " + ", ".join(healthy))
            return healthy
        if ordered:
            _DISCOVERY_CACHE = ordered
            print("V13 AI ROUTER: all discovered models are in cooldown; trying them as last resort.")
            return ordered
        _DISCOVERY_CACHE = list(MODEL_CANDIDATES)
        print("V13 AI ROUTER: discovery returned no approved candidates; using fallback candidate list.")
        return list(MODEL_CANDIDATES)
    except Exception as exc:
        _DISCOVERY_CACHE = list(MODEL_CANDIDATES)
        print(f"V13 AI ROUTER: model discovery error: {exc}; using known candidates.")
        return list(MODEL_CANDIDATES)

def _request_json(main, model, prompt, max_output_tokens=500):
    """Return (parsed_json_or_none, retry_same_model)."""
    endpoint = f"{API_BASE}/{model}:generateContent"
    try:
        response = main.SESSION.post(
            endpoint,
            params={"key": main.AI_API_KEY},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "maxOutputTokens": max_output_tokens,
                },
            },
            timeout=AI_REQUEST_TIMEOUT,
        )
        if response.status_code == 404:
            print(f"V13 AI ROUTER: {model} HTTP 404; model unavailable, skipping it.")
            return None, False
        if response.status_code in (429, 500, 502, 503, 504):
            _mark_model_failure(model, response.status_code)
            print(f"V13 AI ROUTER: {model} HTTP {response.status_code}; retrying once, then failing over.")
            return None, True
        if not response.ok:
            print(f"V13 AI ROUTER: {model} HTTP {response.status_code}; failing over.")
            return None, False
        data = response.json()
        raw = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        try:
            return _clean_json(raw), False
        except Exception as exc:
            print(f"V13 AI ROUTER: {model} invalid JSON: {exc}; failing over.")
            return None, False
    except Exception as exc:
        print(f"V13 AI ROUTER: {model} error: {exc}; retrying once.")
        return None, True


def _numbers(main, text):
    normalized = main.normalize_digits(str(text or ""))
    return set(re.findall(r"\b\d+(?:[.,]\d+)?\b", normalized))


def _bad_meta(text):
    value = str(text or "").lower()
    return any(x in value for x in (
        "http://", "https://", "www.", "منبع:", "به گزارش",
        "طبق گزارش ما", "به گفته منابع ما", "منابع ما",
    ))


def _sentence_count(text):
    return len([
        x for x in re.split(r"(?<=[.!؟؛])\s+", str(text or "").strip())
        if x.strip()
    ])


def _validate(main, original_title, source, data, foreign):
    if not isinstance(data, dict):
        return None
    title = main.clean_title(data.get("title", ""))
    summary = main.clean_content(data.get("summary", ""))
    if not title or not summary:
        return None
    if _bad_meta(title) or _bad_meta(summary):
        return None
    if _sentence_count(summary) > 3 or len(summary) > 750:
        return None
    if not _numbers(main, title + " " + summary).issubset(_numbers(main, source)):
        return None
    if foreign:
        if _persian_ratio(title) < 0.60 or _persian_ratio(summary) < 0.60:
            return None
    else:
        if _persian_ratio(title) < 0.60 or _persian_ratio(summary) < 0.45:
            return None
    return {"title": title, "summary": summary}


def gemini_request(main, title, article_text):
    if not main.AI_API_KEY:
        return None

    source = main.clean_content(article_text or title)
    foreign = _persian_ratio(title) < 0.60

    if foreign:
        prompt = """این خبر از یک منبع خارجی است و باید برای یک کانال خبری فارسی‌زبان آماده شود.
عنوان اصلی:
%s

متن خبر:
%s

فقط اطلاعات موجود را به فارسی روان ترجمه و خلاصه کن.
- عنوان کوتاه، دقیق و خبری باشد.
- خلاصه حداکثر ۳ جمله و ۷۵۰ نویسه باشد.
- هیچ عدد، نام، ادعا یا واقعیت جدیدی اضافه نکن.
- همه اعداد موجود را فقط در صورت وجود در متن اصلی حفظ کن.
- نام شرکت‌ها، افراد و محصولات را دقیق نگه دار.
- هیچ لینک، منبع، «به گزارش» یا توضیح درباره ترجمه نده.

فقط JSON معتبر:
{"title":"تیتر فارسی","summary":"خلاصه فارسی"}""" % (title, source[:6000])
    else:
        prompt = """این خبر فارسی را برای کانال خبری حرفه‌ای بازنویسی کن.
عنوان:
%s

متن:
%s

قواعد:
- عنوان دقیق، کوتاه و خبری باشد.
- خلاصه حداکثر ۳ جمله و ۷۵۰ نویسه باشد.
- هیچ عدد، نام، ادعا یا واقعیت جدیدی اضافه نکن.
- هیچ لینک، منبع یا عبارت «به گزارش» اضافه نکن.
- فقط اطلاعات موجود در متن را حفظ کن.

فقط JSON معتبر:
{"title":"تیتر فارسی","summary":"خلاصه فارسی"}""" % (title, source[:6000])

    for model in _available_models(main):
        for attempt in range(2):
            result, retry_same_model = _request_json(main, model, prompt)
            if result:
                validated = _validate(main, title, source, result, foreign)
                if validated:
                    _mark_model_success(model)
                    print(f"V13 AI ROUTER: SUCCESS via {model}")
                    return validated
                print(f"V13 AI ROUTER: {model} returned invalid/unsafe output; failing over.")
                break
            if retry_same_model and attempt == 0:
                time.sleep(1.2)
                continue
            break

    print("V13 AI ROUTER: all free models failed; publication will use existing V13 safety rules.")
    return None


def install(main):
    main.gemini_request = lambda title, article_text: gemini_request(
        main, title, article_text
    )
    print(
        "V13 AI ROUTER ACTIVE: "
        "dynamic model discovery, strict generateContent filter, free-tier candidates only, 404-safe failover"
    )
