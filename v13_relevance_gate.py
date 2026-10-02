"""NABZ V13 — relevance, sports and publish-quality gate.

1) Unimportant local news is rejected at selection time:
   * foreign "soft local" stories (a university strike in Cameroon, a city
     council row, a festival, a single local crime abroad);
   * Iranian provincial/city routine (a governor's visit, a local office
     opening) unless it carries a national or public-safety signal.
2) Major sports news is let in: Iran national teams and Iranian athletes on
   the world stage, decisive stages of major tournaments, the Tehran derby,
   world records and the Ballon d'Or. Routine league games, rumours and
   interviews stay out. Sports get editorial tier 2 (3 for decisive Iran
   national-team results), so they never displace war or crisis news.
3) A finished post is refused when its text is visibly broken: a truncated
   lead, a too-thin body, or a headline built around an unexplained Latin
   acronym. Refused posts are labelled editorial blocks (never a red run).
"""

import re
import sys

PERSIAN = r"\u0600-\u06FF"


def _word_re(words):
    alt = "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))
    return re.compile(rf"(?<![\w{PERSIAN}])(?:{alt})(?![\w{PERSIAN}])", re.I)


def _norm(text):
    text = str(text or "").replace("\u200c", " ").replace("ي", "ی").replace("ك", "ک")
    return re.sub(r"\s+", " ", text).strip()


def _title(candidate):
    return _norm(candidate.get("title", "")).lower()


def _text(candidate, limit=800):
    extra = _norm(candidate.get("summary", "") or candidate.get("description", "")).lower()[:limit]
    return _title(candidate) + " " + extra


IRAN_LINK = _word_re(("ایران", "ایرانی", "تهران", "iran", "iranian", "tehran"))

# --------------------------------------------------------------------------
# Foreign soft-local news
# --------------------------------------------------------------------------

SOFT_LOCAL = _word_re((
    "دانشگاه", "دانشگاه ها", "سال تحصیلی", "مدرسه", "مدارس", "دانش آموز", "دانش آموزان",
    "دانشجو", "دانشجویان", "معلم", "معلمان", "استادان", "اساتید", "کنکور", "امتحان",
    "اعتصاب", "اتحادیه", "شهرداری", "شهردار", "شورای شهر", "ترافیک", "جشنواره",
    "کنسرت", "خواننده", "بازیگر", "سلبریتی", "ازدواج", "طلاق", "باغ وحش", "پیش بینی هوا",
    "انتخابات محلی", "university", "universities", "academic year", "school", "schools",
    "students", "teachers", "lecturers", "professors", "exam", "mayor", "city council",
    "municipal", "festival", "concert", "celebrity", "singer", "actor", "actress",
    "wedding", "divorce", "zoo", "local election", "labour union", "labor union",
))
LOCAL_CRIME = _word_re((
    "پلیس", "دادگاه", "سرقت", "دزدی", "قتل", "تصادف", "زندان", "محکوم", "بازداشت",
    "police", "court", "theft", "robbery", "murder", "accident", "jail", "prison",
    "sentenced", "arrested",
))
GLOBAL_ACTOR = _word_re((
    "آمریکا", "روسیه", "چین", "اسرائیل", "سازمان ملل", "ترامپ", "پوتین", "ناتو",
    "اتحادیه اروپا", "دیوان بین المللی", "دادگاه لاهه", "شورای امنیت",
    "united states", "russia", "china", "israel", "united nations", "trump", "putin",
    "nato", "european union", "icc", "icj", "security council",
))
MASS_EVENT = re.compile(
    r"(?:حمله|انفجار|تیراندازی|گروگان|ترور|زلزله|سیل|سونامی|ده ?ها کشته|صدها کشته|"
    r"[۵-۹\d]{1,}\s*(?:نفر\s*)?کشته|attack|explosion|shooting|hostage|terror|earthquake|"
    r"flood|tsunami|dozens killed|hundreds killed|\b(?:[5-9]|\d{2,})\s+(?:people\s+)?killed)",
    re.I,
)


def foreign_soft_local(candidate):
    title = _title(candidate)
    if not title:
        return False
    text = _text(candidate)
    if IRAN_LINK.search(text) or MASS_EVENT.search(title):
        return False
    if SOFT_LOCAL.search(title):
        return True
    if LOCAL_CRIME.search(title) and not GLOBAL_ACTOR.search(text):
        return True
    return False

# --------------------------------------------------------------------------
# Iranian provincial / city routine
# --------------------------------------------------------------------------

