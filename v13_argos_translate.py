"""NABZ V13 — Argos Translate offline/localization layer."""
import os
import re
import time
from pathlib import Path

ARGOS_PACKAGES_DIR = os.getenv("ARGOS_PACKAGES_DIR", os.path.join(os.getcwd(), ".argos-packages")).strip()
os.environ.setdefault("ARGOS_DEVICE_TYPE", "cpu")
os.environ.setdefault("ARGOS_COMPUTE_TYPE", "int8_float32")
os.environ.setdefault("ARGOS_INTER_THREADS", "1")
os.environ.setdefault("ARGOS_INTRA_THREADS", "0")
os.environ.setdefault("ARGOS_PACKAGES_DIR", ARGOS_PACKAGES_DIR)

_READY = False
_FAILED = False


def _persian_ratio(text):
    letters = re.findall(r"[A-Za-z\u0600-\u06ff]", str(text or ""))
    if not letters: return 1.0
    return sum("\u0600" <= ch <= "\u06ff" for ch in letters) / len(letters)


def _latin_tokens(text):
    value = re.sub(r"https?://\S+|www\.\S+", " ", str(text or ""), flags=re.I)
    return re.findall(r"(?<![A-Za-z])[A-Za-z]{2,}(?![A-Za-z])", value)

ARGOS_RESIDUAL_MAP = {
    "famine":"قحطی", "kherson":"خرسون", "oleshky":"اولشکی", "russia":"روسیه", "ukraine":"اوکراین",
    "humanitarian":"بشردوستانه", "evacuation":"تخلیه", "corridor":"راهرو", "delays":"به تأخیر انداختن",
    "threatens":"تهدید می‌کند", "threatened":"تهدید کرد", "threat":"تهدید", "nato":"ناتو", "un":"سازمان ملل",
    "gaza":"غزه", "israel":"اسرائیل", "iran":"ایران", "china":"چین", "taiwan":"تایوان", "qatar":"قطر",
    "poland":"لهستان", "syria":"سوریه", "lebanon":"لبنان", "north":"شمال", "south":"جنوب", "region":"منطقه",
    "reuters":"رویترز", "view":"مشاهده", "breaking":"فوری", "latest":"آخرین", "news":"خبر", "report":"گزارش",
    "reports":"گزارش‌ها", "official":"مقام رسمی", "officials":"مقام‌ها", "president":"رئیس‌جمهور", "government":"دولت",
}
_LATIN_DIGRAPHS=(("sch","ش"),("tch","چ"),("ph","ف"),("th","ث"),("sh","ش"),("ch","چ"),("zh","ژ"),("kh","خ"),("gh","غ"),("qu","کو"),("ck","ک"),("ee","ی"),("oo","و"),("ou","و"),("ow","او"),("ai","ای"),("ay","ای"),("ei","ای"),("ey","ای"),("ie","ی"),("tion","شن"),("sion","ژن"),("ci","سی"),("ce","س"),("cy","سی"),("ge","ج"),("gi","جی"))
_LATIN_CHARS={"a":"ا","b":"ب","c":"ک","d":"د","e":"ی","f":"ف","g":"گ","h":"ه","i":"ی","j":"ج","k":"ک","l":"ل","m":"م","n":"ن","o":"و","p":"پ","q":"ق","r":"ر","s":"س","t":"ت","u":"و","v":"و","w":"و","x":"کس","y":"ی","z":"ز"}


def _phonetic_persian(token):
    raw=re.sub(r"[^A-Za-z]","",str(token or "")).lower()
    if not raw: return ""
    if raw in ARGOS_RESIDUAL_MAP: return ARGOS_RESIDUAL_MAP[raw]
    out=[]; i=0
    while i<len(raw):
        matched=False
        for src,dst in _LATIN_DIGRAPHS:
            if raw.startswith(src,i): out.append(dst); i+=len(src); matched=True; break
        if matched: continue
        out.append(_LATIN_CHARS.get(raw[i],"")); i+=1
    return "".join(out).strip()


def _sentence_list(text):
    return [s.strip() for s in re.split(r"(?<=[.!؟؛])\s+",str(text or "").strip()) if s.strip()]


def _translation_pair_ready():
    import argostranslate.translate
    installed=argostranslate.translate.get_installed_languages()
    en=next((x for x in installed if x.code=="en"),None); fa=next((x for x in installed if x.code=="fa"),None)
    if not en or not fa: return False
    try: return bool(en.get_translation(fa))
    except Exception: return False


