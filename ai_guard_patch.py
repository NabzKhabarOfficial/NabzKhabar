"""Safety guard for Gemini rewrites.

Prevents a bad/short Gemini response from replacing a real source headline
with an unrelated headline. No extra API calls or paid services are used.
"""

import re
import main

_ORIGINAL_GEMINI_REQUEST = main.gemini_request

_GENERIC = {
    "خبر", "گزارش", "اعلام", "آخرین", "جدید", "مهم", "تازه", "واکنش", "اظهارات",
    "مواضع", "توضیح", "انتقاد", "تاکید", "تأکید", "گفت", "گفتند", "کرد", "کردند",
    "شد", "شدند", "خواهد", "می", "شود", "است", "هست", "این", "آن", "یک", "از",
    "به", "در", "با", "برای", "و", "که", "را", "تا", "بر", "های", "ها", "هم", "نیز",
    "مورد", "درباره", "تصمیم", "انتشار", "کرده", "شده", "شود",
}


def _norm(text):
    text = main.normalize_digits(str(text or "")).lower()
    text = text.replace("ي", "ی").replace("ى", "ی").replace("ك", "ک")
    text = text.replace("‌", " ")
    text = re.sub(r"[\u200b-\u200f\ufeff]", " ", text)
    text = re.sub(r"[،؛,:.!؟()\[\]{}\"'«»/\\|_–—-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokens(text):
    return {x for x in _norm(text).split() if len(x) >= 2 and x not in _GENERIC}


def _numbers(text):
    return set(re.findall(r"\d+(?:[.,٬]\d+)*", main.normalize_digits(str(text or ""))))


def _topic_match(source_title, source_body, generated_title):
    """Conservative lexical/entity guard; True means Gemini stayed on topic."""
    source = f"{source_title} {source_body}"
    src = _tokens(source)
    gen = _tokens(generated_title)
    if not gen:
        return False

    common = src & gen

    # Preserve important numbers and named entities when present.
    src_nums = _numbers(source)
    gen_nums = _numbers(generated_title)
    if gen_nums and src_nums and not (gen_nums & src_nums):
        return False

    # A short source is exactly where the previous bug occurred. Require a
    # meaningful overlap with the source title; never let a thin RSS snippet
    # authorize a completely new topic.
    if len(main.clean_content(source_body)) < 400:
        title_tokens = _tokens(source_title)
        title_common = title_tokens & gen
        if len(title_common) >= 2:
            return True
        if len(title_common) == 1 and len(title_tokens) <= 3:
            return True
        return False

    if len(common) >= 3:
        return True

    if len(common) >= 2:
        containment = len(common) / max(1, min(len(src), len(gen)))
        return containment >= 0.50

    return False


def _safe_result(original_title, original_body, result):
    if not isinstance(result, dict):
        return {
            "title": main.clean_title(original_title),
            "summary": main.enforce_short_summary(original_body),
        }

    generated_title = main.clean_title(result.get("title", ""))
    generated_summary = main.clean_content(result.get("summary", ""))

    if not generated_title or not _topic_match(original_title, original_body, generated_title):
        print("REJECTED GEMINI TITLE: topic mismatch; using source title")
        safe_title = main.clean_title(original_title)
        safe_summary = main.enforce_short_summary(original_body)
        return {"title": safe_title, "summary": safe_summary}

    # If Gemini produced a title on-topic but a clearly unrelated summary,
    # keep the safe source summary rather than publishing invented context.
    if generated_summary and not _topic_match(original_title, original_body, generated_title + " " + generated_summary):
        print("REJECTED GEMINI SUMMARY: topic mismatch; using source summary")
        generated_summary = main.enforce_short_summary(original_body)

    return {
        "title": generated_title,
        "summary": generated_summary or main.enforce_short_summary(original_body),
    }


def guarded_gemini_request(title, article_text):
    try:
        result = _ORIGINAL_GEMINI_REQUEST(title, article_text)
    except Exception as exc:
        print(f"Gemini guard fallback after request error: {exc}")
        return {
            "title": main.clean_title(title),
            "summary": main.enforce_short_summary(article_text),
        }

    return _safe_result(title, article_text, result)


main.gemini_request = guarded_gemini_request
print("Gemini topic guard: enabled")
