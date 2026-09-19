"""V13 Event Fingerprint 2.0.

Purely local/free event identity layer.  It catches the same real-world
development even when publishers use substantially different wording, while
trying not to suppress genuine follow-up developments.

Fingerprint dimensions:
  actors/entities + location + action + object/family + agreement/event markers
  + numeric anchors + time context.

It is deliberately deterministic and does not call an external service.
"""

import re
import time
from datetime import datetime, timezone

EVENT_HISTORY_SECONDS = 72 * 3600

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
    "دانمارک": "denmark", "دانمارکی": "denmark", "denmark": "denmark",
    "گرینلند": "greenland", "greenland": "greenland",
    "کپنهاگ": "copenhagen", "copenhagen": "copenhagen",
    "نیویورک": "new_york", "new york": "new_york",
    "واشنگتن": "washington", "washington": "washington",
}

LOCATION_ALIASES = {
    "گرینلند": "greenland", "greenland": "greenland",
    "کپنهاگ": "copenhagen", "copenhagen": "copenhagen",
    "واشنگتن": "washington", "washington": "washington",
    "نیویورک": "new_york", "new york": "new_york",
    "اوکراین": "ukraine", "ukraine": "ukraine",
    "ایران": "iran", "iran": "iran",
    "اسرائیل": "israel", "israel": "israel",
    "روسیه": "russia", "russia": "russia",
    "چین": "china", "china": "china",
}

EVENT_FAMILIES = {
    "testosterone_testing": ("تستوسترون", "آزمایش تستوسترون", "testosterone", "testosterone testing"),
    "ceasefire": ("آتش‌بس", "آتش بس", "ceasefire"),
    "missile_attack": ("موشک", "حمله موشکی", "missile attack"),
    "airstrike": ("حمله هوایی", "airstrike", "air strike"),
    "nuclear_enrichment": ("غنی‌سازی", "غنی سازی", "enrichment"),
    "earthquake": ("زلزله", "earthquake"),
    "flood": ("سیل", "flood"),
    "fire": ("آتش‌سوزی", "آتش سوزی", "fire"),
    "explosion": ("انفجار", "explosion"),
    "interest_rates": ("نرخ بهره", "interest rate"),
    "ai_model": ("مدل هوش مصنوعی", "مدل زبانی", "ai model", "language model"),
    "greenland_security": (
        "گرینلند", "greenland", "امنیت گرینلند", "امنیتی گرینلند",
        "greenland security", "greenland defense", "greenland defence",
    ),
}

AGREEMENT_MARKERS = (
    "توافق", "توافقنامه", "پیمان", "معاهده", "قرارداد", "تفاهم", "موافقتنامه",
    "agreement", "accord", "deal", "pact", "treaty",
)

OBJECT_MARKERS = {
    "security": ("امنیت", "امنیتی", "دفاع", "دفاعی", "security", "defense", "defence"),
    "military_presence": ("حضور نظامی", "پایگاه نظامی", "نیروی نظامی", "military presence", "military base"),
    "investment": ("سرمایه‌گذاری", "سرمایه گذاری", "investment"),
    "troops": ("نیرو", "سرباز", "troops", "forces"),
    "testing": ("آزمایش", "testing", "test"),
    "weapons": ("موشک", "پهپاد", "سلاح", "missile", "drone", "weapon"),
    "election": ("انتخابات", "رأی‌گیری", "رای‌گیری", "election", "vote"),
    "tariff": ("تعرفه", "tariff"),
}

ACTION_MARKERS = {
    "agreement": AGREEMENT_MARKERS,
    "announce": ("اعلام کرد", "اعلام شد", "اعلام", "announced", "announces"),
    "sign": ("امضا", "امضا کردند", "امضا خواهد شد", "امضا شود", "sign", "signed", "signing"),
    "approve": ("تایید", "تأیید", "تصویب", "approved", "approve", "ratified"),
    "resume": ("از سر گرفت", "ازسرگیری", "از سرگیری", "دوباره آغاز", "resumed", "restarted", "reinstated"),
    "stop": ("متوقف کرد", "متوقف شد", "تعلیق", "لغو", "suspended", "stopped", "halted", "cancelled", "canceled", "banned"),
    "expand": ("گسترش", "افزایش", "تقویت", "expand", "expanded", "increase", "bolster"),
    "attack": ("حمله", "حمله کرد", "حمله شد", "attack", "attacked", "strike", "struck"),
}

