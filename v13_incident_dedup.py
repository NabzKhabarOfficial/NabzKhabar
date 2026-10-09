"""NABZ V13 — same-incident guard (Oct 2026).

The word-overlap guards miss a story that is retold with different wording:
«حملات پهپادی به مقر گروه‌های تروریستی ضد ایران در اربیل», «حمله پهپادی به
اربیل عراق» and «حمله پهپاد به مقر گروهک تجزیه‌طلب در شمال عراق» share
almost no words, yet they are one incident and went out three times.

This layer reduces the headline + lead to an incident signature:
  * what happened  (attack / earthquake / fire / crash / flood ...)
  * where          (city -> region, e.g. اربیل -> اقلیم کردستان / شمال عراق)
and refuses a post whose signature matches anything published in the last
INCIDENT_WINDOW hours (same kind of event in the same city or region).

Logical exceptions (owner's request, Oct 9) - these are new news, not repeats:
  * reactions and statements: «عراق حمله به اربیل را محکوم کرد», «عراقچی: ...»
  * follow-ups: investigation, arrests, claim of responsibility, retaliation
  * a real casualty update: the toll rises clearly above what was published
  * two different cities of one region (اربیل vs سلیمانیه) are two incidents;
    a region-only wording («شمال عراق») matches any city in that region.

Oct 9 (2): the city list missed «کراماتورسک», so the same bus strike went out
three times. Places are no longer only a fixed list: the headline + lead give
"anchor" words (names and concrete nouns such as کراماتورسک, اتوبوس, فرودگاه
ملک خالد) that are not everyday news words. Same event kind + two shared
anchors = same incident, whatever the wording; a shared known city counts too.
Strong matches (two shared anchors) are remembered for 18 hours, a match on
city/region alone for 8 hours (busy war zones such as غزه stay newsworthy). A casualty update passes only when the
headline itself says the toll rose («شمار کشته‌ها به ۴۰ رسید»).
Fail-safe: any error lets the post through to the older guards.
"""

import re
import time

STORE_KEY = "_published_incidents"
INCIDENT_WINDOW = 8 * 3600       # same city/region only
STRONG_WINDOW = 18 * 3600        # two shared anchor words
ANCHORS_NEEDED = 2
MAX_ITEMS = 120

# event kinds; first match wins, so specific kinds come first
KINDS = (
    ("cyber", r"سایبری|هکر|هک شد"),
    ("quake", r"زلزله|زمین ?لرزه|پس ?لرزه"),
    ("flood", r"سیل|سیلاب|طغیان"),
    ("fire", r"[آا]تش ?سوزی|حریق|[آا]تش گرفت"),
    ("crash", r"سقوط (?:هواپیما|بالگرد|هلیکوپتر|جنگنده|پهپاد)|سانحه هوایی|تصادف|واژگونی|خروج قطار"),
    ("attack", r"پهپاد|موشک|راکت|خمپاره|بمباران|حمله|حملات|هجوم|انفجار|اصابت|تیراندازی|ترور|انتحاری|"
               r"هدف قرار|پدافند|رهگیری"),
)
KIND_RX = [(k, re.compile(rf"(?<![\u0600-\u06FF]){p}")) for k, p in KINDS]

