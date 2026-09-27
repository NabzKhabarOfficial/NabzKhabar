"""NABZ V13 — conservative global critical-news rescue.

Prevents freshness/editorial stages from silently losing high-impact world
events merely because the item is older than the normal freshness window.
No API or paid service is used.
"""
import re
import v13_intelligence

CRITICAL_TERMS = re.compile(
    r"(?:"
    r"mass\s+shooting|mass\s+casualt|major\s+explosion|large\s+explosion|building\s+explosion|"
    r"major\s+fire|earthquake|tsunami|hurricane|wildfire|flood|state\s+of\s+emergency|"
    r"airstrike|air\s+strike|missile|drone|invasion|war|armed\s+conflict|ceasefire|"
    r"martial\s+law|coup|hostage|evacuation|major\s+attack|terror(?:ist|ism)|airport\s+closed|"
    r"flights?\s+suspended|embassy\s+attack|nuclear\s+incident|major\s+security|"
    r"killed|dead|wounded|missing|casualties|dozens|hundreds|"
    r"کشتار|تیراندازی|انفجار|زلزله|سونامی|طوفان|آتش\s*سوزی|سیل|وضعیت\s+اضطراری|"
    r"حمله\s+هوایی|حمله\s+موشکی|موشک|پهپاد|تهاجم|جنگ|درگیری\s+مسلحانه|"
    r"آتش\s*بس|حکومت\s+نظامی|کودتا|گروگان|تخلیه|حمله\s+بزرگ|حمله\s+تروریستی|"
    r"فرودگاه\s+(?:بسته|تعطیل)|تعلیق\s+پرواز|لغو\s+پرواز|کشته|کشته\s+شد|زخمی|مجروح|"
    r"مفقود|تلفات|دهها|ده‌ها|صدها|صدها\s+کشته|بازداشت\s+گسترده"
    r")",
    re.I,
)

MAJOR_ACTORS = re.compile(
    r"(?:iran|israel|united\s+states|america|russia|ukraine|china|taiwan|"
    r"north\s+korea|south\s+korea|japan|nato|united\s+nations|britain|uk|france|germany|"
    r"turkey|iraq|saudi|qatar|uae|yemen|lebanon|syria|palestine|gaza|"
    r"ایران|اسرائیل|آمریکا|روسیه|اوکراین|چین|تایوان|کره\s+شمالی|کره\s+جنوبی|ژاپن|ناتو|"
    r"سازمان\s+ملل|بریتانیا|انگلیس|فرانسه|آلمان|ترکیه|عراق|عربستان|قطر|امارات|یمن|لبنان|سوریه|فلسطین|غزه)", re.I,
)


def _is_global_critical(candidate):
    text = " ".join(str(candidate.get(k, "") or "") for k in ("title", "summary", "description"))
    title = str(candidate.get("title", "") or "")
    if len(title) < 20 or not CRITICAL_TERMS.search(text):
        return False

    # A major actor or a quantified casualty/scale signal is required. This
    # prevents generic foreign commentary from bypassing freshness controls.
    quantified = bool(re.search(r"\b\d{2,}\b|دهها|ده‌ها|صدها|dozens|hundreds|mass", text, re.I))
    return bool(MAJOR_ACTORS.search(text) or quantified)


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
