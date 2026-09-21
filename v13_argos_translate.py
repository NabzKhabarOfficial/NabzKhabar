"""NABZ V13 — Argos Translate offline/localization layer.

Primary purpose: translate English foreign-news text to Persian without an AI
API. The model is installed into the workspace cache and then runs locally.
If Argos is unavailable, callers can fall back to the existing AI router.
"""
import os
import re
from pathlib import Path

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

_EN_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20,
    "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}

_FA_NUMBER_WORDS = {
    # "یک" is intentionally excluded: Argos frequently uses it for the
    # English indefinite article ("a/an"), which is not a factual number.
    # Numeric safety still tracks explicit digits and unambiguous number words.
    "صفر": 0, "دو": 2, "سه": 3, "چهار": 4, "پنج": 5,
    "شش": 6, "هفت": 7, "هشت": 8, "نه": 9, "ده": 10,
    "یازده": 11, "دوازده": 12, "سیزده": 13, "چهارده": 14,
    "پانزده": 15, "شانزده": 16, "هفده": 17, "هجده": 18,
    "نوزده": 19, "بیست": 20, "سی": 30, "چهل": 40, "پنجاه": 50,
    "شصت": 60, "هفتاد": 70, "هشتاد": 80, "نود": 90,
}

def _numeric_values(text):
    """Extract semantic numeric values, including compound number words.

    This prevents false rejections when Argos translates:
      twenty-five -> ۲۵
      two hundred and two -> ۲۰۲
      four hundred -> ۴۰۰
    """
    value = str(text or "").lower()
    normalized = value.translate(str.maketrans(
        "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"
    ))

    values = set()
    # Explicit Arabic/Persian/Latin digits.
    for match in re.findall(r"(?<!\d)\d+(?:[.,]\d+)?(?!\d)", normalized):
        try:
            values.add(int(match.replace(",", "").split(".", 1)[0]))
        except Exception:
            pass

    en = {
        "zero":0,"one":1,"two":2,"three":3,"four":4,"five":5,"six":6,
        "seven":7,"eight":8,"nine":9,"ten":10,"eleven":11,"twelve":12,
        "thirteen":13,"fourteen":14,"fifteen":15,"sixteen":16,
        "seventeen":17,"eighteen":18,"nineteen":19,"twenty":20,
        "thirty":30,"forty":40,"fifty":50,"sixty":60,"seventy":70,
        "eighty":80,"ninety":90,
    }
    fa = {
        "صفر":0,"دو":2,"سه":3,"چهار":4,"پنج":5,"شش":6,"هفت":7,"هشت":8,
        "نه":9,"ده":10,"یازده":11,"دوازده":12,"سیزده":13,"چهارده":14,
        "پانزده":15,"شانزده":16,"هفده":17,"هجده":18,"نوزده":19,"بیست":20,
        "سی":30,"چهل":40,"پنجاه":50,"شصت":60,"هفتاد":70,"هشتاد":80,"نود":90,
    }

    def parse_en(tokens):
        total = 0
        current = 0
        found = False
        for token in tokens:
            if token == "and":
                continue
            if token in en:
                current += en[token]
                found = True
            elif token == "hundred":
                current = max(1, current) * 100
                found = True
            elif token in ("thousand", "million"):
                scale = 1000 if token == "thousand" else 1000000
                current = max(1, current) * scale
                total += current
                current = 0
            else:
                return None if not found else total + current
        return (total + current) if found else None

    def parse_fa(tokens):
        units = {"صد":100, "هزار":1000, "میلیون":1000000}
        total = 0
        current = 0
        found = False
        for token in tokens:
            if token in ("و",):
                continue
            if token in fa:
                current += fa[token]
                found = True
            elif token in units:
                current = max(1, current) * units[token]
                if units[token] >= 1000:
                    total += current
                    current = 0
                found = True
            else:
                return None if not found else total + current
        return (total + current) if found else None

    # English compound phrases.
    en_words = re.findall(
        r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|"
        r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|"
        r"eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|"
        r"eighty|ninety|hundred|thousand|million|and)\b",
        value,
    )
    if en_words:
        run=[]
        for token in en_words:
            if token == "and" and not run:
                continue
            if token == "and" and run:
                run.append(token)
                continue
            if run and token not in en and token not in ("hundred","thousand","million"):
                parsed=parse_en(run)
                if parsed is not None: values.add(parsed)
                run=[]
            run.append(token)
        if run:
            parsed=parse_en(run)
            if parsed is not None: values.add(parsed)

    # Persian compound phrases.
    fa_words = re.findall(
        r"(?:صفر|دو|سه|چهار|پنج|شش|هفت|هشت|نه|ده|یازده|دوازده|سیزده|"
        r"چهارده|پانزده|شانزده|هفده|هجده|نوزده|بیست|سی|چهل|پنجاه|شصت|"
        r"هفتاد|هشتاد|نود|صد|هزار|میلیون|و)",
        value,
    )
    if fa_words:
        run=[]
        for token in fa_words:
            if token == "و" and not run:
                continue
            if token == "و" and run:
                run.append(token)
                continue
            if run and token not in fa and token not in ("صد","هزار","میلیون"):
                parsed=parse_fa(run)
                if parsed is not None: values.add(parsed)
                run=[]
            run.append(token)
        if run:
            parsed=parse_fa(run)
            if parsed is not None: values.add(parsed)

    # Keep unambiguous single-word values too, but never treat Persian "یک"
    # as a factual number because Argos commonly uses it for "a/an".
    values.update(en.get(x) for x in re.findall(r"\b[a-z]+\b", value) if x in en)
    values.update(fa.get(x) for x in fa if x in value)
    values.discard(None)
    return values