# place -> region. Region-only phrases map to themselves.
REGIONS = {
    "iraq_north": "اربیل|سلیمانیه|دهوک|کویه|رزگاری|اقلیم کردستان|کردستان عراق|شمال عراق|"
                  "کرکوک|موصل|سنجار|نینوا",
    "iraq_center": "بغداد|عین الاسد|الانبار|فلوجه|رمادی|سامرا|کربلا|نجف|دیاله|صلاح الدین",
    "iraq_south": "بصره|ناصریه|عماره|میسان|ذی قار",
    "syria_north": "حلب|ادلب|حسکه|قامشلی|رقه|منبج|کوبانی|عین العرب",
    "syria_east": "دیرالزور|دیر الزور|البوکمال|المیادین|التنف",
    "syria_west": "دمشق|ریف دمشق|حمص|حما|لاذقیه|طرطوس|درعا|سویدا|قنیطره|جولان",
    "lebanon_south": "جنوب لبنان|صور|صیدا|نبطیه|بنت جبیل|مرجعیون|خیام",
    "lebanon_beirut": "بیروت|ضاحیه|ضاحیه جنوبی",
    "lebanon_bekaa": "بقاع|بعلبک|هرمل",
    "gaza": "غزه|نوار غزه|رفح|خان یونس|دیر البلح|جبالیا|نصیرات",
    "westbank": "کرانه باختری|جنین|نابلس|رام الله|طولکرم|الخلیل|طوباس",
    "israel_center": "تل آویو|تل اویو|یافا|اشدود|عسقلان|بئرالسبع|بئر السبع|ایلات|حیفا|عکا|نهاریا|کریات شمونه|"
                     "صفد|قدس|بیت المقدس|دیمونا|نقب",
    "yemen": "صنعا|حدیده|عدن|مارب|تعز|صعده|مخا",
    "red_sea": "دریای سرخ|باب المندب|خلیج عدن",
    "hormuz": "تنگه هرمز|دریای عمان|خلیج فارس",
    "gulf": "دوحه|دبی|ابوظبی|ابو ظبی|فجیره|ریاض|جده|منامه|بحرین|کویت|مسقط",
    "iran_tehran": "تهران|کرج|شهریار|اسلامشهر|ری|پرند|پردیس|دماوند",
    "iran_isfahan": "اصفهان|نطنز|کاشان|نجف آباد",
    "iran_qom": "قم|فردو",
    "iran_kurdistan": "سنندج|مریوان|سقز|بانه|کردستان ایران",
    "iran_westaz": "ارومیه|مهاباد|پیرانشهر|سردشت|بوکان|نقده|اشنویه|آذربایجان غربی",
    "iran_kermanshah": "کرمانشاه|اسلام آباد غرب|سرپل ذهاب|قصر شیرین|ایلام|مهران",
    "iran_sistan": "زاهدان|سراوان|خاش|چابهار|ایرانشهر|راسک|سیستان و بلوچستان|زابل",
    "iran_khuzestan": "اهواز|آبادان|خرمشهر|دزفول|ماهشهر|بندر امام|خوزستان|شوش|ایذه",
    "iran_south": "بندرعباس|بندر عباس|بوشهر|عسلویه|کیش|قشم|جاسک|هرمزگان|کنگان",
    "iran_east": "مشهد|نیشابور|سبزوار|کرمان|بم|یزد|بیرجند",
    "iran_north": "رشت|ساری|گرگان|انزلی|آمل|بابل سر|قزوین|زنجان|اردبیل|تبریز|مراغه|همدان|اراک|شیراز|"
                  "خرم آباد|لرستان|یاسوج|شهرکرد|سمنان",
    "pakistan_baluch": "کویته|بلوچستان پاکستان|گوادر|پنجگور",
    "pakistan": "اسلام آباد پاکستان|کراچی|لاهور|پیشاور|خیبر پختونخوا|وزیرستان",
    "afghanistan": "کابل|هرات|قندهار|مزارشریف|مزار شریف|جلال آباد|ننگرهار|بدخشان|پنجشیر",
    "ukraine": "کی یف|خارکیف|خارکف|اودسا|دنیپرو|زاپوریژیا|زاپروژیا|خرسون|دونتسک|لوهانسک|سومی|لویو|پولتاوا|"
               "کراماتورسک|اسلوویانسک|پوکروفسک|باخموت|کنستانتینوفکا|کوستیانتینیفکا|ایزیوم|میکولایف|چرنیهیف|"
               "کریوی ریه|ودسا|دونباس",
    "russia": "مسکو|کورسک|بلگورود|بریانسک|کریمه|سواستوپل|سن پترزبورگ|کازان|نووروسیسک",
    "azerbaijan": "باکو|قره باغ|نخجوان",
    "armenia": "ایروان",
    "turkey": "آنکارا|استانبول|ازمیر|دیاربکر|غازی عنتاب|هاتای|قندیل",
    "sudan": "خارطوم|دارفور|الفاشر|ام درمان",
    "india_pak": "کشمیر|جامو",
}


# Names that describe a whole region, not one city.
REGION_LEVEL = set("""
شمال عراق|اقلیم کردستان|کردستان عراق|نینوا|الانبار|دیاله|صلاح الدین|میسان|ذی قار|ریف دمشق|جولان|
جنوب لبنان|بقاع|نوار غزه|کرانه باختری|نقب|دریای سرخ|باب المندب|خلیج عدن|تنگه هرمز|دریای عمان|
خلیج فارس|کردستان ایران|آذربایجان غربی|سیستان و بلوچستان|خوزستان|هرمزگان|لرستان|بلوچستان پاکستان|
خیبر پختونخوا|وزیرستان|ننگرهار|بدخشان|پنجشیر|کریمه|قره باغ|دارفور|کشمیر
""".replace("\n", "").split("|"))

