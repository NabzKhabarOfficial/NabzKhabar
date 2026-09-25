"""
NABZ KHABAR V13 — FREE AI ROUTER
Dynamic free-tier model discovery with ordered multi-layer failover
No paid service, no billing dependency.
"""

import json
import os
import re
import time

# Ordered free-tier candidates. The router discovers which of these are actually available for this API key.
MODEL_CANDIDATES = (
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.6-flash",
)
API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
AI_HEALTH_FILE = "ai_model_health.json"
MODEL_COOLDOWN_SECONDS = 15 * 60

# Optional OpenRouter free-only fallback. Never selects paid models.
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
        healthy = [m for m in ordered if not _model_disabled(health, m)]
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
            timeout=30,
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



def _openai_compatible_json(main, provider, base_url, api_key, model, prompt, max_output_tokens=500):
    endpoint = f"{base_url}/chat/completions"
    try:
        response = main.SESSION.post(
            endpoint,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "User-Agent": "NabzKhabar-V13/1.0"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "خروجی فقط JSON معتبر با دو کلید title و summary باشد."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "max_completion_tokens": max_output_tokens,
                "response_format": {"type": "json_object"},
                "include_reasoning": False,
            },
            timeout=30,
        )
        if response.status_code == 404:
            print(f"V13 AI ROUTER: {provider}/{model} HTTP 404; skipping.")
            return None, False
        if response.status_code in (401, 403):
            print(f"V13 AI ROUTER: {provider} authentication/permission HTTP {response.status_code}; disabled for this run.")
            return None, False
        if response.status_code in (429, 500, 502, 503, 504):
            print(f"V13 AI ROUTER: {provider}/{model} HTTP {response.status_code}; failing over.")
            return None, False
        if not response.ok:
            print(f"V13 AI ROUTER: {provider}/{model} HTTP {response.status_code}; failing over.")
            return None, False
        data = response.json() or {}
        raw = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        try:
            return _clean_json(raw), False
        except Exception as exc:
            print(f"V13 AI ROUTER: {provider}/{model} invalid JSON: {exc}; failing over.")
            return None, False
    except Exception as exc:
        print(f"V13 AI ROUTER: {provider}/{model} error: {exc}; failing over.")
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
        return None
    for model in models:
        for attempt in range(2):
            result, retry_same_model = _openai_compatible_json(
                main, provider, base_url, api_key, model, prompt
            )
            if result:
                validated = _validate(main, title, source, result, foreign)
                if validated:
                    print(f"V13 AI ROUTER: SUCCESS via {provider}/{model}")
                    return validated
                print(f"V13 AI ROUTER: {provider}/{model} returned invalid/unsafe output; failing over.")
                break
            if retry_same_model and attempt == 0:
                time.sleep(1.2)
                continue
            break
    return None

def _numbers(main, text):
    normalized = main.normalize_digits(str(text or ""))
    return set(re.findall(r"\b\d+(?:[.,]\d+)?\b", normalized))


TRANSLATION_QUALITY_BAD_PATTERNS = (
    # Known machine-translation artifacts observed in production logs.
    # These are deliberately narrow: they block malformed Persian phrasing,
    # not legitimate foreign names or ordinary news vocabulary.
    re.compile(r"برچسب(?:\s|‌)+(?:های|ها)(?:\s|‌).{0,45}(?:رهبر|سیل|دولت|کشور)", re.I),
    re.compile(r"جنگ(?:\s|‌)+به(?:\s|‌)+جهان", re.I),
    re.compile(r"(?:در انگلیسای|انگلیسای|ثی پلوگ|خاکستری گری|تی آی خاکستری)", re.I),
    re.compile(r"\b(\S+)\s+\1\s+\1\b", re.I),
)


def _translation_quality_bad(text):
    value = str(text or "").strip()
    if not value:
        return True
    for pattern in TRANSLATION_QUALITY_BAD_PATTERNS:
        if pattern.search(value):
            return True
    # A title with an excessive number of very short fragments is usually a
    # broken literal translation rather than a normal Persian news headline.
    words = [x for x in re.split(r"\s+", value) if x]
    if len(words) >= 10 and sum(len(x) <= 2 for x in words) >= 5:
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


def _argos_foreign_translation(title, source):
    """Primary non-AI localization path for English foreign stories."""
    try:
        from v13_argos_translate import translate_foreign_story
        result = translate_foreign_story(title, source)
        if result:
            print("V13 AI ROUTER: foreign story translated via local Argos Translate.")
            return result
    except Exception as exc:
        print(f"V13 AI ROUTER: Argos layer error; continuing to AI fallback: {exc}")
    return None


