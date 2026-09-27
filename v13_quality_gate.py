"""NABZ V13 quality gate.

A deterministic, free editorial layer that raises the bar for story selection
without replacing the existing intelligence/rescue stack.
"""
import re
import v13_intelligence

# Strong, observable events: these deserve priority over generic statements.
MASS_IMPACT = re.compile(
    r"(?:mass\s+shooting|mass\s+casualt|multiple\s+people\s+killed|dozens\s+killed|"
    r"hundreds\s+killed|\b\d{2,}\s+(?:people|killed|dead|wounded)\b|"
    r"کشتار|تلفات\s+سنگین|ده(?:ها|ها)\s+کشته|صدها\s+کشته|\d{2,}\s*(?:کشته|کشته‌شده|کشته\s+شد|زخمی|مجروح))",
    re.I,
)

BREAKING_EVENT = re.compile(
    r"(?:killed|dead|wounded|missing|arrested|explosion|blast|earthquake|tsunami|"
    r"wildfire|flood|evacuated|evacuation|airstrike|air\s+strike|missile|drone\s+strike|"
    r"attack|shooting|hostage|coup|invasion|war|ceasefire|airport\s+closed|flights?\s+suspended|"
    r"کشته|کشته\s+شد|زخمی|مجروح|مفقود|بازداشت|انفجار|زلزله|سیل|آتش\s*سوزی|تخلیه|"
    r"حمله|حمله\s+هوایی|حمله\s+موشکی|موشک|پهپاد|تیراندازی|گروگان|کودتا|تهاجم|جنگ|"
    r"آتش\s*بس|بسته\s+شدن\s+فرودگاه|تعلیق\s+پرواز|لغو\s+پرواز)",
    re.I,
)

MAJOR_DECISION = re.compile(
    r"(?:sanction|sanctions|ban|banned|suspend|suspended|approve|approved|signed|agreement|"
    r"deal|treaty|ceasefire|resign|resigned|elected|election|court\s+ruling|nuclear|"
    r"تحریم|تحریم‌ها|تحریمها|ممنوع|ممنوعیت|تعلیق|تصویب|امضا|توافق|معاهده|آتش\s*بس|"
    r"استعفا|انتخاب|انتخابات|حکم\s+دادگاه|هسته‌ای|هسته ای)", re.I,
)

ROUTINE_ONLY = re.compile(
    r"(?:دیدار|سفر|مراسم|همایش|گرامیداشت|تبریک|تسلیت|پیام|اظهارات|سخنان|"
    r"دیدگاه|نقش\s+محوری|نقش\s+مهم|ضرورت|لزوم|خواستار|واکنش|تأکید|تاکید|"
    r"meeting|visit|ceremony|remarks|statement|calls?\s+for|urges?|praises?)",
    re.I,
)


def _text(candidate):
    return " ".join(str(candidate.get(k, "") or "") for k in ("title", "summary", "description", "article_text"))


def _quality_bonus(candidate):
    title = str(candidate.get("title", "") or "")
    body = _text(candidate)
    t = (title + " " + body[:3500]).lower()
    bonus = 0
    if MASS_IMPACT.search(t):
        bonus += 9
    elif BREAKING_EVENT.search(title.lower()):
        bonus += 5
    elif BREAKING_EVENT.search(body[:1600].lower()):
        bonus += 2
    if MAJOR_DECISION.search(title.lower()):
        bonus += 4
    # A precise number/date/location is stronger evidence than vague commentary.
    if re.search(r"\b\d{1,4}(?:[.,]\d+)?\b", title):
        bonus += 2
    if re.search(r"(?:ایران|آمریکا|اسرائیل|روسیه|اوکراین|چین|ترکیه|فرانسه|بریتانیا|عراق|ناتو|"
                 r"iran|united states|israel|russia|ukraine|china|turkey|france|uk|iraq|nato)", title, re.I):
        bonus += 2
    # Generic commentary should never outrank a concrete event merely because
    # it contains a high-profile actor.
    if ROUTINE_ONLY.search(title) and not (MASS_IMPACT.search(title) or BREAKING_EVENT.search(title) or MAJOR_DECISION.search(title)):
        bonus -= 5
    return bonus


def install():
    original_score = v13_intelligence.event_score
    original_publishable = v13_intelligence.is_publishable

    def quality_score(main, candidate):
        base = int(original_score(main, candidate) or 0)
        return base + _quality_bonus(candidate)

    def quality_publishable(main, candidate):
        ok, score, reason = original_publishable(main, candidate)
        if not ok:
            return ok, score, reason
        qscore = max(int(score or 0), quality_score(main, candidate))
        # Never rescue generic commentary here. Concrete events can receive
        # the quality bonus, while the existing intelligence/rescue rules
        # remain authoritative for publication safety.
        return True, qscore, reason

    v13_intelligence.event_score = quality_score
    v13_intelligence.is_publishable = quality_publishable
    print("V13 QUALITY GATE: high-impact event ranking active")
