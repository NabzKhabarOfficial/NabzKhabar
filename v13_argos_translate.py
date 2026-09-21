"""NABZ V13 — Argos Translate offline/localization layer.

Primary purpose: translate English foreign-news text to Persian without an AI
API. The model is installed into the workspace cache and then runs locally.
If Argos is unavailable, callers can fall back to the existing AI router.
"""
import os
import re

ARGOS_PACKAGES_DIR = os.getenv(
    "ARGOS_PACKAGES_DIR",
    os.path.join(os.getcwd(), ".argos-packages"),
).strip()
os.environ.setdefault("ARGOS_DEVICE_TYPE", "cpu")
os.environ.setdefault("ARGOS_COMPUTE_TYPE", "int8_float32")
os.environ.setdefault("ARGOS_INTER_THREADS", "1")
os.environ.setdefault("ARGOS_INTRA_THREADS", "0")
os.environ.setdefault("ARGOS_PACKAGES_DIR", ARGOS_PACKAGES_DIR)

_READY = False
_FAILED = False

def _persian_ratio(text):
    letters = re.findall(r"[A-Za-z\u0600-\u06ff]", str(text or ""))
    if not letters:
        return 1.0
    return sum("\u0600" <= ch <= "\u06ff" for ch in letters) / len(letters)

def _numbers(text):
    value = str(text or "").translate(str.maketrans(
        "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"
    ))
    return set(re.findall(r"\b\d+(?:[.,]\d+)?\b", value))

def _sentence_list(text):
    return [s.strip() for s in re.split(r"(?<=[.!؟؛])\s+", str(text or "").strip()) if s.strip()]

def _ensure_model():
    global _READY, _FAILED
    if _READY:
        return True
    if _FAILED:
        return False
    try:
        import argostranslate.package
        import argostranslate.translate
        installed = argostranslate.translate.get_installed_languages()
        en = next((x for x in installed if x.code == "en"), None)
        fa = next((x for x in installed if x.code == "fa"), None)
        if en and fa:
            try:
                en.get_translation(fa)
                _READY = True
                print("V13 ARGOS: en->fa package already installed.")
                return True
            except Exception:
                pass
        print("V13 ARGOS: installing en->fa package into cached package directory...")
        os.makedirs(ARGOS_PACKAGES_DIR, exist_ok=True)
        argostranslate.package.update_package_index()
        packages = argostranslate.package.get_available_packages()
        package = next((p for p in packages if p.from_code == "en" and p.to_code == "fa"), None)
        if package is None:
            raise RuntimeError("Argos en->fa package not found in package index.")
        download_path = package.download()
        argostranslate.package.install_from_path(download_path)
        installed = argostranslate.translate.get_installed_languages()
        en = next((x for x in installed if x.code == "en"), None)
        fa = next((x for x in installed if x.code == "fa"), None)
        if not en or not fa:
            raise RuntimeError("Argos en->fa languages unavailable after install.")
        en.get_translation(fa)
        _READY = True
        print("V13 ARGOS: en->fa translation layer ready.")
        return True
    except Exception as exc:
        _FAILED = True
        print(f"V13 ARGOS: unavailable; AI fallback remains active: {exc}")
        return False

def translate_en_to_fa(text):
    """Translate English text locally. Returns empty string on failure."""
    if not text or not _ensure_model():
        return ""
    try:
        import argostranslate.translate
        value = str(text).strip()
        chunks, current, current_len = [], [], 0
        for sentence in _sentence_list(value):
            if current and current_len + len(sentence) > 1800:
                chunks.append(" ".join(current)); current=[]; current_len=0
            current.append(sentence); current_len += len(sentence) + 1
        if current:
            chunks.append(" ".join(current))
        if not chunks:
            chunks = [value[:1800]]
        translated = [argostranslate.translate.translate(chunk, "en", "fa") for chunk in chunks]
        return " ".join(x.strip() for x in translated if x and x.strip()).strip()
    except Exception as exc:
        print(f"V13 ARGOS: translation error: {exc}")
        return ""

def translate_foreign_story(title, article_text):
    """Translate an English foreign story using Argos only; no AI/API call."""
    title = str(title or "").strip()
    source = str(article_text or title).strip()
    if _persian_ratio(title) >= 0.60:
        return None
    fa_title = translate_en_to_fa(title)
    fa_body = translate_en_to_fa(source[:6000])
    if not fa_title or not fa_body:
        return None
    if _persian_ratio(fa_title) < 0.60 or _persian_ratio(fa_body) < 0.60:
        print("V13 ARGOS: Persian validation failed.")
        return None
    original_numbers = _numbers(title + " " + source)
    translated_numbers = _numbers(fa_title + " " + fa_body)
    if not translated_numbers.issubset(original_numbers):
        print("V13 ARGOS: rejected translation because it introduced a number.")
        return None
    summary = " ".join(_sentence_list(fa_body)[:3]).strip()
    if len(summary) > 750:
        summary = summary[:750].rsplit(" ", 1)[0] + "…"
    if not summary:
        return None
    return {"title": fa_title[:180].strip(), "summary": summary}

def healthcheck():
    return _ensure_model()


def install(main):
    """Install the independent Argos layer without changing the news engine."""
    main.argos_translate_foreign_story = translate_foreign_story
    print("V13 ARGOS TRANSLATE ACTIVE: independent English -> Persian local fallback")
