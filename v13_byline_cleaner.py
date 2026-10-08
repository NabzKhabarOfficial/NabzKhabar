"""Deterministic cleanup for publisher/reporter bylines at the start of news text.

Also strips news-site page chrome that the article extractor sometimes keeps in the body
(Mehr/ISNA-style "۱۶ مهر ۱۴۰۵، ۲۲:۰۶ کد مطلب 6972118 بین الملل غرب آسیا ..." header with the
section breadcrumb repeated and the headline repeated), and keeps the Persian half-space
(ZWNJ) so words like «می‌شود» and «رسانه‌ها» are not split in two. Loaded agency terms
(«رژیم صهیونیستی»، «هلاکت»، «اشغالگر») are turned into neutral wording (NEUTRAL_TERMS).
"""
import re

_S = r"[\s\u200c]"  # a space or a half-space (ZWNJ)

GENERIC_SOURCE_RE = re.compile(
    r"^\s*(?:باشگاه" + _S + r"+خبرنگاران" + _S + r"+جوان|خبرگزاری" + _S + r"+(?:مهر|ایسنا|ایرنا|فارس|تسنیم|دانشجو|برنا|ایلنا)|"
    r"خبرگزاری" + _S + r"+صدا" + _S + r"*و" + _S + r"*سیما|رویترز|آسوشیتدپرس|فرانس" + _S + r"+پرس|الجزیره|العربیه|"
    r"بی" + _S + r"*بی" + _S + r"*سی|دویچه" + _S + r"+وله)\s*[,،:]?\s*",
    re.I,
)

REPORTER_LEAD_RE = re.compile(
    r"^\s*(?:[^.!؟\n]{1,120}?\s*[-–—]\s*)?(?=[^\n])",
    re.I,
)

KNOWN_PREFIXES = (
    "به گزارش خبرنگار", "به گزارش", "مینا عظیمی", "کیمیا قلی پور", "کیمیا قلی‌پور", "مرتضی قانع",
)

# ---------------------------------------------------------------- page chrome
_D = r"[0-9۰-۹]"
_MONTHS = r"(?:فروردین|اردیبهشت|خرداد|تیر|مرداد|شهریور|مهر|آبان|آذر|دی|بهمن|اسفند)"
DATE_TIME_RE = re.compile(_D + r"{1,2}\s+" + _MONTHS + r"\s+" + _D + r"{4}\s*[،,\-–]?\s*(?:ساعت\s*)?" + _D + r"{1,2}:" + _D + r"{2}")
CODE_RE = re.compile(r"کد" + _S + r"*(?:مطلب|خبر)\s*[:：]?\s*" + _D + r"+")
# Section names news sites print above an article (breadcrumb). Only removed at the very
# start of the body, never inside a sentence.
SECTIONS = (
    "غرب آسیا و آفریقای شمالی", "آسیا و اقیانوسیه", "آمریکا و اروپا", "اروپا و آمریکا", "آفریقا",
    "بین الملل", "بین‌الملل", "سیاست خارجی", "سیاست داخلی", "سیاست", "اقتصاد", "جامعه", "حوادث",
    "فرهنگ و هنر", "علم و فناوری", "دانش و فناوری", "ورزش", "استان ها", "استان‌ها", "دفاع و امنیت",
    "انتظامی و حوادث", "مجلس", "دولت", "اخبار", "عمومی", "پربازدید", "خلاصه خبر",
)
_SECTION_RE = re.compile(
    r"^\s*(?:" + "|".join(sorted((re.escape(s).replace(r"\ ", _S + "+").replace("\u200c", _S) for s in SECTIONS),
                                 key=len, reverse=True)) + r")(?=[\s\u200c،,:\-–]|$)\s*[،,:\-–]?\s*"
)


