"""V13 event-level duplicate protection.

Purely local/free. This layer catches the same real-world event when
different publishers/headlines use materially different wording.
It complements exact URL/hash and topic-level similarity checks.
"""

import re
import time

EVENT_HISTORY_SECONDS = 72 * 3600

# Canonical organizations/actors that strongly anchor an event.
ENTITY_ALIASES = {
    "پنتاگون": "pentagon", "pentagon": "pentagon",
    "کاخ سفید": "white_house", "white house": "white_house",
    "وزارت دفاع آمریکا": "us_defense", "وزارت دفاع امریکا": "us_defense",
    "اف بی آی": "fbi", "fbi": "fbi",
    "سیا": "cia", "cia": "cia",
    "ناتو": "nato", "nato": "nato",
    "سازمان ملل": "un", "united nations": "un",
    "ترامپ": "trump", "دونالد ترامپ": "trump", "trump": "trump",
    "پوتین": "putin", "ولادیمیر پوتین": "putin", "putin": "putin",
    "مکرون": "macron", "امانوئل مکرون": "macron", "macron": "macron",
    "ایران": "iran", "ایرانی": "iran", "iran": "iran",
    "آمریکا": "usa", "امریکا": "usa", "ایالات متحده": "usa",
    "اسرائیل": "israel", "اسرائیلی": "israel", "israel": "israel",
    "روسیه": "russia", "روسی": "russia", "russia": "russia",
    "چین": "china", "چینی": "china", "china": "china",
    "اوکراین": "ukraine", "اوکراینی": "ukraine", "ukraine": "ukraine",
}

# Event families prevent false positives between unrelated stories sharing
# the same organization/person. Each family contains distinctive anchors.
EVENT_FAMILIES = {
    "testosterone_testing": (
        "تستوسترون", "آزمایش تستوسترون", "testosterone", "testosterone testing",
    ),
    "military_policy": (
        "نظامیان", "نظامی", "ارتش", "نیروهای مسلح", "troops", "military",
        "soldiers", "policy",
    ),
    "ceasefire": ("آتش‌بس", "آتش بس", "ceasefire"),
    "missile_attack": ("موشک", "حمله موشکی", "missile", "missile attack"),
    "airstrike": ("حمله هوایی", "airstrike", "air strike"),
    "sanctions": ("تحریم", "تحریم‌ها", "sanctions", "sanction"),
    "nuclear_enrichment": ("غنی‌سازی", "غنی سازی", "enrichment", "nuclear"),
    "election": ("انتخابات", "رأی‌گیری", "رای‌گیری", "election", "vote"),
    "earthquake": ("زلزله", "earthquake"),
    "flood": ("سیل", "flood"),
    "fire": ("آتش‌سوزی", "آتش سوزی", "fire"),
    "explosion": ("انفجار", "explosion"),
    "oil_supply": ("نفت", "عرضه نفت", "oil", "oil supply"),
    "energy_price": ("قیمت انرژی", "انرژی", "energy price", "energy"),
    "interest_rates": ("نرخ بهره", "interest rate", "rates"),
    "ai_model": ("مدل هوش مصنوعی", "مدل زبانی", "ai model", "language model"),
}

GENERIC = {
    "خبر", "گزارش", "اعلام", "اعلام کرد", "خبر داد", "گفت", "اظهار",
    "واکنش", "تصمیم", "تازه", "جدید", "مهم", "آخرین", "امروز", "درباره",
    "برای", "پس", "همزمان", "کشور", "دولت", "رئیس", "رئیس جمهور", "وزیر",
    "مقام", "منطقه", "جهان", "سیاست", "policy", "news", "report", "latest",
    "new", "says", "said", "amid", "over", "after", "will",
}

def _norm(text):
    value = str(text or "").lower()
    value = value.replace("ي", "ی").replace("ك", "ک")
    value = value.replace("\u200c", " ").replace("\u200f", " ")
    value = re.sub(r"[^\w\u0600-\u06ff]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def _entities(text):
    value = _norm(text)
    return {
        canonical
        for alias, canonical in sorted(
            ENTITY_ALIASES.items(), key=lambda item: -len(item[0])
        )
        if _norm(alias) in value
    }

def _families(text):
    value = _norm(text)
    return {
        family
        for family, phrases in EVENT_FAMILIES.items()
        if any(_norm(phrase) in value for phrase in phrases)
    }

def _tokens(text):
    value = _norm(text)
    return {
        token for token in value.split()
        if len(token) >= 3 and token not in GENERIC
    }

def _numbers(text):
    return set(re.findall(r"\b\d+(?:[.,]\d+)?\b", str(text or "")))

def event_score(title_a, title_b, summary_a="", summary_b=""):
    """Return a conservative 0..1 same-event confidence."""
    a = f"{title_a} {summary_a}"
    b = f"{title_b} {summary_b}"

    entities = _entities(a) & _entities(b)
    families = _families(a) & _families(b)
    tokens = _tokens(a) & _tokens(b)
    numbers = _numbers(a) & _numbers(b)

    # A named event family plus a shared actor is the strongest signal.
    if families and entities and len(tokens) >= 2:
        return 0.98
    if families and entities and len(tokens) >= 1:
        return 0.95

    # Distinctive event vocabulary can stand alone when sufficiently strong.
    if families and len(tokens) >= 3:
        return 0.94
    if families and len(tokens) >= 2:
        return 0.90

    # Numeric anchors make otherwise similar operational events safer to join.
    if entities and len(tokens) >= 3 and numbers:
        return 0.93
    if entities and len(tokens) >= 3:
        return 0.88

    return 0.0

def install(core):
    original_history = core.history_contains_story
    original_penalty = core.diversity_penalty
    original_process = core.process_news

    def history_contains_story(title, title_history):
        if original_history(title, title_history):
            return True

        now = int(time.time())
        for timestamp, old_title in title_history:
            try:
                age = now - int(timestamp)
            except Exception:
                continue
            if age < 0 or age > EVENT_HISTORY_SECONDS:
                continue

            score = event_score(title, old_title)
            if score >= 0.90:
                print(
                    f"V13 EVENT DEDUP: BLOCKED | score={score:.2f} | "
                    f"existing={old_title} | candidate={title}"
                )
                return True

        return False

    def diversity_penalty(candidate, selected):
        penalty = original_penalty(candidate, selected)
        base_penalty = penalty

        for used in selected:
            score = event_score(
                candidate.get("title", ""),
                used.get("title", ""),
                candidate.get("summary", ""),
                used.get("summary", ""),
            )
            if score >= 0.95:
                penalty += 65
            elif score >= 0.90:
                penalty += 55
            elif score >= 0.88:
                penalty += 40

        penalty = min(penalty, 90)
        if penalty > base_penalty:
            print(
                f"V13 EVENT DIVERSITY: +{penalty - base_penalty} | "
                f"{candidate.get('title', '')}"
            )
        return penalty

    def process_news(candidate, hash_history, title_history, *args, **kwargs):
        title = candidate.get("title", "") if isinstance(candidate, dict) else ""
        if title and history_contains_story(title, title_history):
            print(f"V13 EVENT DEDUP: PRE-PUBLISH BLOCK | {title}")
            return False
        return original_process(candidate, hash_history, title_history, *args, **kwargs)

    core.history_contains_story = history_contains_story
    core.diversity_penalty = diversity_penalty
    core.process_news = process_news

    print(
        "V13 EVENT DEDUP ENGINE ACTIVE | "
        "window=72h | threshold=0.90 | pre-publish=ON"
    )