IRAN_LOCAL = _word_re((
    "استان", "استانداری", "استاندار", "معاون استاندار", "فرماندار", "فرمانداری",
    "بخشدار", "بخشداری", "دهیار", "دهیاری", "شهرستان", "شهردار", "شهرداری",
    "شورای شهر", "مدیرکل", "اداره کل", "امام جمعه", "نماینده مردم",
    "آذربایجان شرقی", "آذربایجان غربی", "اردبیل", "البرز", "ایلام", "بوشهر",
    "چهارمحال", "خراسان", "خراسان رضوی", "خراسان جنوبی", "خراسان شمالی", "خوزستان",
    "زنجان", "سمنان", "سیستان و بلوچستان", "استان فارس", "قزوین", "کردستان", "کرمان",
    "کرمانشاه", "کهگیلویه", "گلستان", "گیلان", "لرستان", "مازندران", "استان مرکزی",
    "هرمزگان", "همدان", "یزد", "تبریز", "ارومیه", "شیراز", "اهواز", "کرج", "رشت",
    "ساری", "گرگان", "یاسوج", "بیرجند", "بجنورد", "زاهدان", "سنندج", "خرم آباد",
    "اراک", "بندرعباس", "شهرکرد", "دزفول", "آبادان", "کاشان", "قشم", "کیش",
))
IRAN_LOCAL_EXCEPTION = re.compile(
    r"(?:کشته|جان باخت|زخمی|زلزله|سیل|انفجار|آتش ?سوزی|حمله|تیراندازی|ترور|اعتراض|تجمع|"
    r"سراسری|کشوری|ملی|دولت|مجلس|رئیس ?جمهور|وزیر|تحریم|هسته|موشک|پهپاد|نفت|گاز|"
    r"قطعی برق|قطع برق|قطعی آب|کمبود|اعدام|میلیارد|تنگه هرمز|خلیج فارس|ریزگرد|آلودگی شدید)",
    re.I,
)


SERVICE_SCHEDULE = re.compile(
    r"(?:جدول|برنامه|زمان ?بندی|ساعات|ساعت های)\s*(?:\S+\s+){0,3}?(?:قطع|قطعی|خاموشی|خاموشی های|محدودیت)"
    r"|(?:قطع|قطعی|خاموشی)\s*(?:برق|آب|گاز)\s*(?:\S+\s+){0,6}?(?:جدول|برنامه ریزی شده|زمان ?بندی)"
    r"|power cut schedule|outage schedule|load ?shedding schedule",
    re.I,
)
LOW_VALUE = _word_re((
    "یادداشت", "سرمقاله", "دیدگاه", "تحلیل", "تحلیلگر", "اندیشکده", "نیویورکر",
    "درس هایی از", "روایت", "گفت و گو با", "مصاحبه با", "پادکست", "معرفی کتاب",
    "هدفون", "ایربادز", "ایرباد", "گلکسی بادز", "ایرپادز", "ساعت هوشمند", "رونمایی از گوشی",
    "قیمت گوشی", "بررسی گوشی", "حراج",
    "opinion", "analysis", "op-ed", "editorial", "think tank", "new yorker", "podcast",
    "earbuds", "earphones", "smartwatch", "hands-on", "review:",
))
MISSING_CONTENT = _word_re((
    "لینک", "از طریق لینک", "دریافت فایل", "فایل جدول", "فایل پیوست", "دانلود",
    "جدول زیر", "تصاویر زیر", "تصویر زیر", "ویدیو زیر", "ویدئو زیر", "فیلم زیر",
    "در ادامه ببینید", "اینجا کلیک", "کلیک کنید", "اینفوگرافیک زیر",
    "link below", "click here", "download",
))


