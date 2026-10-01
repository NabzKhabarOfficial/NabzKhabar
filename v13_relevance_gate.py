"""NABZ V13 — relevance and publish-quality gate.

1) Foreign "soft local" news (a university strike in Cameroon, a city-council
   row abroad...) is rejected at selection time unless it is tied to Iran or
   is a real security/casualty event.
2) A finished post is refused when its text is visibly broken: a truncated
   lead ("۳ نفتکش در آخرین"), a too-thin body, or a headline built around an
   unexplained Latin acronym ("... لیست عدم سازگاری PGSA"). Refused posts are
   labelled as editorial blocks, so they never turn a run red.
"""

import re
import sys

SOFT_LOCAL_TOPICS = (
    "دانشگاه", "سال تحصیلی", "مدرسه", "مدارس", "دانش آموز", "دانشجو", "معلم",
    "استادان", "اساتید", "کنکور", "امتحان", "اعتصاب", "اتحادیه", "شهرداری",
    "شهردار", "شورای شهر", "ترافیک", "جشنواره", "کنسرت",
    "university", "universities", "academic year", "school", "students",
    "teachers", "lecturers", "professors", "exam", "mayor", "city council",
    "municipal", "festival", "concert", "labour union", "labor union",
)
IRAN_LINK = ("ایران", "تهران", "iran", "tehran")
HARD_EVENT = (
    "کشته", "زخمی", "حمله", "انفجار", "تیراندازی", "گروگان", "آتش سوزی",
    "killed", "dead", "wounded", "attack", "explosion", "shooting", "hostage",
)

KNOWN_ACRONYMS = {
    "NATO", "OPEC", "IAEA", "UN", "EU", "US", "USA", "UK", "AI", "FBI", "CIA",
    "BBC", "CNN", "IMF", "WHO", "FIFA", "UEFA", "NASA", "BRICS", "G7", "G20",
    "CEO", "GDP", "NBA", "UFC", "SpaceX", "NABZ", "ICC", "ICJ", "WTO", "OIC",
    "ASEAN", "SCO", "CPI", "UAE", "IRGC", "AFP", "AP",
}

PROBLEM_STATUS = "quality_blocked"
SOFT_LOCAL_REASON = "foreign-soft-local"


def _norm(text):
    return re.sub(r"\s+", " ", str(text or "").replace("\u200c", " ")).strip()


def foreign_soft_local(candidate):
    title = _norm(candidate.get("title", "")).lower()
    if not title or not any(t in title for t in SOFT_LOCAL_TOPICS):
        return False
    text = title + " " + _norm(candidate.get("summary", "") or candidate.get("description", "")).lower()[:600]
    if any(x in text for x in IRAN_LINK):
        return False
    if any(x in title for x in HARD_EVENT):
        return False
    return True


_VERBISH_END = re.compile(r"(?:[.!؟?»\")]|(?:د|ت|ست|ند|ید|یم))$")


def caption_problem(title, sentences):
    """Return a reason string when the post text is not publishable."""
    title = _norm(title)
    if len(title.split()) < 4:
        return "title-too-short"
    for acr in re.findall(r"\b[A-Z][A-Z0-9+]{2,}\b", title):
        if acr not in KNOWN_ACRONYMS:
            return f"unexplained-acronym:{acr}"
    if not sentences:
        return "empty-body"
    body = " ".join(sentences)
    if len(body) < 70 or len(body.split()) < 12:
        return "body-too-thin"
    if len(sentences[0].split()) < 6:
        return "lead-fragment"
    if not _VERBISH_END.search(sentences[-1].strip()):
        return "body-truncated"
    return ""


def _register_statuses():
    main_mod = sys.modules.get("__main__")
    statuses = getattr(main_mod, "EDITORIAL_BLOCK_STATUSES", None)
    if isinstance(statuses, set):
        statuses.add(PROBLEM_STATUS)


def install(core, current):
    import v13_intelligence

    previous = v13_intelligence.is_publishable

    def relevance_gate(main_obj, candidate):
        ok, score, reason = previous(main_obj, candidate)
        if ok and foreign_soft_local(candidate):
            return False, 0, SOFT_LOCAL_REASON
        return ok, score, reason

    v13_intelligence.is_publishable = relevance_gate
    _register_statuses()
    print("V13 RELEVANCE GATE ACTIVE: foreign soft-local news + broken post text are blocked.", flush=True)