def gemini_request(main, title, article_text):
    # For foreign stories, try the local Argos en->fa engine first.
    # This makes translation independent of quotas and avoids publishing a
    # fluent-looking but semantically broken AI translation. AI providers
    # remain the fallback when Argos is unavailable or fails validation.

    source = main.clean_content(article_text or title)
    foreign = _persian_ratio(title) < 0.60

    argos_result = None
    if foreign:
        argos_result = _argos_foreign_translation(title, source)
        if argos_result:
            validated_argos = _validate(main, title, source, argos_result, foreign)
            if validated_argos:
                print("V13 AI ROUTER: foreign story accepted via local Argos before AI fallback.")
                return validated_argos
            print("V13 AI ROUTER: Argos output failed publication-quality validation; trying AI fallback.")

        # AI is the quality fallback when local translation is unavailable.
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
- در خروجی از الفبای لاتین استفاده نکن؛ نام شرکت‌ها و محصولات را نیز به شکل فارسی‌نویسی‌شده بیاور.

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
- در خروجی از الفبای لاتین استفاده نکن؛ نام شرکت‌ها و محصولات را نیز به شکل فارسی‌نویسی‌شده بیاور.
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
                    print(f"V13 AI ROUTER: SUCCESS via Gemini/{model}")
                    return validated
                print(f"V13 AI ROUTER: Gemini/{model} returned invalid/unsafe output; failing over.")
                break
            if retry_same_model and attempt == 0:
                time.sleep(1.2)
                continue
            break

    if ENABLE_OPENROUTER_FALLBACK and OPENROUTER_API_KEY:
        result = _fallback_provider_request(
            main, "OpenRouter", _openrouter_free_models(main), OPENROUTER_BASE,
            OPENROUTER_API_KEY, prompt, title, source, foreign
        )
        if result:
            return result
    else:
        print("V13 AI ROUTER: OpenRouter free fallback unavailable (missing key or disabled).")

    # Final fallback: local Argos Translate, after all AI providers fail.
    if foreign:
        if not argos_result:
            argos_result = _argos_foreign_translation(title, source)
        if argos_result:
            # Argos has its own dedicated safety validation. Do not run the
            # stricter AI numeric validator again: it compares explicit digits
            # only, while Argos legitimately converts written English numbers
            # into Persian words/digits. Re-validating here caused valid Argos
            # translations to be discarded and the story to be reported as
            # "AI localization unavailable".
            def _sanitize_argos_text(value):
                text = str(value or "")
                # Argos can translate source-page metadata along with the article.
                # Remove navigation/source artifacts instead of discarding an
                # otherwise valid Persian emergency translation.
                text = re.sub(r"https?://\S+|www\.\S+", " ", text, flags=re.I)
                # Remove source/navigation labels on their own line or inline.
                text = re.sub(
                    r"(?:^|[\n|])\s*(?:منبع|source|منبع خبر|لینک|link)\s*[:：].*$",
                    " ",
                    text,
                    flags=re.I | re.M,
                )
                text = re.sub(
                    r"\s+(?:منبع|source|منبع خبر|لینک|link)\s*[:：].*$",
                    " ",
                    text,
                    flags=re.I,
                )
                text = re.sub(r"\s+", " ", text).strip()
                return text

            argos_title = main.clean_title(_sanitize_argos_text(argos_result.get("title", "")))
            argos_summary = main.clean_content(_sanitize_argos_text(argos_result.get("summary", "")))
            # Argos already passed its dedicated translation safety checks.
            # Keep only publication-level structural/language checks here.
            # Do not apply AI-specific content heuristics to the local fallback.
            argos_reasons = []
            if not argos_title:
                argos_reasons.append("empty-title")
            if not argos_summary:
                argos_reasons.append("empty-summary")
            if _persian_ratio(argos_title) < 0.60:
                argos_reasons.append("title-not-persian")
            if _persian_ratio(argos_summary) < 0.60:
                argos_reasons.append("summary-not-persian")
            # Argos translations may legitimately contain Persian prose such as
            # «به گزارش ...» when that phrase exists in the source. The generic
            # AI metadata gate treats that phrase as metadata and was therefore
            # discarding otherwise valid fallback translations. At this stage
            # only block actual URL/source-label artifacts that should never
            # survive the sanitizer above.
            def _argos_bad_meta(value):
                text = str(value or "")
                if re.search(r"https?://\S+|www\.\S+", text, flags=re.I):
                    return True
                return bool(re.search(
                    r"(?:^|[\n|])\s*(?:منبع|source|منبع خبر|لینک|link)\s*[:：]",
                    text,
                    flags=re.I,
                ))
            if _argos_bad_meta(argos_title) or _argos_bad_meta(argos_summary):
                argos_reasons.append("metadata")
            if _sentence_count(argos_summary) > 3:
                argos_reasons.append("too-many-sentences")
            if len(argos_summary) > 750:
                argos_reasons.append("too-long")
            if argos_reasons:
                print("V13 AI ROUTER: Argos final safety blocked: " + ", ".join(argos_reasons))
            else:
                print("V13 AI ROUTER: SUCCESS via Argos Translate (final fallback).")
                return {"title": argos_title, "summary": argos_summary}

    print("V13 AI ROUTER: Gemini/OpenRouter failed; Argos unavailable or rejected; publication will use existing V13 safety rules.")
    return None


def install(main):
    main.gemini_request = lambda title, article_text: gemini_request(
        main, title, article_text
    )
    print(
        "V13 AI ROUTER ACTIVE: "
        "multi-provider free router: Gemini -> OpenRouter :free -> Argos, strict validation, 404-safe failover"
    )