# Speeches made of slogans ("the enemy is confused", "will never rest") carry
# no new fact; they are blocked unless they announce a concrete event.
SPEAKER_PREFIX = re.compile(r"^[^:؛«»]{2,45}:\s")
SPEECH_VERB = re.compile(r"(?:گفت|اظهار کرد|اظهار داشت|تاکید کرد|تأکید کرد|ادعا|خطبه|سخنرانی|خطاب به)")
RHETORIC = re.compile(
    r"(?:سردرگم|ناکام|توهم|ذلت|پشیمان|زانو|شکست خورده|محکوم به شکست|از پای نخواهد نشست|"
    r"جرأت|جرات|تحقیر|شکست خواهد|استکبار|خون ?خواهی|نابود خواهد|به خاک سیاه|توطئه|"
    r"جنگ ترکیبی|سنگر|دشمن|ایدئولوژیک|محاسبات .{0,20}(?:غلط|اشتباه)|فراتر از محاسبات|"
    r"همخوانی نداشت|موفق نخواهند|نخواهد توانست)"
)
# A concrete event inside a speech keeps it as news ("IRGC: enemy drone shot down").
CONCRETE_EVENT = re.compile(
    r"(?:سرنگون|شلیک|کشته|زخمی|حمله|توقیف|بازداشت|دستگیر|اعزام|رهگیری|منهدم|هدف قرار|"
    r"امضا|تصویب|استعفا|برکنار|منصوب|اعدام|آزاد شد|آزادی|تحریم کرد|لغو|تعلیق|بسته شد|"
    r"\d{2,}|[۰-۹]{2,})"
)
# Friday-prayer sermons and religious speeches: never news for this channel.
SERMON = re.compile(r"(?:امام جمعه|ائمه جمعه|امامان جمعه|خطیب جمعه|خطیب نماز|نماز جمعه|خطبه|خطبه های)")
# Drills and exercises ("flood drill held") are rehearsals, not events. Big
# national military exercises (رزمایش) stay news unless they are local.
DRILL = re.compile(r"(?:مانور|تمرین امداد|شبیه ?سازی (?:زلزله|سیل|حادثه))")
LOCAL_EXERCISE = re.compile(r"رزمایش.{0,40}(?:شهرستان|بخش|استان|شهرداری|مدارس|دانش ?آموز|هلال احمر|آتش ?نشانی|بسیج)")
# Local police "follow-ups" (clues found, special order to arrest) with no
# casualties: provincial routine, even when the word "attack" appears.
LOCAL_FOLLOWUP = re.compile(r"(?:دستورکار|دستور کار|سرنخ|در حال پیگیری|پیگیری ویژه|پیگیری پرونده|در دست بررسی)")
HARD_TOLL = re.compile(r"(?:کشته|جان باخت|جان سپرد|انفجار|تیراندازی|گروگان)")
# Funerals, memorials and anniversaries: news only for top national figures.
CEREMONY = re.compile(r"(?:تشییع|مراسم|بزرگداشت|سالگرد|یادبود|گرامیداشت|چهلم|ختم|سوگواری)")
TOP_FIGURE = re.compile(r"(?:رهبر|رئیس ?جمهور|نخست ?وزیر|دبیرکل|فرمانده کل|پاپ|پادشاه|ملکه|شاه )")
# Individual MPs' general remarks ("province needs attention").
MP_REMARK = re.compile(r"(?:^|\s)(?:نماینده مجلس|نماینده مردم|نمایندگان مردم|عضو کمیسیون|نماینده)(?:\s|:)")
# Analysis / prescription / opinion framings in the headline.
ANALYSIS_TITLE = re.compile(
    r"(?:^|\s)(?:راهکار|راهکارهای|راه حل|ضرورت|چرا|چگونه|پیامدهای|قضیه|قضیۀ|بررسی|"
    r"نگاهی به|درس های|شانس .{0,30}کم|بدون برنامه)(?:\s|$)"
)


def noise_reason(title, lead=""):
    """Why a story is editorial noise (sermon, slogan speech, analysis), or ""."""
    title = _norm(title).lower()
    lead = _norm(lead).lower()
    text = f"{title} {lead}"
    if title and (DRILL.search(title) or LOCAL_EXERCISE.search(title)):
        return "drill-or-exercise"
    if title and LOCAL_FOLLOWUP.search(title) and IRAN_LOCAL.search(title) and not HARD_TOLL.search(title):
        return "local-police-followup"
    if not title or MASS_EVENT.search(title):
        return ""
    if SERMON.search(text):
        return "sermon"
    speech = (bool(SPEAKER_PREFIX.search(title)) or bool(SPEECH_VERB.search(text))
              or "اعلام کرد" in lead or "بیان کرد" in lead)
    if speech and RHETORIC.search(text) and not CONCRETE_EVENT.search(title):
        return "rhetoric-statement"
    if ANALYSIS_TITLE.search(title):
        return "analysis-or-opinion"
    if CEREMONY.search(title) and not TOP_FIGURE.search(title):
        return "ceremony"
    if MP_REMARK.search(title) and not CONCRETE_EVENT.search(title):
        return "mp-remark"
    return ""