# Headlines that report a reaction or a new development of the incident.
REACTION = re.compile(
    r"محکوم|واکنش|بیانیه|تسلیت|ابراز نگرانی|ابراز تاسف|خواستار|هشدار داد|تهدید کرد|تماس تلفنی|"
    r"گفت ?و ?گو|گفتگو|احضار|سخنگو|اظهار|تاکید|تأکید|گفت(?![\u0600-\u06FF])|می گوید|"
    r"مسئولیت|مسوولیت|بر عهده گرفت|تحقیقات|بررسی علت|علت حادثه|بازداشت|دستگیر|شناسایی عاملان|"
    r"تلافی|انتقام|شورای امنیت|سازمان ملل")
_SPEAKER = re.compile(r"^[^:،.]{2,40}:\s")
_TOLL = re.compile(r"(\d+)\s*(?:نفر\s*)?(?:کشته|زخمی|مجروح|مصدوم|قربانی|جان باخت|شهید|کشته و زخمی)"
                   r"|(?:کشته|زخمی|مجروح|مصدوم|جان باختن|شهادت)\s+(?:شدن\s+)?(\d+)"
                   r"|(?:کشته|قربانی|جان باخت|زخمی|مجروح|مصدوم|تلفات)[^.]{0,50}?به\s+(\d+)\s*(?:نفر|تن)?\s*(?:رسید|افزایش)")
_DIG = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


# Words that say what kind of news it is, not which incident: never anchors.
GENERIC_WORDS = """
حمله حملات هجوم پهپاد پهپادی پهپادها موشک موشکی موشکها راکت خمپاره بمب بمباران بمبهای هدایت شونده
انفجار انفجارها اصابت تیراندازی ترور تروریستی انتحاری هوایی زمینی دریایی پدافند پدافندی سامانه سامانه ها رهگیری
کشته کشتهها کشته شدن زخمی زخمیها مجروح مجروحان مصدوم مصدومان قربانی قربانیان جان باخته جان باختگان تلفات شهید
شهادت نفر تن دستکم دست حداقل بیش کمتر چندین ده ها صدها هزاران شمار آمار تعداد رسید افزایش یافت جای گذاشت
شهر شهرهای استان منطقه مناطق مرز مرزی نزدیک شرق غرب شمال جنوب مرکز مرکزی شرقی غربی شمالی جنوبی خط مقدم حومه
نیروها نیروهای نظامیان نظامی ارتش مقامات مقام محلی مسئولان مسئول منابع رسانه ها رسانه گزارش گزارشها خبر
غیرنظامی غیرنظامیان مردم ساکنان شهروندان کودکان زنان امروز دیروز بامداد شب صبح عصر ساعات ساعت روز
هدف قرار گرفت گرفتند داد دادند کرد کردند شد شدند است بود دیگر جدید بخشی ادامه مداوم مستمر افزایش
اعلام کرد گفت خبر داد رئیس جمهور وزیر سخنگو ولودیمیر دونالد ارتش هدف
""".split()


def toll(text):
    t = _norm(text).translate(_DIG)
    nums = [int(n) for groups in _TOLL.findall(t) for n in groups if n.isdigit()]
    return max(nums) if nums else 0


def is_reaction(title):
    t = _norm(title)
    return bool(_SPEAKER.search(t) or REACTION.search(t))


def _norm(text):
    try:
        import v13_story_dedup as dd
        text = dd._norm(text)
    except Exception:
        text = str(text or "").replace("\u200c", " ")
    return re.sub(r"\s+", " ", text).strip()


def _keys(text):
    import v13_story_dedup as dd
    return dd.fingerprint(text)


def _generic_keys():
    try:
        import v13_story_dedup as dd
        keys = set(dd.COMMON)
        for w in GENERIC_WORDS:
            keys |= dd.fingerprint(w)
        return keys
    except Exception:
        return set()


_GENERIC = _generic_keys()