def _sentence_list(text):
    return [s.strip() for s in re.split(r"(?<=[.!؟؛])\s+", str(text or "").strip()) if s.strip()]

def _translation_pair_ready():
    import argostranslate.translate
    installed = argostranslate.translate.get_installed_languages()
    en = next((x for x in installed if x.code == "en"), None)
    fa = next((x for x in installed if x.code == "fa"), None)
    if not en or not fa:
        return False
    try:
        return bool(en.get_translation(fa))
    except Exception:
        return False

def _ensure_model():
    global _READY, _FAILED
    if _READY:
        return True
    if _FAILED:
        return False
    try:
        import argostranslate.package
        import argostranslate.translate

        if _translation_pair_ready():
            _READY = True
            print("V13 ARGOS: en->fa package already installed.")
            return True

        print("V13 ARGOS: preparing cached en->fa package...")
        os.makedirs(ARGOS_PACKAGES_DIR, exist_ok=True)

        cached_models = sorted(Path(ARGOS_PACKAGES_DIR).glob("translate-en_fa-*.argosmodel"))
        if cached_models:
            cached = cached_models[-1]
            print(f"V13 ARGOS: found cached model {cached.name}; installing it.")
            argostranslate.package.install_from_path(cached)
            if _translation_pair_ready():
                _READY = True
                print("V13 ARGOS: cached en->fa model installed and ready.")
                return True

        # Keep Argos' own package-index/cache location separate from the
        # persistent model directory. Pointing XDG_CACHE_HOME inside
        # ARGOS_PACKAGES_DIR causes Argos 1.11 to expect a metadata.json file
        # that is not present on a fresh GitHub Actions runner.
        argostranslate.package.update_package_index()
        packages = argostranslate.package.get_available_packages()
        package = next(
            (p for p in packages if p.from_code == "en" and p.to_code == "fa"),
            None,
        )
        if package is None:
            raise RuntimeError("Argos en->fa package not found in package index.")

        download_path = Path(package.download())
        cached_path = Path(ARGOS_PACKAGES_DIR) / download_path.name
        if download_path.resolve() != cached_path.resolve():
            import shutil
            shutil.copy2(download_path, cached_path)

        argostranslate.package.install_from_path(cached_path)
        print(f"V13 ARGOS: model cached at {cached_path}")

        if not _translation_pair_ready():
            raise RuntimeError("Argos en->fa translation pair unavailable after install.")

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
    original_numbers = _numeric_values(title + " " + source)
    translated_numbers = _numeric_values(fa_title + " " + fa_body)
    if not translated_numbers.issubset(original_numbers):
        print(
            "V13 ARGOS: rejected translation because it introduced "
            f"unmatched number value(s): {sorted(translated_numbers - original_numbers)}"
        )
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
