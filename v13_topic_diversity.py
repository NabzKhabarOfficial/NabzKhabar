"""V13 topic-level diversity and event-repeat protection.

Purely local/free: no network calls and no new secrets.
This layer complements, rather than replaces, exact/semantic deduplication.
"""

import re
import time

ENTITY_ALIASES = {
    "امانوئل مکرون": "macron", "امانوئل ماکرون": "macron",
    "مکرون": "macron", "ماکرون": "macron", "macron": "macron",
    "گروه هفت": "g7", "گروه ۷": "g7", "g7": "g7", "g-7": "g7",
    "دونالد ترامپ": "trump", "ترامپ": "trump", "trump": "trump",
    "ولادیمیر پوتین": "putin", "پوتین": "putin",
    "روسیه": "russia", "روسی": "russia", "russia": "russia",
    "آمریکا": "usa", "امریکا": "usa", "ایالات متحده": "usa",
    "آمریکایی": "usa", "usa": "usa",
    "اسرائیل": "israel", "اسرائیلی": "israel", "israel": "israel",
    "ایران": "iran", "ایرانی": "iran", "iran": "iran",
    "چین": "china", "چینی": "china", "china": "china",
    "اوکراین": "ukraine", "اوکراینی": "ukraine", "ukraine": "ukraine",
    "زلنسکی": "zelensky", "ولودیمیر زلنسکی": "zelensky",
    "نتانیاهو": "netanyahu", "بنیامین نتانیاهو": "netanyahu",
    "حوثی": "houthis", "حوثی‌ها": "houthis", "حوثی ها": "houthis",
    "انصارالله": "houthis", "حزب‌الله": "hezbollah", "حزب الله": "hezbollah",
    "ناتو": "nato", "اتحادیه اروپا": "eu", "اروپا": "europe",
    "پنتاگون": "pentagon", "کاخ سفید": "white_house",
}

TOPIC_GROUPS = {
    "energy": ("انرژی", "نفت", "گاز", "سوخت", "بنزین", "برق", "ذخایر", "energy", "oil", "gas", "fuel"),
    "diplomacy": ("نشست", "مذاکره", "مذاکرات", "دیدار", "رایزنی", "اجلاس", "گفت‌وگو", "گفتگو", "دیپلماتیک", "diplomacy", "talks", "summit", "meeting"),
    "conflict": ("جنگ", "حمله", "حملات", "درگیری", "موشک", "بمباران", "آتش‌بس", "آتش بس", "عملیات نظامی", "تلفات", "حملات ترکیبی", "conflict", "war", "attack", "missile", "ceasefire"),
    "nuclear": ("هسته‌ای", "هسته ای", "غنی‌سازی", "غنی سازی", "راکتور", "nuclear", "enrichment"),
    "economy": ("اقتصاد", "تورم", "بازار", "قیمت", "مالیات", "سهام", "بورس", "بانک", "رکود", "اقتصادی", "economy", "inflation", "market"),
    "ai": ("هوش مصنوعی", "مدل زبانی", "یادگیری ماشین", "چت‌بات", "چت بات", "هوش مصنوعی مولد", "artificial intelligence", "machine learning"),
    "technology": ("فناوری", "تکنولوژی", "نرم‌افزار", "نرم افزار", "گوشی", "موبایل", "تراشه", "پردازنده", "اینترنت", "technology", "software", "chip"),
    "health": ("پزشکی", "سلامت", "بیمارستان", "درمان", "بیماری", "واکسن", "اورژانس", "health", "medical", "hospital"),
    "sports": ("فوتبال", "بسکتبال", "والیبال", "تنیس", "المپیک", "لیگ", "جام جهانی", "ورزش", "football", "basketball", "tennis", "sports"),
    "education": ("دانشگاه", "دانش‌آموز", "دانش آموز", "مدرسه", "آموزش", "دانشجو", "education", "school", "university"),
    "disaster": ("زلزله", "سیل", "آتش‌سوزی", "آتش سوزی", "انفجار", "سقوط", "طوفان", "earthquake", "flood", "fire", "explosion"),
}

GENERIC = {"خبر","گزارش","اعلام","خبر داد","گفت","اظهار","واکنش","تصمیم","تازه","جدید","مهم","آخرین","امروز","درباره","برای","پس","همزمان","کشور","دولت","رئیس","رئیس جمهور","وزیر","مقام","منطقه","جهان"}

def _norm(text):
    text = str(text or "").lower().replace("ي", "ی").replace("ك", "ک")
    text = text.replace("\u200c", " ")
    return re.sub(r"\s+", " ", text).strip()

def _entities(text):
    v = _norm(text)
    return {canon for alias, canon in sorted(ENTITY_ALIASES.items(), key=lambda x: -len(x[0])) if alias in v}

def _topics(text):
    v = _norm(text)
    return {topic for topic, phrases in TOPIC_GROUPS.items() if any(_norm(p) in v for p in phrases)}

def _tokens(text):
    v = re.sub(r"[^\w\u0600-\u06ff]+", " ", _norm(text))
    return {x for x in v.split() if len(x) >= 3 and x not in GENERIC}

def similarity(title_a, title_b, summary_a="", summary_b=""):
    a = {"e": _entities(f"{title_a} {summary_a}"), "t": _topics(f"{title_a} {summary_a}"), "w": _tokens(f"{title_a} {summary_a}")}
    b = {"e": _entities(f"{title_b} {summary_b}"), "t": _topics(f"{title_b} {summary_b}"), "w": _tokens(f"{title_b} {summary_b}")}
    e, t, w = a["e"] & b["e"], a["t"] & b["t"], a["w"] & b["w"]

    if len(e) >= 3 and t: return 0.98
    if len(e) >= 2 and t: return 0.90
    if len(e) >= 2 and len(w) >= 1: return 0.80
    if len(e) == 1 and t and len(w) >= 4: return 0.72
    if len(e) == 1 and t and len(w) >= 2: return 0.62
    return 0.0

def install(core):
    original_history = core.history_contains_story
    original_penalty = core.diversity_penalty

    def history_contains_story(title, title_history):
        if original_history(title, title_history):
            return True
        now = int(time.time())
        for timestamp, old_title in title_history:
            try:
                age = now - int(timestamp)
            except Exception:
                continue
            if age < 0 or age > 48 * 3600:
                continue
            score = similarity(title, old_title)
            if score >= 0.90:
                print(f"V13 TOPIC DEDUP: blocked | score={score:.2f} | {title}")
                return True
        return False

    def diversity_penalty(candidate, selected):
        penalty = original_penalty(candidate, selected)
        for used in selected:
            score = similarity(
                candidate.get("title", ""),
                used.get("title", ""),
                candidate.get("summary", ""),
                used.get("summary", ""),
            )
            if score >= 0.90:
                penalty += 55
            elif score >= 0.80:
                penalty += 38
            elif score >= 0.62:
                penalty += 22
        penalty = min(penalty, 75)
        if penalty > original_penalty(candidate, selected):
            print(f"V13 TOPIC DIVERSITY: +{penalty - original_penalty(candidate, selected)} | {candidate.get('title','')}")
        return penalty

    core.history_contains_story = history_contains_story
    core.diversity_penalty = diversity_penalty
    print("V13 TOPIC DIVERSITY ENGINE ACTIVE | history=48h | event threshold=0.90")