def anchors(text):
    try:
        return {k for k in _keys(text) if k not in _GENERIC and len(k) >= 3}
    except Exception:
        return set()


_UPDATE = re.compile(r"(?:شمار|آمار|تعداد|تلفات)\s+(?:\S+\s+){0,4}?(?:کشته|قربانی|جان باخت|زخمی|مجروح|مصدوم|تلفات)"
                     r"|(?:افزایش|بالا رفتن)\s+(?:شمار|آمار|تعداد)?\s*(?:کشته|قربانیان|جان باختگان|تلفات)")


_P = "\u0600-\u06FF"
_SUF = r"(?:ی|های|ها)?"
_REGION_LEVEL_N = {_norm(x) for x in REGION_LEVEL if x.strip()}
_REGION_RX = []
for _region, _alts in REGIONS.items():
    _names = sorted({_norm(a) for a in _alts.split("|") if a.strip()}, key=len, reverse=True)
    _REGION_RX.append((_region, _names, re.compile(
        rf"(?<![{_P}])(?:{'|'.join(re.escape(n) for n in _names)}){_SUF}(?![{_P}])")))
# Iraqi Kurdistan must not count as the Iranian province.
_IRAQ_KURD = re.compile(r"(?:اقلیم کردستان|کردستان عراق)")
_IRAN_KURD = re.compile(rf"(?<![{_P}])کردستان(?![{_P}])")
_NOT_EVENT = re.compile(r"سالگرد|یادبود|مراسم|تشییع|رزمایش|مانور|سالروز|بزرگداشت")


def signature(text):
    t = _norm(text)
    if not t or _NOT_EVENT.search(t):
        return None
    kind = next((k for k, rx in KIND_RX if rx.search(t)), None)
    if not kind:
        return None
    regions, places = set(), set()
    cities = set()
    for region, names, rx in _REGION_RX:
        for m in rx.finditer(t):
            regions.add(region)
            word = m.group(0)
            for n in names:
                if word.startswith(n):
                    places.add(n)
                    if n not in _REGION_LEVEL_N:
                        cities.add(n)
                    break
    if not _IRAQ_KURD.search(t) and _IRAN_KURD.search(t):
        regions.add("iran_kurdistan")
    anc = anchors(t)
    if not regions and len(anc) < ANCHORS_NEEDED:
        return None
    return {"kind": kind, "regions": sorted(regions), "places": sorted(places),
            "cities": sorted(cities), "toll": toll(t), "a": sorted(anc)}


def match_strength(a, b):
    """0 = different incidents, 1 = same city/region only, 2 = shared anchor words."""
    if not a or not b or a.get("kind") != b.get("kind"):
        return 0
    ca, cb = set(a.get("cities") or []), set(b.get("cities") or [])
    if ca and cb and not (ca & cb):
        return 0  # two different known cities: two incidents
    shared_anchors = set(a.get("a") or []) & set(b.get("a") or [])
    if len(shared_anchors) >= ANCHORS_NEEDED:
        return 2  # e.g. کراماتورسک + اتوبوس
    if ca & cb or set(a.get("regions") or []) & set(b.get("regions") or []):
        return 1  # same city/region only: busy war zones get the short window
    return 0


def same_incident(a, b):
    return match_strength(a, b) > 0


def is_update(new, old, title=""):
    """A real casualty update: the headline says the toll rose, and it clearly did."""
    if not _UPDATE.search(_norm(title)):
        return False
    n, o = int(new.get("toll") or 0), int(old.get("toll") or 0)
    return n >= 3 and n >= o + 3 and n >= o * 1.3


def _title(caption):
    for line in str(caption or "").splitlines():
        s = line.strip()
        if not s or s.startswith(("#", "━", "🔗", "💓", "▫", "⚡")) or "t.me/" in s:
            continue
        return s
    return ""


def _head(caption):
    try:
        import v13_text_polish as tp
        return tp.head_text(caption)
    except Exception:
        lines = [l.strip() for l in str(caption or "").splitlines()
                 if l.strip() and not l.strip().startswith(("#", "━", "🔗", "💓", "▫")) and "t.me/" not in l]
        return " ".join(lines[:2])


SEED_FLAG = "_published_incidents_v2"


def _recent(health):
    now = time.time()
    items = health.get(STORE_KEY)
    if not isinstance(items, list):
        return []
    return [x for x in items if isinstance(x, dict) and now - float(x.get("t", 0) or 0) <= STRONG_WINDOW]


