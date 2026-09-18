"""
NABZ KHABAR V13 — FREE AI ROUTER
Primary: Gemini 2.5 Flash-Lite (small, high-volume, free-tier friendly)
Fallback: Gemini 3.1 Flash-Lite
No paid service, no billing dependency.
"""

import json
import re
import time

PRIMARY_MODEL = "gemini-2.5-flash-lite"
FALLBACK_MODEL = "gemini-3.1-flash-lite"
API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


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


def _request_json(main, model, prompt, max_output_tokens=500):
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
            print(f"V13 AI ROUTER: {model} HTTP 404 (model unavailable for this API key/project); trying fallback.")
            return None
        if response.status_code in (429, 500, 502, 503, 504):
            print(f"V13 AI ROUTER: {model} HTTP {response.status_code}; trying next model.")
            return None
        if not response.ok:
            print(f"V13 AI ROUTER: {model} HTTP {response.status_code}; trying next model.")
            return None
        data = response.json()
        raw = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        return _clean_json(raw)
    except Exception as exc:
        print(f"V13 AI ROUTER: {model} error: {exc}")
        return None


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

    for model in (PRIMARY_MODEL, FALLBACK_MODEL):
        for attempt in range(2):
            result = _request_json(main, model, prompt)
            if result:
                validated = _validate(main, title, source, result, foreign)
                if validated:
                    print(f"V13 AI ROUTER: SUCCESS via {model}")
                    return validated
                print(f"V13 AI ROUTER: {model} returned invalid/unsafe output.")
                break
            if attempt == 0:
                time.sleep(1.2)

    print("V13 AI ROUTER: all free models failed; publication will use existing V13 safety rules.")
    return None


def install(main):
    main.gemini_request = lambda title, article_text: gemini_request(
        main, title, article_text
    )
    print(
        "V13 AI ROUTER ACTIVE: "
        f"primary={PRIMARY_MODEL}, fallback={FALLBACK_MODEL}, free-only"
    )
