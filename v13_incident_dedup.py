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
Fail-safe: any error lets the post through to the older guards.
"""

import re
import time

STORE_KEY = "_published_incidents"
INCIDENT_WINDOW = 8 * 3600
MAX_ITEMS = 120

# event kinds; first match wins, so specific kinds come first
KINDS = (
    ("cyber", r"سایبری|هکر|هک شد"),
    ("quake", r"زلزله|زمین ?لرزه|پس ?لرزه"),
    ("flood", r"سیل|سیلاب|طغیان"),
    ("fire", r"[آا]تش ?سوزی|حریق|[آا]تش گرفت"),
    ("crash", r"سقوط (?:هواپیما|بالگرد|هلیکوپتر|جنگنده|پهپاد)|سانحه هوایی|تصادف|واژگونی|خروج قطار"),
    ("attack", r"پهپاد|موشک|راکت|خمپاره|بمباران|حمله|حملات|انفجار|اصابت|تیراندازی|ترور|انتحاری|"
               r"هدف قرار|پدافند|رهگیری"),
)
KIND_RX = [(k, re.compile(rf"(?<![\u0600-\u06FF]){p}")) for k, p in KINDS]

# place -> region. Region-only phrases map to themselves.
REGIONS = {
    "iraq_north": "اربیل|اربیل عراق|سلیمانیه|دهوک|کویه|رزگاری|اقلیم کردستان|کردستان عراق|شمال عراق|"
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
    "ukraine": "کی یف|خارکیف|خارکف|اودسا|دنیپرو|زاپوریژیا|زاپروژیا|خرسون|دونتسک|لوهانسک|سومی|لویو|پولتاوا",
    "russia": "مسکو|کورسک|بلگورود|بریانسک|کریمه|سواستوپل|سن پترزبورگ|کازان|نووروسیسک",
    "azerbaijan": "باکو|قره باغ|نخجوان",
    "armenia": "ایروان",
    "turkey": "آنکارا|استانبول|ازمیر|دیاربکر|غازی عنتاب|هاتای|قندیل",
    "sudan": "خارطوم|دارفور|الفاشر|ام درمان",
    "india_pak": "کشمیر|جامو",
}


def _norm(text):
    try:
        import v13_story_dedup as dd
        text = dd._norm(text)
    except Exception:
        text = str(text or "").replace("\u200c", " ")
    return re.sub(r"\s+", " ", text).strip()


_P = "\u0600-\u06FF"
_SUF = r"(?:ی|های|ها)?"
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
    for region, names, rx in _REGION_RX:
        for m in rx.finditer(t):
            regions.add(region)
            word = m.group(0)
            for n in names:
                if word.startswith(n):
                    places.add(n)
                    break
    if not _IRAQ_KURD.search(t) and _IRAN_KURD.search(t):
        regions.add("iran_kurdistan")
    if not regions:
        return None
    return {"kind": kind, "regions": sorted(regions), "places": sorted(places)}


def same_incident(a, b):
    if not a or not b or a.get("kind") != b.get("kind"):
        return False
    return bool(set(a.get("regions") or []) & set(b.get("regions") or []))


def _head(caption):
    try:
        import v13_text_polish as tp
        return tp.head_text(caption)
    except Exception:
        lines = [l.strip() for l in str(caption or "").splitlines()
                 if l.strip() and not l.strip().startswith(("#", "━", "🔗", "💓", "▫")) and "t.me/" not in l]
        return " ".join(lines[:2])


def _recent(health):
    now = time.time()
    items = health.get(STORE_KEY)
    if not isinstance(items, list):
        return []
    return [x for x in items if isinstance(x, dict) and now - float(x.get("t", 0) or 0) <= INCIDENT_WINDOW]


def _seed(health):
    """First run: rebuild signatures from the headlines the other guards stored."""
    if isinstance(health.get(STORE_KEY), list):
        return _recent(health)
    items = []
    for key in ("_published_heads", "_published_stories"):
        for x in health.get(key) or []:
            if not isinstance(x, dict):
                continue
            sig = signature(x.get("title", ""))
            if sig:
                items.append({"t": float(x.get("t", 0) or 0), "title": str(x.get("title", ""))[:120], **sig})
    items.sort(key=lambda x: x["t"])
    return [x for x in items if time.time() - x["t"] <= INCIDENT_WINDOW]


def find(caption):
    sig = signature(_head(caption))
    if not sig:
        return None
    import v13_story_dedup as dd
    _, health = dd._health()
    for item in reversed(_seed(health)):
        if same_incident(sig, item):
            return item
    return None


def remember(caption):
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
        match = orig_find(caption)
        if match:
            return match
        try:
            item = find(caption)
            if item:
                print(f"V13 INCIDENT DEDUP: same {item.get('kind')} in {','.join(item.get('regions') or [])} "
                      f"within {INCIDENT_WINDOW // 3600}h -> earlier: {str(item.get('title', ''))[:90]}", flush=True)
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
    print(f"V13 INCIDENT DEDUP ACTIVE: same event + same place blocked for {INCIDENT_WINDOW // 3600}h.", flush=True)
