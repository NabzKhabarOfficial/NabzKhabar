"""Strict AI output guard for NabzKhabar.

Gemini may rewrite wording, but it must not change the story or attach a
summary from another article. No extra API calls or paid services are used.
"""

import re
import main

_ORIGINAL_GEMINI_REQUEST = main.gemini_request

_GENERIC = {
    "خبر", "گزارش", "اعلام", "آخرین", "جدید", "مهم", "تازه", "واکنش", "اظهارات",
    "مواضع", "توضیح", "انتقاد", "تاکید", "تأکید", "گفت", "گفتند", "کرد", "کردند",
    "شد", "شدند", "خواهد", "می", "شود", "است", "هست", "این", "آن", "یک", "از",
    "به", "در", "با", "برای", "و", "که", "را", "تا", "بر", "های", "ها", "هم", "نیز",
    "مورد", "درباره", "تصمیم", "انتشار", "کرده", "شده", "شود", "ایران", "آمریکا",
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


def _overlap(a, b):
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0, 0, 0.0
    common = ta & tb
    containment = len(common) / max(1, min(len(ta), len(tb)))
    return len(common), len(ta), containment


def _topic_match(source_title, source_body, generated_title):
    src = _tokens(f"{source_title} {source_body}")
    gen = _tokens(generated_title)
    if not gen:
        return False

    common = src & gen
    src_nums = _numbers(f"{source_title} {source_body}")
    gen_nums = _numbers(generated_title)
    if gen_nums and src_nums and not (gen_nums & src_nums):
        return False

    title_tokens = _tokens(source_title)
    title_common = title_tokens & gen

    if len(main.clean_content(source_body)) < 400:
        return len(title_common) >= 2 or (len(title_common) == 1 and len(title_tokens) <= 3)

    if len(title_common) >= 2:
        return True
    if len(common) >= 3:
        return True
    if len(common) >= 2 and len(common) / max(1, min(len(src), len(gen))) >= 0.50:
        return True
    return False


def _summary_matches_title(source_title, generated_title, generated_summary):
    """A summary must visibly belong to the final headline."""
    title_tokens = _tokens(f"{source_title} {generated_title}")
    summary_tokens = _tokens(generated_summary)
    if not title_tokens or not summary_tokens:
        return False
    common = title_tokens & summary_tokens
    # Two meaningful title/entity words is the normal case. One is acceptable
    # only when it is a long distinctive word (e.g. Einstein/Manhattan).
    if len(common) >= 2:
        return True
    return any(len(w) >= 6 for w in common)


def _summary_matches_source(source_body, generated_summary):
    """Reject a summary that clearly belongs to another article."""
    source_tokens = _tokens(source_body)
    summary_tokens = _tokens(generated_summary)
    if not source_tokens or not summary_tokens:
        return False
    common = source_tokens & summary_tokens
    containment = len(common) / max(1, len(summary_tokens))
    return len(common) >= 3 and containment >= 0.20


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
        generated_title = main.clean_title(original_title)
        generated_summary = main.enforce_short_summary(original_body)

    # The previous guard validated the title but could still allow a summary
    # from a different story. This is the critical second half of the guard.
    if generated_summary:
        if not _summary_matches_title(original_title, generated_title, generated_summary):
            print("REJECTED GEMINI SUMMARY: title-summary mismatch; using source summary")
            generated_summary = main.enforce_short_summary(original_body)
        elif not _summary_matches_source(original_body, generated_summary):
            print("REJECTED GEMINI SUMMARY: source-body mismatch; using source summary")
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
print("Gemini strict title/body guard: enabled")