def rhetoric_statement(candidate):
    return bool(noise_reason(candidate.get("title", ""),
                             candidate.get("summary", "") or candidate.get("description", "")))


def service_schedule(candidate):
    return bool(SERVICE_SCHEDULE.search(_text(candidate, 300)))


def low_value(candidate):
    title = _title(candidate)
    if not title or MASS_EVENT.search(title):
        return False
    return bool(LOW_VALUE.search(title))


def iran_local_routine(candidate):
    title = _title(candidate)
    if service_schedule(candidate):
        return True
    if not title or not IRAN_LOCAL.search(title):
        return False
    return not IRAN_LOCAL_EXCEPTION.search(title)

# --------------------------------------------------------------------------
# Major sports
# --------------------------------------------------------------------------

SPORT = _word_re((
    "فوتبال", "والیبال", "کشتی آزاد", "کشتی فرنگی", "کشتی گیر", "کشتی گیران",
    "بسکتبال", "فوتسال", "تنیس", "وزنه برداری", "تکواندو", "المپیک", "پارالمپیک",
    "جام جهانی", "لیگ قهرمانان", "لیگ قهرمانان اروپا", "لیگ قهرمانان آسیا",
    "جام ملت های اروپا", "کوپا آمریکا", "جام ملت های آسیا", "بازی های آسیایی",
    "قهرمانی جهان", "رکورد جهان", "توپ طلا", "پرسپولیس", "استقلال تهران", "سپاهان",
    "دربی", "تیم ملی", "ملی پوش", "سرمربی",
    "football", "soccer", "volleyball", "wrestling", "basketball", "olympic", "olympics",
    "world cup", "champions league", "euro 2028", "copa america", "asian cup",
    "asian games", "world championship", "world record", "ballon d'or",
))
BIG_STAGE = _word_re((
    "جام جهانی", "المپیک", "پارالمپیک", "لیگ قهرمانان", "جام ملت های اروپا", "کوپا آمریکا",
    "جام ملت های آسیا", "بازی های آسیایی", "قهرمانی جهان",
    "world cup", "olympic", "olympics", "champions league", "copa america", "asian cup",
    "asian games", "world championship",
))
DECISIVE = _word_re((
    "فینال", "قهرمان", "قهرمانی", "صعود", "صعود کرد", "حذف", "حذف شد", "نیمه نهایی",
    "یک چهارم نهایی", "مدال", "مدال طلا", "طلای", "نقره", "برنز", "قرعه کشی", "رکورد",
    "final", "champion", "champions", "title", "qualify", "qualified", "qualifies",
    "knocked out", "eliminated", "semi-final", "semifinal", "quarter-final", "medal",
    "gold", "record", "draw",
))
RESULT = _word_re((
    "پیروز", "پیروزی", "برد", "شکست", "باخت", "مساوی", "تساوی", "نتیجه", "صعود",
    "حذف", "قهرمان", "قهرمانی", "مدال", "سرمربی", "گلزنی",
    "beat", "beats", "won", "wins", "lost", "loses", "drew", "result", "coach", "appointed",
))
SINGULAR = re.compile(r"(?:توپ طلا|رکورد جهان|ballon d'or|world record)", re.I)
DERBY = re.compile(r"(?:دربی|پرسپولیس.*استقلال|استقلال.*پرسپولیس)", re.I)
SPORT_NOISE = re.compile(
    r"(?:شایعه|احتمال|احتمالا|مذاکره با|در آستانه|نقل و انتقالات|مصاحبه|واکنش|گفت|"
    r"ادعا|انتقاد|عکس|ویدیو|فیلم|حاشیه|rumou?r|could|might|linked with|talks with|"
    r"interview|reacts|says|said|photo|video)",
    re.I,
)
IRAN_TEAM = re.compile(r"(?:تیم ملی|ملی پوش|ایران|iran)", re.I)


def major_sports(candidate):
    """Return 0 (not major), 2 (major) or 3 (decisive Iran national result)."""
    title = _title(candidate)
    if not title or not SPORT.search(title) or SPORT_NOISE.search(title):
        return 0
    if SINGULAR.search(title):
        return 2
    iran = bool(IRAN_TEAM.search(title))
    if iran and RESULT.search(title):
        return 3 if (BIG_STAGE.search(title) or DECISIVE.search(title)) else 2
    if BIG_STAGE.search(title) and DECISIVE.search(title):
        return 2
    if DERBY.search(title) and RESULT.search(title):
        return 2
    return 0

# --------------------------------------------------------------------------
# Post text quality
# --------------------------------------------------------------------------

