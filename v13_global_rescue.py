"""NABZ V13 — conservative global critical-news rescue.

Prevents the freshness/editorial pipeline from silently losing high-impact
world events merely because the item is older than the normal freshness window.
No API or paid service is used.
"""
import re
import v13_intelligence

CRITICAL_TERMS = re.compile(
    r"(?:"
    r"mass\s+shooting|terror(?:ist|ism)|major\s+explosion|large\s+explosion|"
    r"earthquake|tsunami|hurricane|wildfire|state\s+of\s+emergency|"
    r"airstrike|air\s+strike|missile|drone|invasion|war|armed\s+conflict|"
    r"ceasefire|martial\s+law|coup|hostage|evacuation|major\s+attack|"
    r"کشتار|تیراندازی|انفجار|زلزله|سونامی|طوفان|آتش\s*سوزی|وضعیت\s+اضطراری|"
    r"حمله\s+هوایی|حمله\s+موشکی|موشک|پهپاد|تهاجم|جنگ|درگیری\s+مسلحانه|"
    r"آتش\s*بس|حکومت\s+نظامی|کودتا|گروگان|تخلیه|حمله\s+بزرگ|"
    r"دهها|ده‌ها|صدها|صدها\s+کشته|کشته\s+شدن|زخمی\s+شدن"
    r")",
    re.I,
)

MAJOR_ACTORS = re.compile(
    r"(?:iran|israel|united\s+states|america|russia|ukraine|china|taiwan|"
    r"north\s+korea|south\s+korea|japan|nato|united\s+nations|britain|uk|france|germany|"
    r"ایران|اسرائیل|آمریکا|روسیه|اوکراین|چین|تایوان|کره\s+شمالی|کره\s+جنوبی|ژاپن|ناتو|"
    r"سازمان\s+ملل|بریتانیا|انگلیس|فرانسه|آلمان)", re.I,
)


def _is_global_critical(candidate):
    text = " ".join(str(candidate.get(k, "") or "") for k in ("title", "summary", "description"))
    title = str(candidate.get("title", "") or "")
    if len(title) < 20 or not CRITICAL_TERMS.search(text):
        return False
    return bool(MAJOR_ACTORS.search(text) or re.search(r"\b\d{2,}\b", text))


def install():
    original = v13_intelligence.is_publishable

    def wrapped(main, candidate):
        ok, score, reason = original(main, candidate)
        if ok or not _is_global_critical(candidate):
            return ok, score, reason
        rescued = max(int(score or 0), int(v13_intelligence.MIN_EVENT_SCORE) + 5)
        print(f"V13 GLOBAL CRITICAL RESCUE: {candidate.get('title', '')}")
        return True, rescued, "global-critical-rescue"

    v13_intelligence.is_publishable = wrapped
    print("V13 GLOBAL CRITICAL RESCUE ACTIVE")
