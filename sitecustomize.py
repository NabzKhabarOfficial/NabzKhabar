"""NABZ V13 startup safety hook.

Keeps the existing Argos module intact while enforcing a deterministic
publication-quality gate around its foreign-story fallback. No network or paid
service is introduced.
"""
import builtins
import re

_original_import = builtins.__import__
_wrapped = False


def _persian_ratio(text):
    letters = re.findall(r"[A-Za-z\u0600-\u06ff]", str(text or ""))
    if not letters:
        return 1.0
    return sum("\u0600" <= ch <= "\u06ff" for ch in letters) / len(letters)


def _clean_scraped(text):
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    value = re.sub(r"\b(?:published|updated)\s+(?:on\s+)?\d{1,2}\s+[A-Za-z]+\s+\d{4}(?:\s+\d{1,2}:\d{2})?\b", " ", value, flags=re.I)
    value = re.sub(r"(?:^|\s)(?:listen|save|tags?|follow|share|copy link|read more|advertisement)\s*(?:\([^)]*\))?\s*[:|–—-]?\s*", " ", value, flags=re.I)
    value = re.sub(r"\[[^\]]{1,120}\]", " ", value)
    return re.sub(r"\s+", " ", value).strip(" -|:")


def _bad_translation(text):
    value = re.sub(r"\s+", " ", str(text or "")).strip().lower()
    bad = (
        "جنگ به جهان", "هشدار به جهان را ویران", "برچسب های", "برچسب‌های",
        "گوش دادن", "صرفه جویی", "رسانه های اجتماعی", "رسانه‌های اجتماعی",
        "به گوگلی", "در گوگلی", "به منطقه حمله می کند", "به منطقه حمله می‌کند",
        "به جهان حمله می کند", "به جهان حمله می‌کند",
    )
    if any(x in value for x in bad):
        return True
    if re.search(r"\b(?:the|and|of|to|in|on|with|from|published|tags?|listen|save)\b", value, re.I):
        return True
    return len(re.findall(r"\b(?:یک|به|از|را|در|برای)\b", value)) >= 8 and len(value) < 220


def _quality_ok(result, source):
    if not isinstance(result, dict):
        return False
    title = str(result.get("title", "")).strip()
    summary = str(result.get("summary", "")).strip()
    if not title or not summary:
        return False
    if _persian_ratio(title) < 0.72 or _persian_ratio(summary) < 0.72:
        return False
    if _bad_translation(title) or _bad_translation(summary):
        return False
    if len(title) < 12 or len(title) > 180:
        return False
    if len(summary) < 35 or len(summary) > 750:
        return False
    return True


def _wrap_argos(module):
    global _wrapped
    if _wrapped or not hasattr(module, "translate_foreign_story"):
        return module
    original = module.translate_foreign_story

    def guarded_translate_foreign_story(title, article_text):
        clean_title = _clean_scraped(title)
        clean_source = _clean_scraped(article_text or clean_title)
        result = original(clean_title, clean_source)
        if not _quality_ok(result, clean_source):
            print("V13 TRANSLATION QUALITY GATE: rejected Argos output; no low-quality translation will be published.")
            return None
        return result

    module.translate_foreign_story = guarded_translate_foreign_story
    _wrapped = True
    print("V13 TRANSLATION QUALITY GATE ACTIVE: Argos output is publication-blocked when malformed.")
    return module


def _nabz_import(name, globals=None, locals=None, fromlist=(), level=0):
    module = _original_import(name, globals, locals, fromlist, level)
    if name == "v13_argos_translate" or name.startswith("v13_argos_translate."):
        try:
            import sys
            _wrap_argos(sys.modules.get("v13_argos_translate", module))
        except Exception as exc:
            print(f"V13 TRANSLATION QUALITY GATE: hook error: {exc}")
    return module


builtins.__import__ = _nabz_import