KNOWN_ACRONYMS = {
    "NATO", "OPEC", "IAEA", "UN", "EU", "US", "USA", "UK", "AI", "FBI", "CIA",
    "BBC", "CNN", "IMF", "WHO", "FIFA", "UEFA", "NASA", "BRICS", "G7", "G20",
    "CEO", "GDP", "NBA", "UFC", "SpaceX", "NABZ", "ICC", "ICJ", "WTO", "OIC",
    "ASEAN", "SCO", "CPI", "UAE", "IRGC", "AFP", "AP", "AFC", "VAR", "MMA",
}

PROBLEM_STATUS = "quality_blocked"
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
    if MISSING_CONTENT.search(title + " " + body):
        return "refers-to-missing-content"
    if SERVICE_SCHEDULE.search(title):
        return "service-schedule"
    noise = noise_reason(title, sentences[0])
    if noise:
        return noise
    if not _VERBISH_END.search(sentences[-1].strip()):
        return "body-truncated"
    return ""

# --------------------------------------------------------------------------
# Install
# --------------------------------------------------------------------------

SPORTS_GOOGLE_QUERIES = (
    ("ورزش", "تیم ملی فوتبال ایران"),
    ("ورزش", "تیم ملی والیبال ایران"),
    ("ورزش", "کشتی ایران قهرمانی جهان"),
    ("ورزش", "site:varzesh3.com"),
    ("ورزش", "جام جهانی فوتبال"),
    ("ورزش", "لیگ قهرمانان اروپا"),
)


def _register_statuses():
    main_mod = sys.modules.get("__main__")
    statuses = getattr(main_mod, "EDITORIAL_BLOCK_STATUSES", None)
    if isinstance(statuses, set):
        statuses.add(PROBLEM_STATUS)


def _add_sports_feeds(core):
    feeds = getattr(core, "GOOGLE_NEWS_FEEDS", None)
    builder = getattr(core, "google_news_search_url", None)
    if not isinstance(feeds, list) or not callable(builder):
        return 0
    existing = {(str(a), str(b)) for a, b in feeds}
    added = 0
    for category, query in SPORTS_GOOGLE_QUERIES:
        try:
            feed = (category, builder(query))
        except Exception:
            continue
        if feed[1] and feed not in existing:
            feeds.append(feed)
            existing.add(feed)
            added += 1
    return added


def install(core, current):
    import v13_intelligence
    import v13_policy_guard

    min_score = int(getattr(v13_intelligence, "MIN_EVENT_SCORE", 7))
    previous = v13_intelligence.is_publishable

    def relevance_gate(main_obj, candidate):
        ok, score, reason = previous(main_obj, candidate)
        sports = major_sports(candidate)
        if sports:
            if reason == "recent-editorial-block":
                return ok, score, reason
            candidate["_major_sports"] = sports
            return True, max(int(score or 0), min_score + 3), "major-sports"
        if not ok:
            return ok, score, reason
        if foreign_soft_local(candidate):
            return False, 0, "foreign-soft-local"
        if service_schedule(candidate):
            return False, 0, "service-schedule"
        if iran_local_routine(candidate):
            return False, 0, "iran-local-routine"
        if low_value(candidate):
            return False, 0, "low-value-opinion-or-product"
        noise = noise_reason(candidate.get("title", ""),
                             candidate.get("summary", "") or candidate.get("description", ""))
        if noise:
            return False, 0, noise
        return ok, score, reason

    v13_intelligence.is_publishable = relevance_gate

    previous_tier = v13_intelligence._publication_tier

    def sports_tier(candidate):
        tier = previous_tier(candidate)
        sports = candidate.get("_major_sports") or major_sports(candidate)
        return max(tier, sports) if sports else tier

    v13_intelligence._publication_tier = sports_tier

    previous_scope = v13_policy_guard._foreign_local_only

    def sports_scope(candidate):
        if major_sports(candidate):
            return False
        return previous_scope(candidate)

    v13_policy_guard._foreign_local_only = sports_scope

    strict = getattr(core, "is_strictly_useful_news", None)
    if callable(strict):
        def sports_strict(candidate):
            return True if major_sports(candidate) else strict(candidate)
        core.is_strictly_useful_news = sports_strict

    _register_statuses()
    added = _add_sports_feeds(core)
    print(f"V13 RELEVANCE GATE ACTIVE: local news blocked, major sports allowed (+{added} sports feeds), "
          "broken post text blocked.", flush=True)