POSITIVE_ACTIONS = (
    "به توافق رسید", "به توافق رسیدند", "به توافق رسیده", "reached agreement", "reached a deal",
    "از سر گرفت", "ازسرگیری", "از سرگیری", "دوباره آغاز", "آغاز کرد", "آغاز شد",
    "شروع کرد", "شروع شد", "بازگرداند", "بازگشت", "احیا کرد", "احیا شد",
    "تایید کرد", "تأیید کرد", "تصویب کرد", "resumed", "resume", "restarted",
    "restart", "restored", "approved", "launched", "started", "began", "reinstated",
)

NEGATIVE_ACTIONS = (
    "متوقف کرد", "متوقف شد", "تعلیق کرد", "تعلیق شد", "لغو کرد", "لغو شد",
    "پایان داد", "پایان یافت", "ممنوع کرد", "ممنوع شد", "توقف",
    "suspended", "suspend", "stopped", "stop", "halted", "halt",
    "cancelled", "canceled", "banned", "ended",
)

GENERIC = {
    "خبر", "گزارش", "اعلام", "اعلام کرد", "خبر داد", "گفت", "اظهار", "واکنش",
    "تصمیم", "تازه", "جدید", "مهم", "آخرین", "امروز", "درباره", "برای", "پس",
    "همزمان", "کشور", "دولت", "رئیس", "رئیس جمهور", "وزیر", "مقام", "منطقه",
    "جهان", "سیاست", "policy", "news", "report", "latest", "new", "says", "said",
    "amid", "over", "after", "will",
}

TIME_MARKERS = {
    "today": ("امروز", "today", "جمعه", "شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه"),
    "tomorrow": ("فردا", "tomorrow", "هفته آینده", "next week"),
    "next_week": ("هفته آینده", "next week", "هفته بعد"),
    "this_week": ("این هفته", "this week"),
    "tonight": ("امشب", "tonight"),
    "yesterday": ("دیروز", "yesterday"),
}