def _ensure_model():
    global _READY,_FAILED
    if _READY: return True
    if _FAILED: return False
    try:
        import argostranslate.package
        if _translation_pair_ready(): _READY=True; print("V13 ARGOS: en->fa package already installed."); return True
        os.makedirs(ARGOS_PACKAGES_DIR,exist_ok=True)
        cached=sorted(Path(ARGOS_PACKAGES_DIR).glob("translate-en_fa-*.argosmodel"))
        if cached:
            argostranslate.package.install_from_path(cached[-1])
            if _translation_pair_ready(): _READY=True; print("V13 ARGOS: cached en->fa model installed and ready."); return True
        argostranslate.package.update_package_index(); packages=argostranslate.package.get_available_packages()
        package=next((p for p in packages if p.from_code=="en" and p.to_code=="fa"),None)
        if package is None: raise RuntimeError("Argos en->fa package not found in package index.")
        download_path=Path(package.download()); cached_path=Path(ARGOS_PACKAGES_DIR)/download_path.name
        if download_path.resolve()!=cached_path.resolve():
            import shutil; shutil.copy2(download_path,cached_path)
        argostranslate.package.install_from_path(cached_path)
        if not _translation_pair_ready(): raise RuntimeError("Argos en->fa translation pair unavailable after install.")
        _READY=True; print(f"V13 ARGOS: model cached at {cached_path}"); return True
    except Exception as exc:
        _FAILED=True; print(f"V13 ARGOS: unavailable; AI fallback remains active: {exc}"); return False


def translate_en_to_fa(text):
    if not text or not _ensure_model(): return ""
    try:
        import argostranslate.translate
        value=str(text).strip(); chunks=[]; current=[]; current_len=0
        for sentence in _sentence_list(value):
            if current and current_len+len(sentence)>1800: chunks.append(" ".join(current)); current=[]; current_len=0
            current.append(sentence); current_len+=len(sentence)+1
        if current: chunks.append(" ".join(current))
        if not chunks: chunks=[value[:1800]]
        translated=[]
        for chunk in chunks:
            try: value_out=argostranslate.translate.translate(chunk,"en","fa")
            except Exception as exc: print(f"V13 ARGOS: chunk translation failed: {exc}"); value_out=""
            if value_out and value_out.strip(): translated.append(value_out.strip())
        return " ".join(translated).strip()
    except Exception as exc:
        print(f"V13 ARGOS: translation error: {exc}"); return ""


def _repair_argos_residuals(text):
    value=str(text or "")
    for src,dst in ARGOS_RESIDUAL_MAP.items(): value=re.sub(r"(?i)(?<![A-Za-z])"+re.escape(src)+r"(?![A-Za-z])",dst,value)
    residuals=list(dict.fromkeys(_latin_tokens(value)))
    if residuals and _translation_pair_ready():
        try:
            import argostranslate.translate
            for token in residuals[:20]:
                try: candidate=str(argostranslate.translate.translate(token,"en","fa") or "").strip()
                except Exception: candidate=""
                if candidate and not _latin_tokens(candidate) and _persian_ratio(candidate)>=0.50:
                    value=re.sub(r"(?i)(?<![A-Za-z])"+re.escape(token)+r"(?![A-Za-z])",candidate,value)
        except Exception as exc: print(f"V13 ARGOS: residual-token rescue unavailable: {exc}")
    for token in list(dict.fromkeys(_latin_tokens(value)))[:30]:
        replacement=_phonetic_persian(token)
        if replacement and _persian_ratio(replacement)>=0.90: value=re.sub(r"(?i)(?<![A-Za-z])"+re.escape(token)+r"(?![A-Za-z])",replacement,value)
    return re.sub(r"\s+"," ",value).strip()


def _clean_source_for_translation(source):
    value=re.sub(r"https?://\S+|www\.\S+"," ",str(source or ""),flags=re.I)
    # Remove common international-news webpage chrome before offline translation.
    # Without this, Argos translates UI/caption text such as "Listen", "Share"
    # and image credits and can produce fluent-looking but unusable Telegram copy.
    value=re.sub(r"(?is)\bListen\s*\(\s*\d+\s*mins?\s*\)", " ", value)
    value=re.sub(r"(?is)\bShare\s+.+?\s+on\s+social\s+media\b", " ", value)
    value=re.sub(r"(?is)\b(?:By|Image|Photo|File)\s*:\s*[^.]{0,180}", " ", value)
    value=re.sub(r"(?is)\b(?:Al Jazeera Staff|Reuters Staff|AFP Staff)\b", " ", value)
    value=re.sub(r"(?is)\bPublished\s+(?:on|at)\s+\d{1,2}\s+\w+\s+\d{4}", " ", value)
    return re.sub(r"\s+"," ",value).strip()[:2400]


def translate_foreign_story(title,article_text):
    title=str(title or "").strip(); source=_clean_source_for_translation(article_text or title)
    if _persian_ratio(title)>=0.60: return None
    fa_title=_repair_argos_residuals(translate_en_to_fa(title[:500]))
    if not fa_title or _persian_ratio(fa_title)<0.60: return None
    # Do not feed giant scraped pages to Argos. The title is translated first;
    # a clean short excerpt is used for context, and a title-only emergency
    # summary is allowed when the body is malformed.
    fa_body=_repair_argos_residuals(translate_en_to_fa(source[:2400]))
    if not fa_body or _persian_ratio(fa_body)<0.60: fa_body=fa_title
    summary=" ".join(_sentence_list(fa_body)[:3]).strip() or fa_title
    if len(summary)>750: summary=summary[:750].rsplit(" ",1)[0]+"…"
    return {"title":fa_title[:180].strip(),"summary":summary}


def healthcheck(): return _ensure_model()

def install(main):
    main.argos_translate_foreign_story=translate_foreign_story
    print("V13 ARGOS TRANSLATE ACTIVE: independent English -> Persian local fallback")
