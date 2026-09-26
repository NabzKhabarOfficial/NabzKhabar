"""
NABZ KHABAR V13 — FREE AI ROUTER
Dynamic free-tier model discovery with ordered multi-layer failover
No paid service, no billing dependency.
"""

import json
import os
import re
import time

# Low-cost/free-tier Gemini candidates, ordered from lighter to stronger.
# The router discovers which models are actually available for this API key.
MODEL_CANDIDATES = (
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
)
API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
AI_HEALTH_FILE = "ai_model_health.json"
MODEL_COOLDOWN_SECONDS = 5 * 60

# Multi-provider free-tier AI pool.
# Providers are optional: a missing secret never stops the news pipeline.
# Order is intentional: Groq -> Gemini (light models) -> OpenRouter.
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_BASE = "https://api.groq.com/openai/v1"
GROQ_MODELS = (
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
ENABLE_OPENROUTER_FALLBACK = os.getenv("ENABLE_OPENROUTER_FALLBACK", "1").strip() == "1"
OPENROUTER_MODELS_CACHE_SECONDS = 15 * 60
_openrouter_models_cache = {"at": 0.0, "models": []}


def _persian_ratio(text):
    text = str(text or "")
    letters = re.findall(r"[A-Za-z\u0600-\u06ff]", text)
    if not letters:
        return 1.0
    return sum("\u0600" <= ch <= "\u06ff" for ch in letters) / len(letters)


def _clean_json(raw):
    """Parse provider JSON even when a free model wraps it in prose/code fences."""
    raw = str(raw or "").strip()
    raw = re.sub(r"^\s*\`\`\`(?:json)?\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s*\`\`\`\s*$", "", raw)
    try:
        return json.loads(raw.strip())
    except Exception:
        # Some free models emit a short preamble around the JSON. Extract the
        # first balanced top-level JSON object instead of rejecting it.
        start = raw.find("{")
        if start < 0:
            raise
        depth = 0
        in_string = False
        escaped = False
        for idx in range(start, len(raw)):
            ch = raw[idx]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(raw[start:idx + 1])
        raise



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
    """Return candidate models that this exact API key advertises for generateContent."""
    try:
        response = main.SESSION.get(
            API_BASE,
            params={"key": main.AI_API_KEY, "pageSize": 100},
            timeout=20,
        )
        if not response.ok:
            print(f"V13 AI ROUTER: model discovery HTTP {response.status_code}; using known candidates.")
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
        healthy = [m for m in ordered if not _model_disabled(health, f"gemini:{m}")]
        if healthy:
            print("V13 AI ROUTER: discovered available models: " + ", ".join(healthy))
            return healthy
        if ordered:
            print("V13 AI ROUTER: all discovered models are in cooldown; trying them as last resort.")
            return ordered
        print("V13 AI ROUTER: discovery returned no approved candidates; using fallback candidate list.")
        return list(MODEL_CANDIDATES)
    except Exception as exc:
        print(f"V13 AI ROUTER: model discovery error: {exc}; using known candidates.")
        return list(MODEL_CANDIDATES)

def _request_json(main, model, prompt, max_output_tokens=500):
    """One Gemini attempt; provider health is tracked independently."""
    endpoint = f"{API_BASE}/{model}:generateContent"
    health_key = f"gemini:{model}"
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
            timeout=30,
        )
        if response.status_code == 404:
            print(f"V13 AI ROUTER: {model} HTTP 404; model unavailable, skipping it.")
            return None, False
        if response.status_code in (429, 500, 502, 503, 504):
            _mark_model_failure(health_key, response.status_code)
            print(f"V13 AI ROUTER: {model} HTTP {response.status_code}; failing over without retry.")
            return None, False
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
        print(f"V13 AI ROUTER: {model} error: {exc}; failing over without retry.")
        return None, False



def _openai_compatible_json(main, provider, base_url, api_key, model, prompt, max_output_tokens=500):
    """One provider attempt. Provider failures are isolated and never abort V13."""
    endpoint = f"{base_url}/chat/completions"
    health_key = f"{provider.lower()}:{model}"
    try:
        response = main.SESSION.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "NabzKhabar-V13/1.0",
            },
            json={
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": "خروجی فقط یک JSON معتبر با دو کلید title و summary باشد؛ هیچ متن دیگری تولید نکن.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "max_tokens": max_output_tokens,
            },
            timeout=30,
        )
        if response.status_code == 400:
            detail = str(getattr(response, "text", "") or "").replace("\n", " ")[:500]
            print(f"V13 AI ROUTER: {provider}/{model} HTTP 400; provider rejected request: {detail}")
            _mark_model_failure(health_key, 400)
            return None, False
        if response.status_code == 404:
            print(f"V13 AI ROUTER: {provider}/{model} HTTP 404; skipping.")
            _mark_model_failure(health_key, 404)
            return None, False
        if response.status_code in (401, 403):
            print(f"V13 AI ROUTER: {provider} authentication/permission HTTP {response.status_code}; skipping.")
            _mark_model_failure(health_key, response.status_code)
            return None, False
        if response.status_code in (429, 500, 502, 503, 504):
            _mark_model_failure(health_key, response.status_code)
            print(f"V13 AI ROUTER: {provider}/{model} HTTP {response.status_code}; failing over without retry.")
            return None, False
        if not response.ok:
            print(f"V13 AI ROUTER: {provider}/{model} HTTP {response.status_code}; failing over.")
            _mark_model_failure(health_key, response.status_code)
            return None, False
        data = response.json() or {}
        raw = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        if isinstance(raw, list):
            raw = "".join(str(x.get("text", "")) if isinstance(x, dict) else str(x) for x in raw)
        try:
            result = _clean_json(raw)
        except Exception as exc:
            print(f"V13 AI ROUTER: {provider}/{model} invalid JSON: {exc}; failing over.")
            _mark_model_failure(health_key, 422)
            return None, False
        _mark_model_success(health_key)
        return result, False
    except Exception as exc:
        print(f"V13 AI ROUTER: {provider}/{model} error: {exc}; failing over.")
        _mark_model_failure(health_key, 599)
        return None, False

