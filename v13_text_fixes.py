"""NABZ V13 - text fixes for common editorial slips (Oct 2026).

Fixes that a reviewer caught in published posts, applied to every new post
before it is formatted:

* known typos: «سخ دوستانی» -> «سخنرانی دوستانه», «دست وپنج نرم» -> «دست و پنجه نرم»
* a sentence or bullet that starts with a dangling «که» (broken relative clause)
  loses the «که» so it reads as a sentence

The same launcher hook also starts the Telegram error logger (v13_error_log),
so no extra edit to run_bot.py is needed.

Fail-safe: any error returns the original text unchanged.
"""

import re

TYPO_FIXES = (
    ("سخ دوستانی", "سخنرانی دوستانه"),
    ("دست وپنج نرم", "دست و پنجه نرم"),
    ("دست و پنج نرم", "دست و پنجه نرم"),
)

_DANGLING_THAT = re.compile(r"(^|\n|▫️\s*|•\s*|-\s*)که\s+(?=\S)")


def fix_text(text):
    try:
        value = str(text or "")
        for wrong, right in TYPO_FIXES:
            value = value.replace(wrong, right)
        value = _DANGLING_THAT.sub(lambda m: m.group(1), value)
        return value
    except Exception:
        return text


def install(formatter):
    """Wrap the formatter's title/body functions so every post is cleaned."""
    try:
        import v13_error_log
        v13_error_log.install()
    except Exception as exc:
        print(f"V13 TELEGRAM ERROR LOG: not installed ({type(exc).__name__})", flush=True)
    if getattr(formatter, "_v13_text_fixes_installed", False):
        return
    for name in ("format_title", "format_body"):
        inner = getattr(formatter, name, None)
        if not callable(inner):
            continue

        def wrapped(value, _inner=inner):
            return _inner(fix_text(value))

        setattr(formatter, name, wrapped)
    formatter._v13_text_fixes_installed = True
    print("V13 TEXT FIXES ACTIVE: typo and dangling-que cleanup.", flush=True)
