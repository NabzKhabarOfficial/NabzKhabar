"""Deterministic cleanup for publisher/reporter bylines at the start of news text."""
import re

GENERIC_SOURCE_RE = re.compile(
    r"^\s*(?:باشگاه\s+خبرنگاران\s+جوان|خبرگزاری\s+(?:مهر|ایسنا|ایرنا|فارس|تسنیم|دانشجو|برنا|ایلنا)|"
    r"خبرگزاری\s+صدا\s*و\s*سیما|رویترز|آسوشیتدپرس|فرانس\s+پرس|الجزیره|العربیه|"
    r"بی\s*بی\s*سی|دویچه\s+وله)\s*[,،:]?\s*",
    re.I,
)

REPORTER_LEAD_RE = re.compile(
    r"^\s*(?:[^.!؟\n]{1,120}?\s*[-–—]\s*)?(?=[^\n])",
    re.I,
)

KNOWN_PREFIXES = (
    "به گزارش خبرنگار", "به گزارش", "مینا عظیمی", "کیمیا قلی پور", "کیمیا قلی‌پور", "مرتضی قانع",
)


def clean(value):
    text = str(value or "")
    text = text.replace("\u200c", " ").replace("\u200f", " ")
    for _ in range(2):
        before = text
        text = GENERIC_SOURCE_RE.sub("", text, count=1)
        for prefix in KNOWN_PREFIXES:
            text = re.sub(r"^\s*" + re.escape(prefix) + r"\s*[-–—:،]?\s*", "", text, flags=re.I)
        # After a recognized publisher, remove the reporter/desk credit ending
        # at a dash. Example: "باشگاه خبرنگاران جوان، اعظم پورکند - lead".
        if before != text and re.match(r"^\s*[^.!؟\n]{1,160}\s*[-–—]\s+", text):
            text = re.sub(r"^\s*[^.!؟\n]{1,160}\s*[-–—]\s+", "", text, count=1)
        if text == before:
            break
    return re.sub(r"\s{2,}", " ", text).strip()


def install(core):
    for name in ("build_caption",):
        original = getattr(core, name, None)
        if not callable(original):
            continue
        def wrapped(title, body, _original=original):
            return _original(clean(title), clean(body))
        setattr(core, name, wrapped)
    print("V13 BYLINE CLEANER ACTIVE: generic publisher/reporter lead-ins removed.")