def _norm(text):
    value = str(text or "").lower()
    value = value.replace("ي", "ی").replace("ك", "ک")
    value = value.replace("\u200c", " ").replace("\u200f", " ")
    value = re.sub(r"[^\w\u0600-\u06ff]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def _contains(value, phrase):
    return _norm(phrase) in value

def _entities(text):
    value = _norm(text)
    return {canonical for alias, canonical in sorted(ENTITY_ALIASES.items(), key=lambda item: -len(item[0])) if _contains(value, alias)}

def _locations(text):
    value = _norm(text)
    return {canonical for alias, canonical in sorted(LOCATION_ALIASES.items(), key=lambda item: -len(item[0])) if _contains(value, alias)}

def _families(text):
    value = _norm(text)
    return {family for family, phrases in EVENT_FAMILIES.items() if any(_contains(value, phrase) for phrase in phrases)}

def _markers(text, mapping):
    value = _norm(text)
    return {key for key, phrases in mapping.items() if any(_contains(value, phrase) for phrase in phrases)}

def _tokens(text):
    value = _norm(text)
    return {token for token in value.split() if len(token) >= 3 and token not in GENERIC}

def _numbers(text):
    raw = str(text or "")
    normalized = raw.replace("٫", ".").replace("٬", ",")
    return set(re.findall(r"\b\d+(?:[.,]\d+)?\b", normalized))

def _action_profile(text):
    value = _norm(text)
    positive = any(_contains(value, item) for item in POSITIVE_ACTIONS)
    negative = any(_contains(value, item) for item in NEGATIVE_ACTIONS)
    return positive, negative

def _direction_conflict(text_a, text_b):
    a_pos, a_neg = _action_profile(text_a)
    b_pos, b_neg = _action_profile(text_b)
    return (a_pos and b_neg) or (a_neg and b_pos)

def _time_context(text):
    value = _norm(text)
    return {key for key, phrases in TIME_MARKERS.items() if any(_contains(value, phrase) for phrase in phrases)}

def _fingerprint(text):
    return {
        "entities": _entities(text),
        "locations": _locations(text),
        "families": _families(text),
        "actions": _markers(text, ACTION_MARKERS),
        "objects": _markers(text, OBJECT_MARKERS),
        "agreements": bool(_markers(text, {"agreement": AGREEMENT_MARKERS})),
        "numbers": _numbers(text),
        "times": _time_context(text),
        "tokens": _tokens(text),
    }

def event_score(title_a, title_b, summary_a="", summary_b=""):
    """Return conservative 0..1 confidence that two stories describe one event."""
    a = f"{title_a} {summary_a}".strip()
    b = f"{title_b} {summary_b}".strip()
    if not a or not b:
        return 0.0

    if _direction_conflict(a, b):
        return 0.0

    fa = _fingerprint(a)
    fb = _fingerprint(b)

    entities = fa["entities"] & fb["entities"]
    locations = fa["locations"] & fb["locations"]
    families = fa["families"] & fb["families"]
    actions = fa["actions"] & fb["actions"]
    objects = fa["objects"] & fb["objects"]
    numbers = fa["numbers"] & fb["numbers"]
    times = fa["times"] & fb["times"]
    tokens = fa["tokens"] & fb["tokens"]

    # Strong event identity: concrete family + actor/location + concrete action/object.
    if families and entities and (locations or actions or objects) and len(tokens) >= 1:
        return 0.99
    if families and locations and entities and (actions or objects):
        return 0.98

    # Agreement/deal events are especially prone to headline paraphrases.
    if fa["agreements"] and fb["agreements"] and entities and locations and objects:
        return 0.98
    if fa["agreements"] and fb["agreements"] and entities and locations and len(tokens) >= 2:
        return 0.96

    # Numeric anchors make otherwise-similar developments materially stronger.
    if entities and locations and numbers and (actions or objects) and len(tokens) >= 2:
        return 0.97
    if entities and numbers and len(tokens) >= 3:
        return 0.93

    # Existing conservative rules retained for known event families.
    if families and entities and len(tokens) >= 2:
        return 0.98
    if families and entities and len(tokens) >= 1:
        return 0.95
    if families and len(tokens) >= 3:
        return 0.94
    if families and len(tokens) >= 2:
        return 0.90

    if entities and len(tokens) >= 3:
        return 0.88

    # A shared explicit time context is useful only as a tie-breaker; it never
    # creates a duplicate by itself.
    if entities and locations and times and len(tokens) >= 3:
        return 0.90

    return 0.0

def fingerprint_debug(text):
    """Small deterministic diagnostic surface used by regression tests."""
    fp = _fingerprint(text)
    return {key: sorted(value) if isinstance(value, set) else value for key, value in fp.items()}

def install(core):
    original_history = core.history_contains_story
    original_penalty = core.diversity_penalty
    original_process = core.process_news

    def history_contains_story(title, title_history, summary=""):
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
            score = event_score(title, old_title, summary, "")
            if score >= 0.90:
                print(f"V13 EVENT DEDUP 2.0: BLOCKED | score={score:.2f} | existing={old_title} | candidate={title}")
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
            if score >= 0.98:
                penalty += 70
            elif score >= 0.95:
                penalty += 60
            elif score >= 0.90:
                penalty += 50
            elif score >= 0.88:
                penalty += 35
        penalty = min(penalty, 95)
        if penalty > base_penalty:
            print(f"V13 EVENT DIVERSITY 2.0: +{penalty - base_penalty} | {candidate.get('title', '')}")
        return penalty

    def process_news(candidate, hash_history, title_history, *args, **kwargs):
        title = candidate.get("title", "") if isinstance(candidate, dict) else ""
        summary = candidate.get("summary", "") if isinstance(candidate, dict) else ""
        if title and history_contains_story(title, title_history, summary):
            print(f"V13 EVENT DEDUP 2.0: PRE-PUBLISH BLOCK | {title}")
            return False
        return original_process(candidate, hash_history, title_history, *args, **kwargs)

    core.history_contains_story = history_contains_story
    core.diversity_penalty = diversity_penalty
    core.process_news = process_news
    print("V13 EVENT FINGERPRINT 2.0 ACTIVE | window=72h | threshold=0.90 | pre-publish=ON")
