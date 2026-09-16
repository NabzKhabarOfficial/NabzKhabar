"""Stronger duplicate-news guard for NabzKhabar.

This module is imported by the GitHub Actions runner before main.main().
It monkey-patches the existing story matcher instead of rewriting the
large main.py file, keeping the current architecture and state format.
"""

import re
import main


GENERIC = {
    "خبر", "گزارش", "اعلام", "آخرین", "جدید", "مهم", "تازه", "جزئیات",
    "واکنش", "اظهارات", "مواضع", "توضیح", "انتقاد", "تاکید", "تأکید",
    "گفت", "گفتند", "کرد", "کردند", "شد", "شدند", "خواهد", "می", "شود",
    "است", "هست", "این", "آن", "یک", "از", "به", "در", "با", "برای", "و",
    "که", "را", "تا", "بر", "های", "ها", "هم", "نیز", "مورد", "درباره",
    "درخواست", "دیدار", "سخنان", "مقامات", "مقام", "کشور", "منطقه", "شهر",
    "استان", "رئیس", "وزیر", "وزارت", "دولت",
}


def _norm(text):
    text = main.normalize_digits(str(text or "")).lower()
    text = (
        text.replace("ي", "ی")
        .replace("ى", "ی")
        .replace("ك", "ک")
        .replace("ة", "ه")
    )
    text = re.sub(r"[\u200b-\u200f\ufeff]", " ", text)
    text = re.sub(r"[،؛,:.!؟()\[\]{}\"'«»/\\|_–—-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokens(text):
    return {
        token
        for token in _norm(text).split()
        if len(token) >= 2 and token not in GENERIC
    }


def _numbers(text):
    return set(
        re.findall(
            r"\d+(?:[.,٬]\d+)*",
            main.normalize_digits(str(text or "")),
        )
    )


def strong_same_story(a, b):
    """Catch paraphrased headlines that describe the same story."""
    title_a = main.clean_title(a.get("title", ""))
    title_b = main.clean_title(b.get("title", ""))

    if not title_a or not title_b:
        return False

    if _norm(title_a) == _norm(title_b):
        return True

    tokens_a = _tokens(title_a)
    tokens_b = _tokens(title_b)
    common = tokens_a & tokens_b

    if not tokens_a or not tokens_b:
        return False

    jaccard = len(common) / len(tokens_a | tokens_b)
    containment = len(common) / min(len(tokens_a), len(tokens_b))

    # Strong overlap: different wording, same core entities.
    if len(common) >= 4 and containment >= 0.60:
        return True

    if len(common) >= 5 and jaccard >= 0.32:
        return True

    # A shared number is a strong event anchor.
    common_numbers = _numbers(title_a) & _numbers(title_b)
    if common_numbers and len(common) >= 2 and jaccard >= 0.25:
        return True

    # Several distinctive long words shared between headlines.
    long_common = [word for word in common if len(word) >= 4]
    if len(long_common) >= 3 and containment >= 0.50:
        return True

    return False


# The existing pipeline calls same_story in clustering, current-run selection,
# and history checks. Replacing this single function strengthens all of them.
main.same_story = strong_same_story


def strong_same_event(a_title, a_body, b_title, b_body):
    return strong_same_story(
        {"title": f"{a_title} {a_body}"},
        {"title": f"{b_title} {b_body}"},
    )


main.same_event = strong_same_event