def _openrouter_free_models(main):
    """Discover OpenRouter's currently listed zero-cost chat models."""
    global _openrouter_models_cache
    now = time.time()
    if now - float(_openrouter_models_cache.get("at", 0)) < OPENROUTER_MODELS_CACHE_SECONDS:
        return list(_openrouter_models_cache.get("models", []))
    try:
        response = main.SESSION.get(
            f"{OPENROUTER_BASE}/models",
            timeout=15,
            headers={"User-Agent": "NabzKhabar-V13/1.0"},
        )
        if not response.ok:
            print(f"V13 AI ROUTER: OpenRouter model discovery HTTP {response.status_code}; skipping provider.")
            return []
        models = []
        for item in (response.json() or {}).get("data", []):
            model_id = str(item.get("id", "")).strip()
            pricing = item.get("pricing") or {}
            if not model_id.endswith(":free"):
                continue
            if str(pricing.get("prompt", "")).strip() not in ("0", "0.0", "0.00"):
                continue
            if str(pricing.get("completion", "")).strip() not in ("0", "0.0", "0.00"):
                continue
            supported = item.get("supported_parameters") or []
            priority = 0 if "response_format" in supported else 10
            if any(x in model_id.lower() for x in ("qwen", "llama", "gemma", "mistral")):
                priority -= 2
            models.append((priority, model_id))
        models.sort(key=lambda x: (x[0], x[1]))
        selected = [model_id for _, model_id in models[:8]]
        _openrouter_models_cache = {"at": now, "models": selected}
        print("V13 AI ROUTER: OpenRouter free models: " + (", ".join(selected) if selected else "none"))
        return selected
    except Exception as exc:
        print(f"V13 AI ROUTER: OpenRouter discovery error: {exc}; skipping provider.")
        return []


def _fallback_provider_request(main, provider, models, base_url, api_key, prompt, title, source, foreign):
    if not api_key:
        print(f"V13 AI ROUTER: {provider} unavailable (missing API key).")
        return None
    health = _load_health()
    for model in models:
        health_key = f"{provider.lower()}:{model}"
        if _model_disabled(health, health_key):
            print(f"V13 AI ROUTER: {provider}/{model} is in cooldown; skipping.")
            continue
        result, _ = _openai_compatible_json(main, provider, base_url, api_key, model, prompt)
        if result:
            validated = _validate(main, title, source, result, foreign)
            if validated:
                print(f"V13 AI ROUTER: SUCCESS via {provider}/{model}")
                return validated
            print(f"V13 AI ROUTER: {provider}/{model} returned invalid/unsafe output; failing over.")
            _mark_model_failure(health_key, 422)
    return None

def _numbers(main, text):
    normalized = main.normalize_digits(str(text or ""))
    return set(re.findall(r"\b\d+(?:[.,]\d+)?\b", normalized))


