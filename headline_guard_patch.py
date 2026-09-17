"""Headline cleanup guard for Gemini-generated Persian headlines.

Removes obvious short garbage prefixes accidentally emitted before an otherwise
valid headline. It does not make another API call and uses no paid service.
"""

import re
import main

_ORIGINAL_GEMINI_REQUEST = main.gemini_request

_VALID_SHORT_LEADS = {
    "در", "به", "از", "با", "بر", "پس", "که", "این", "آن", "یک", "هر",
    "هم", "تا", "می", "را", "یا", "نه", "و", "اما", "اگر", "برای", "روی",
}


def _clean_generated_title(title):
    title = main.clean_title(title)
    if not title:
        return title

    # Fix duplicated fragments such as: «مح محورهای ...» -> «محورهای ...».
    m = re.match(r"^([\u0600-\u06ff]{1,3})\s+\1([\u0600-\u06ff]+)(.*)$", title)
    if m:
        title = m.group(1) + m.group(2) + m.group(3)

    # Remove a stray 1-3 letter Persian token when it is not a normal
    # grammatical lead. Examples seen in the bad output: «پف حواشی ...».
    parts = title.split()
    while len(parts) >= 2:
        first = parts[0]
        second = parts[1]
        if (
            1 <= len(first) <= 3
            and first not in _VALID_SHORT_LEADS
            and len(second) >= 4
            and re.fullmatch(r"[\u0600-\u06ff]+", first)
            and re.fullmatch(r"[\u0600-\u06ff]+", second)
        ):
            parts.pop(0)
            continue
        break

    return " ".join(parts).strip()[:180]


def guarded_gemini_request(title, article_text):
    result = _ORIGINAL_GEMINI_REQUEST(title, article_text)
    if isinstance(result, dict):
        result = dict(result)
        result["title"] = _clean_generated_title(result.get("title", ""))
    return result


main.gemini_request = guarded_gemini_request
print("HEADLINE GUARD: stray Gemini title prefixes cleaned")