# ---------------------------------------------------------------- neutral wording
# Owner rule (Oct 9 2026): wire-agency loaded terms become neutral, BBC/Reuters-style words.
# Longest phrases first; ZWNJ and space are both accepted inside a phrase.
NEUTRAL_TERMS = (
    ("ارتش اشغالگر رژیم صهیونیستی", "ارتش اسرائیل"),
    ("ارتش رژیم صهیونیستی", "ارتش اسرائیل"),
    ("رژیم اشغالگر قدس", "اسرائیل"),
    ("رژیم غاصب صهیونیستی", "اسرائیل"),
    ("رژیم صهیونیستی", "اسرائیل"),
    ("رژیم صهیونیست", "اسرائیل"),
    ("سخنگوی صهیونیست ها", "سخنگوی اسرائیل"),
    ("نظامیان صهیونیست", "نظامیان اسرائیلی"),
    ("نظامی صهیونیست", "نظامی اسرائیلی"),
    ("نظامی اشغالگر", "نظامی اسرائیلی"),
    ("نظامیان اشغالگر", "نظامیان اسرائیلی"),
    ("صهیونیست ها", "اسرائیلی‌ها"),
    ("صهیونیست‌ها", "اسرائیلی‌ها"),
    ("صهیونیستی", "اسرائیلی"),
    ("صهیونیست", "اسرائیلی"),
    ("به هلاکت رسیدند", "کشته شدند"),
    ("به هلاکت رسید", "کشته شد"),
    ("هلاک شدند", "کشته شدند"),
    ("هلاک شد", "کشته شد"),
    ("هلاکت", "کشته شدن"),
)


def _phrase_re(phrase):
    body = re.escape(phrase).replace(r"\ ", _S + "+").replace("\u200c", _S)
    return re.compile(r"(?<![\w\u0600-\u06FF])" + body + r"(?![\w\u0600-\u06FF])")


_NEUTRAL = [(_phrase_re(a), b) for a, b in NEUTRAL_TERMS]


def neutral(value):
    text = str(value or "")
    for pat, repl in _NEUTRAL:
        text = pat.sub(repl, text)
    return text


def strip_chrome(text, title=""):
    """Remove the page header (date/time, article code, section breadcrumb, repeated headline)
    from the start of an article body. Text that has no such header is returned unchanged."""
    raw = str(text or "")
    if not (CODE_RE.search(raw[:400]) or DATE_TIME_RE.search(raw[:400])):
        return raw
    head, tail = raw[:400], raw[400:]
    head = CODE_RE.sub(" ", head)
    head = DATE_TIME_RE.sub(" ", head)
    head = re.sub(r"\s{2,}", " ", head).lstrip(" ⚡️|-–—:،,")
    for _ in range(12):
        new = _SECTION_RE.sub("", head, count=1)
        if new == head:
            break
        head = new
    text = (head + tail).strip()
    t = re.sub(r"\s+", " ", str(title or "").replace("\u200c", " ")).strip()
    if len(t) >= 12:
        for _ in range(2):
            probe = text.replace("\u200c", " ")
            if probe.startswith(t):
                text = text[len(t):].lstrip(" .:،,-–—")
            else:
                break
    return text


def clean(value):
    text = str(value or "")
    text = text.replace("\u200f", " ")
    for _ in range(2):
        before = text
        text = GENERIC_SOURCE_RE.sub("", text, count=1)
        for prefix in KNOWN_PREFIXES:
            pat = re.escape(prefix).replace(r"\ ", _S + "+").replace("\u200c", _S)
            text = re.sub(r"^\s*" + pat + r"\s*[-–—:،]?\s*", "", text, flags=re.I)
        # After a recognized publisher, remove the reporter/desk credit ending
        # at a dash. Example: "باشگاه خبرنگاران جوان، اعظم پورکند - lead".
        if before != text and re.match(r"^\s*[^.!؟\n]{1,160}\s*[-–—]\s+", text):
            text = re.sub(r"^\s*[^.!؟\n]{1,160}\s*[-–—]\s+", "", text, count=1)
        if text == before:
            break
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def install(core):
    for name in ("build_caption",):
        original = getattr(core, name, None)
        if not callable(original):
            continue
        def wrapped(title, body, _original=original):
            t = clean(title)
            return _original(neutral(t), neutral(clean(strip_chrome(body, t))))
        setattr(core, name, wrapped)
    print("V13 BYLINE CLEANER ACTIVE: publisher lead-ins and page headers removed, neutral wording on.")