TRANSLATION_QUALITY_BAD_PATTERNS = (
    # Known machine-translation artifacts observed in production logs.
    re.compile(r"(?<![\u0600-\u06ff])تحق(?![\u0600-\u06ff])", re.I),
    re.compile(r"اطلاعات(?:\s|‌)+کارکنان.{0,80}(?:می\s*توان|میتوان).{0,30}(?:دانست|در\s*نظر)", re.I),
    # Known machine-translation artifacts observed in production logs.
    # These are deliberately narrow: they block malformed Persian phrasing,
    # not legitimate foreign names or ordinary news vocabulary.
    re.compile(r"برچسب(?:\s|‌)+(?:های|ها)(?:\s|‌).{0,45}(?:رهبر|سیل|دولت|کشور)", re.I),
    re.compile(r"جنگ(?:\s|‌)+به(?:\s|‌)+جهان", re.I),
    re.compile(r"(?:در انگلیسای|انگلیسای|ثی پلوگ|خاکستری گری|تی آی خاکستری)", re.I),
    # Production artifacts observed in the final Telegram output. These are
    # not valid Persian spellings and must never reach publication.
    re.compile(r"پیزیسلکیان|پیزیشکیان|پیزشکیلیان", re.I),
    re.compile(r"منبع\s*تصویر|عنوان\s*[,،:]|بست\s+به\s+روز\s+رسانی|منتشر\s+شده\s+\d{1,2}\s+سپتامبر", re.I),
    # Reject webpage/navigation chrome leaked by scraped international pages.
    re.compile(r"گوش\s+دادن\s*\(\s*\d+\s*دقیقه", re.I),
    re.compile(r"صرفه\s*جویی|رسانه\s*های\s*اجتماعی", re.I),
    re.compile(r"(?:به|در)\s+الجزیره\b.*?(?:کارکنان|افپ|ا\s*پ)", re.I),
    re.compile(r"\b(\S+)\s+\1\b", re.I),
    re.compile(r"(?:بی\s*بی\s*سی){2,}|(?:لندن){2,}", re.I),
    re.compile(r"\b(\S+)\s+\1\s+\1\b", re.I),
)


def _translation_quality_bad(text):
    value = str(text or "").strip()
    if not value:
        return True
    for pattern in TRANSLATION_QUALITY_BAD_PATTERNS:
        if pattern.search(value):
            return True
    # Do not reject ordinary Persian because of short function words such as
    # «به»، «در»، «که»، «از». Only flag dense one-letter fragments.
    words = [x.strip("،؛:!?()[]{}«»'") for x in re.split(r"\s+", value) if x]
    one_char = [x for x in words if len(x) == 1 and re.search(r"[\u0600-\u06ff]", x)]
    if len(words) >= 12 and len(one_char) >= 4:
        return True
    return False


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
    if _translation_quality_bad(title) or _translation_quality_bad(summary):
        print("V13 AI ROUTER: translation quality gate rejected malformed Persian output.")
        print(f"V13 AI ROUTER: rejected title={title[:180]!r}")
        print(f"V13 AI ROUTER: rejected summary={summary[:500]!r}")
        return None
    if _sentence_count(summary) > 3 or len(summary) > 750:
        return None
    if not _numbers(main, title + " " + summary).issubset(_numbers(main, source)):
        return None
    # Persian-only publication contract: do not allow stray English
    # words such as "the" to survive into the final Telegram post.
    latin_title = re.findall(r"(?<![A-Za-z])[A-Za-z]{2,}(?![A-Za-z])", title)
    latin_summary = re.findall(r"(?<![A-Za-z])[A-Za-z]{2,}(?![A-Za-z])", summary)
    allowed_brand = {"NABZ"}
    if any(x.upper() not in allowed_brand for x in latin_title + latin_summary):
        return None

    if foreign:
        if _persian_ratio(title) < 0.60 or _persian_ratio(summary) < 0.60:
            return None
    else:
        if _persian_ratio(title) < 0.60 or _persian_ratio(summary) < 0.45:
            return None
    return {"title": title, "summary": summary}


def gemini_request(main, title, article_text):
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
- هیچ لینک، منبع، «به گزارش» یا توضیح درباره ترجمه نده.
- نام افراد، کشورها و سازمان‌ها را دقیق حفظ کن.
- فقط JSON معتبر:
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

    # Free AI pool only. No local machine-translation fallback.
    result = _fallback_provider_request(
        main, "Groq", GROQ_MODELS, GROQ_BASE, GROQ_API_KEY,
        prompt, title, source, foreign
    )
    if result:
        return result

    for model in _available_models(main):
        health_key = f"gemini:{model}"
        if _model_disabled(_load_health(), health_key):
            print(f"V13 AI ROUTER: Gemini/{model} is in cooldown; skipping.")
            continue
        result, _ = _request_json(main, model, prompt)
        if result:
            validated = _validate(main, title, source, result, foreign)
            if validated:
                _mark_model_success(health_key)
                print(f"V13 AI ROUTER: SUCCESS via Gemini/{model}")
                return validated
            print(f"V13 AI ROUTER: Gemini/{model} returned invalid/unsafe output; failing over.")
            _mark_model_failure(health_key, 422)

    if ENABLE_OPENROUTER_FALLBACK and OPENROUTER_API_KEY:
        result = _fallback_provider_request(
            main, "OpenRouter", _openrouter_free_models(main), OPENROUTER_BASE,
            OPENROUTER_API_KEY, prompt, title, source, foreign
        )
        if result:
            return result
    else:
        print("V13 AI ROUTER: OpenRouter free fallback unavailable (missing key or disabled).")

    print("V13 AI ROUTER: all configured free AI providers failed; publication blocked.")
    return None

def install(main):
    main.gemini_request = lambda title, article_text: gemini_request(
        main, title, article_text
    )
    print(
        "V13 AI ROUTER ACTIVE: multi-provider free AI pool with strict validation and no machine-translation fallback"
    )