def _seed(health):
    """First run (and v2 upgrade): rebuild signatures from the headlines the other guards stored."""
    if isinstance(health.get(STORE_KEY), list) and health.get(SEED_FLAG):
        return _recent(health)
    health[SEED_FLAG] = True
    items = []
    for key in ("_published_heads", "_published_stories"):
        for x in health.get(key) or []:
            if not isinstance(x, dict):
                continue
            sig = signature(x.get("title", ""))
            if sig:
                items.append({"t": float(x.get("t", 0) or 0), "title": str(x.get("title", ""))[:120], **sig})
    for x in health.get(STORE_KEY) or []:
        if isinstance(x, dict) and x.get("title"):
            sig = signature(x.get("title", ""))
            if sig:
                items.append({"t": float(x.get("t", 0) or 0), "title": str(x.get("title", ""))[:120], **sig})
    items.sort(key=lambda x: x["t"])
    return [x for x in items if time.time() - x["t"] <= STRONG_WINDOW]


def toll_update(caption):
    """True when the headline reports a clearly higher toll for an incident already published."""
    title = _title(caption)
    if not _UPDATE.search(_norm(title)):
        return False
    sig = signature(_head(caption))
    if not sig:
        return False
    import v13_story_dedup as dd
    _, health = dd._health()
    now = time.time()
    seen = [x for x in _seed(health) if match_strength(sig, x) and now - float(x.get("t", 0) or 0) <= STRONG_WINDOW]
    return bool(seen) and all(is_update(sig, x, title) for x in seen)


def find(caption):
    if is_reaction(_title(caption)):
        return None
    sig = signature(_head(caption))
    if not sig:
        return None
    import v13_story_dedup as dd
    _, health = dd._health()
    title = _title(caption)
    now = time.time()
    for item in reversed(_seed(health)):
        strength = match_strength(sig, item)
        if not strength:
            continue
        age = now - float(item.get("t", 0) or 0)
        if age > (STRONG_WINDOW if strength == 2 else INCIDENT_WINDOW):
            continue
        if is_update(sig, item, title):
            print(f"V13 INCIDENT DEDUP: toll update {item.get('toll', 0)} -> {sig['toll']}, allowed.", flush=True)
            return None
        return item
    return None


def remember(caption):
    if is_reaction(_title(caption)):
        return  # reactions never block the incident itself
    sig = signature(_head(caption))
    if not sig:
        return
    import v13_story_dedup as dd
    router, health = dd._health()
    items = _seed(health)
    items.append({"t": time.time(), "title": _head(caption)[:120], **sig})
    health[STORE_KEY] = items[-MAX_ITEMS:]
    router._save_health(health)


_INSTALLED = {"done": False}


def install():
    if _INSTALLED["done"]:
        return
    import v13_story_dedup as dd
    orig_find = dd.find_duplicate
    orig_remember = dd.remember

    def find_duplicate(caption):
        try:
            if toll_update(caption):
                print("V13 INCIDENT DEDUP: casualty update of a published incident, allowed.", flush=True)
                return None
        except Exception as exc:
            print(f"V13 INCIDENT DEDUP: update check skipped ({type(exc).__name__}).", flush=True)
        match = orig_find(caption)
        if match:
            return match
        try:
            item = find(caption)
            if item:
                print(f"V13 INCIDENT DEDUP: same {item.get('kind')} ({','.join((item.get('regions') or []) + (item.get('a') or [])[:4])}) "
                      f"-> earlier: {str(item.get('title', ''))[:90]}", flush=True)
                return item
        except Exception as exc:
            print(f"V13 INCIDENT DEDUP: check skipped ({type(exc).__name__}).", flush=True)
        return None

    def remember_all(caption):
        orig_remember(caption)
        try:
            remember(caption)
        except Exception as exc:
            print(f"V13 INCIDENT DEDUP: remember skipped ({type(exc).__name__}).", flush=True)

    dd.find_duplicate = find_duplicate
    dd.remember = remember_all
    _INSTALLED["done"] = True
    print(f"V13 INCIDENT DEDUP ACTIVE: same event + same place/anchors blocked "
          f"({STRONG_WINDOW // 3600}h strong, {INCIDENT_WINDOW // 3600}h region).", flush=True)
