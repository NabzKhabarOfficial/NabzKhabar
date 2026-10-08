"""NABZ V13 — text polish layer (Oct 2026).

Fixes the quality problems seen in published posts, without touching the
news engine. Everything is fail-safe: any error falls back to the old path.

1) Topic labels: whole-word matching (no more «طلا» inside a sports medal
   becoming «اقتصاد», «ناو» inside «شناور», «متا» inside «متاسفانه»), sports
   and science detected from the headline, the lead breaks ties before the
   weak "war" fallback, and economy/police stories stop being «نظامی».
2) Details: filler lines («جزئیات بیشتری در دسترس نیست», «این گزارش توسط
   ایرنا منتشر شد», «این ... نشان دهنده ... است») and lines that only repeat
   the title/lead are dropped.
3) AI output: common mistranslations are corrected (هوتی→حوثی, قواهای→نیروهای,
   موشک کروی→کروز, خلیج هرمز→تنگه هرمز ...); output with foreign-script
   letters, a lead that starts mid-context, a title/lead sea mismatch or a
   wrong job title (نخست وزیر زلنسکی) is rejected so the next model retries.
   The prompt gets explicit rules for all of the above.
4) Duplicates: the same incident retold within 12 hours (same title+lead
   names) is caught even when the story is so hot that its names are no
   longer "rare" for the 36h guard.
6) Header (owner's request, Oct 8): the «🇮🇷 ایران · ⚔️ نظامی» line is gone
   (the region was often wrong, e.g. a Syrian pipeline marked «ایران»). The
   post now opens with the channel's own signature, «💓 نبض خبر ▰▰▰▰▱», and
   the duplicate pulse line in the footer is dropped. The website pages drop
   the topic tag too.
7) Lead check (Oct 8): when a detail line matches the headline much better
   than the lead does, it becomes the lead (title and lead must tell the same
   story), and empty "this happened on Thursday" lines are dropped.
"""

import re
import time

P = "\u0600-\u06FF"
_SUF = r"(?:ی|ها|های|هایی|ای|ان|ات|ند|ه|ه اند|اند)?"


def _rx(words, suffix=True):
    words = [w.strip() for w in words if w and w.strip()]
    alt = "|".join(re.escape(w) for w in sorted(set(words), key=len, reverse=True))
    suf = _SUF if suffix else ""
    return re.compile(rf"(?<![{P}\w])(?:{alt}){suf}(?![{P}\w])")


def _norm(value):
    value = str(value or "").replace("\u200c", " ").replace("ي", "ی").replace("ك", "ک")
    value = value.replace("أ", "ا").replace("إ", "ا").replace("ۀ", "ه")
    value = re.sub("[\u064B-\u065F\u0670]", "", value)
    return re.sub(r"\s+", " ", value).strip()


# --------------------------------------------------------------------------
# 1) Topic labels
# --------------------------------------------------------------------------

IMAGERY = re.compile(r"تصاویر ماهواره ?ای|تصویر ماهواره ?ای|داده های ماهواره ?ای")

SPORT_WORDS = _rx((
    "فوتبال", "فوتسال", "والیبال", "بسکتبال", "هندبال", "واترپلو", "کشتی آزاد",
    "کشتی فرنگی", "کشتی گیر", "کشتی گیران", "جودو", "جودوکار", "تکواندو", "کاراته",
    "ووشو", "وزنه برداری", "وزنه بردار", "بوکس", "تنیس", "پینگ پنگ", "تنیس روی میز",
    "شطرنج", "رالی", "فرمول یک", "دوومیدانی", "شنا", "دوچرخه سواری", "قایقرانی",
    "المپیک", "پارالمپیک", "بازی های آسیایی", "جام جهانی", "لیگ برتر", "لیگ قهرمانان",
    "جام ملت ها", "ملی پوش", "ملی پوشان", "سرمربی", "دروازه بان", "پرسپولیس",
    "سپاهان", "استقلال تهران", "قهرمانی آسیا", "قهرمانی جهان", "مسابقات جهانی",
    "پرتاب دیسک", "پرتاب وزنه", "رکورد جهان", "توپ طلا", "فیفا", "یوفا",
))
MEDAL = re.compile(r"(?:مدال|طلای|نقره|برنز|نشان طلا)")
SPORT_CONTEXT = re.compile(r"(?:کاروان|تیم|ملی ?پوش|رقابت|مسابقات|بازی های|قهرمان|آسیایی|جهانی|ناشنوایان|المپیک)")
SCIENCE = _rx(("نوبل", "المپیاد", "اخترفیزیک", "نوترینو", "ناسا", "تلسکوپ", "دانشمندان"))

COMBAT = _rx((
    "موشک", "موشکی", "پهپاد", "پهپادی", "بمباران", "شلیک", "جنگنده", "سرنگون",
    "رهگیری", "حمله هوایی", "حمله موشکی", "حمله پهپادی", "حملات هوایی", "توپخانه",
    "کشته شد", "کشته شدند", "شهید", "شهادت", "ترور", "تروریست", "تروریستی",
    "انفجار بمب", "بمب", "عملیات نظامی", "درگیری مسلحانه", "ناو",
    "ناو هواپیمابر", "تفنگدار", "نیروی دریایی", "نیروی هوایی", "بمب افکن",
))
MILITARY_AMBIG = _rx((
    "حمله کرد", "حمله به", "حملات", "پس از حمله", "در پی حمله", "هدف قرار گرفت",
    "هدف قرار گرفتند", "هدف قرار دادند", "هدف شد", "هدف شدند", "اعزام نیرو",
    "اعزام شد", "رزمایش", "پایگاه", "یورش", "استقرار", "درگیری ها", "درگیری های",
    "محاصره دریایی", "شناور", "نفتکش", "نفت کش",
))
MILITARY_WEAK = _rx(("جنگ", "نظامی", "نظامیان", "ارتش", "سپاه", "آتش بس", "امنیتی"))
ARMS = re.compile(r"(?:فروش|خرید|تحویل|ارسال|بسته)\s+(?:\S+\s+){0,6}?(?:سلاح|تسلیحات|جنگنده|موشک|پهپاد)"
                  r"|(?:سلاح|تسلیحات)\s+(?:\S+\s+){0,4}?(?:فروش|خرید|تحویل)")
MILITARY_SITE = _rx(("فرودگاه نظامی", "پایگاه نظامی", "پایگاه هوایی", "پادگان", "انبار مهمات",
                     "تاسیسات نظامی", "مقر"))
ACCIDENT = _rx(("انفجار", "آتش سوزی", "سقوط", "زلزله", "سیل", "سیلاب", "تصادف", "مصدوم",
                "غرق", "ریزش", "طوفان", "حادثه", "حوادث", "سانحه", "آتش گرفت", "تیراندازی"))
WARNING = _rx(("هشدار", "خطر احتمالی", "احتمال وقوع", "احتمال سیل", "پیش بینی", "آماده باش",
               "در معرض خطر"))
HAPPENED = _rx(("کشته", "جان باخت", "جان باختند", "مصدوم", "زخمی", "خسارت", "رخ داد",
                "ناپدید", "مفقود", "تخریب", "آواره", "محبوس", "نجات", "فوتی"))
WEATHERISH = _rx(("سیل", "سیلاب", "طوفان", "باران", "بارش", "برف", "گرد و خاک", "زلزله"))
POLICE = _rx(("پلیس", "قاچاق", "قاچاقچی", "قاچاقچیان", "کشف", "دستگیری", "دستگیر", "سرقت",
              "قتل", "کلاهبرداری", "انتظامی"))
ATTACKISH = _rx(("حمله", "انفجار", "تروریست", "تروریستی", "شهید", "شهادت", "کشته", "بمب"))
ECON_CORE = _rx(("تورم", "بازار", "بورس", "قیمت", "قیمت ها", "اقتصاد", "اقتصادی", "تجارت",
                 "صادرات", "واردات", "بودجه", "اوراق قرضه", "نرخ بهره", "سرمایه گذاری", "ارز",
                 "شاخص قیمت", "رشد اقتصادی", "بانک مرکزی", "نقدینگی"))
TOPICS = (
    ("☢️", "هسته‌ای", _rx(("هسته ای", "غنی سازی", "اورانیوم", "سایت هسته ای", "سلاح هسته ای",
                          "آژانس بین المللی انرژی اتمی"))),
    ("⚖️", "قضایی", _rx(("دادگاه", "اعدام", "دیوان", "حکم", "محاکمه", "بازداشت", "زندان",
                       "قوه قضاییه", "قوه قضائیه", "دادستان", "متهم"))),
    ("💰", "اقتصاد", _rx(("دلار", "یورو", "طلا", "سکه", "بورس", "تورم", "نرخ بهره", "بانک مرکزی",
                        "قیمت", "قیمت نفت", "بنزین", "اقتصاد", "اقتصادی", "تعرفه", "بازار", "ارز",
                        "نفت", "نفتی", "صادرات", "واردات", "دیزل", "گازوئیل", "تجارت", "میلیارد",
                        "هزینه", "بیمه", "بانک", "بودجه", "سرمایه گذاری", "ادغام", "اوپک",
                        "پالایشگاه", "نقدینگی", "کشتیرانی"))),
    ("💻", "فناوری", _rx(("هوش مصنوعی", "تراشه", "اپل", "گوگل", "مایکروسافت", "متا", "انویدیا",
                        "سایبری", "اینترنت", "فناوری", "ماهواره", "ربات", "اسپیس ایکس",
                        "استارلینک"))),
    ("🩺", "سلامت", _rx(("بیماری", "واکسن", "ویروس", "بیمارستان", "سلامت", "دارو", "شیوع"))),
    ("🌦", "آب و هوا", _rx(("هواشناسی", "بارش", "باران", "برف", "گرما", "سرما", "خشکسالی"))),
    ("🏛", "سیاست", _rx(("وزیر", "سفارت", "سفیر", "دیپلماتیک", "مذاکره", "رئیس جمهور", "مجلس",
                       "انتخابات", "انتخاباتی", "تحریم", "سازمان ملل", "دولت", "پارلمان",
                       "نخست وزیر", "کنگره", "قطعنامه", "توافق", "نظرسنجی", "مذاکرات", "گفتگو",
                       "گفت و گو", "احضار", "آیین نامه", "رای گیری"))),
)
_SPEAKER_PREFIX = re.compile(r"^[^:؛«»]{2,45}:\s")
SPEECH = _rx((
    "گفت", "اظهار کرد", "اظهار داشت", "تاکید کرد", "تأکید کرد", "خواستار", "ادعا کرد",
    "معتقد است", "واکنش", "هشدار داد", "تهدید کرد", "خطاب به", "افزود", "بیان کرد",
    "ادعا", "می گوید", "گفته است", "اعلام کرد", "مدعی شد", "سخنرانی", "خطبه",
), suffix=False)
RHETORIC = re.compile(
    r"(?:سردرگم|ناکام|توهم|ذلت|پشیمان|زانو|شکست خورده|محکوم به شکست|از پای نخواهد نشست|"
    r"عقب نشینی خواهد|جرأت|جرات|تحقیر|شکست خواهد|مقاومت مردم|دشمن|استکبار|"
    r"(?<![" + P + r"])خواب(?![" + P + r"])|(?<![" + P + r"])رویا(?![" + P + r"]))")


def is_sport(title):
    text = _norm(title)
    if SCIENCE.search(text):
        return False
    if SPORT_WORDS.search(text):
        return True
    return bool(MEDAL.search(text) and SPORT_CONTEXT.search(text))


def _first_topic(text):
    for emoji, name, rx in TOPICS:
        if rx.search(text):
            return emoji, name
    return None


_CTX = {"lead": ""}


def topic_of(title, label, lead=None):
    text = IMAGERY.sub(" ", _norm(title))
    lead = IMAGERY.sub(" ", _norm(_CTX.get("lead", "") if lead is None else lead))
    if SCIENCE.search(text):
        return "🔬", "علم"
    if label == "ورزش" or is_sport(text):
        return "⚽", "ورزش"
    if "نظرسنجی" in text:
        return "🏛", "سیاست"
    statement = bool(_SPEAKER_PREFIX.search(text)) or bool(SPEECH.search(text))
    rhetoric = bool(RHETORIC.search(text))
    combat = bool(COMBAT.search(text))
    strong = combat or bool(MILITARY_AMBIG.search(text))
    if statement and (rhetoric or not combat):
        if not rhetoric:
            found = _first_topic(text)
            if found:
                return found
        return "🗣", "موضع‌گیری"
    accident = bool(ACCIDENT.search(text))
    if accident and WARNING.search(text) and not HAPPENED.search(text) and not strong:
        return ("🌦", "آب و هوا") if WEATHERISH.search(text) else ("⚠️", "هشدار")
    if accident and not strong and not MILITARY_SITE.search(text):
        return "🚨", "حادثه"
    if POLICE.search(text) and not ATTACKISH.search(text) and not COMBAT.search(text):
        return "🚔", "انتظامی"
    if strong and not combat and ECON_CORE.search(text):
        return "💰", "اقتصاد"
    if strong or (accident and MILITARY_SITE.search(text)) or ARMS.search(text):
        return "⚔️", "نظامی"
    found = _first_topic(text)
    if found:
        return found
    if accident:
        return "🚨", "حادثه"
    if lead:
        found = _first_topic(lead)
        if found and found[1] in ("اقتصاد", "قضایی", "سلامت", "فناوری", "آب و هوا", "هسته‌ای"):
            return found
    if MILITARY_WEAK.search(text) or (lead and COMBAT.search(lead)):
        return "⚔️", "نظامی"
    return "📰", "خبر"


# --------------------------------------------------------------------------
# 2) Detail lines + 3) wording fixes
# --------------------------------------------------------------------------

FILLER = re.compile(
    r"(?:(?:هیچ\s+)?(?:جزئیات|اطلاعات)\s+(?:بیشتر|بیشتری|دیگری|دیگر)\s+(?:\S+\s+){0,2}?"
    r"(?:در دسترس|منتشر|اعلام)\s*(?:نیست|نشده)"
    r"|^این\s+(?:گزارش|خبر|ادعا|ادعاها|مطلب|تصاویر|اطلاعات)\s+(?:توسط|از سوی|به نقل از)\s"
    r"|^(?:این|چنین)\s+\S+(?:\s+\S+)?\s+(?:نشان ?دهنده|نشانگر|بیانگر|حاکی از)\s"
    r"|^این\s+(?:پیام|بیانیه|اقدام|حرکت|رویداد)\s+به\s+یک\s"
    r"|به\s+مسائل\s+دیگری?\s+(?:نیز\s+)?اشاره\s+کرد)"
)
_DIGITS = re.compile(r"[0-9۰-۹]+")
# «این رویداد روز پنجشنبه رخ داد»، «این حادثه در جنوب لبنان رخ داد»: says nothing new.
EVENT_FILLER = re.compile(r"^(?:این|چنین)\s+(?:رویداد|وضعیت|حادثه|اتفاق|موضوع|ماجرا)\s+.*"
                          r"(?:رخ داد|رخ داده است|رخ می دهد|اتفاق افتاد|اتفاق افتاده است)\s*[.!]?$")


def is_filler(sentence):
    s = _norm(sentence)
    if FILLER.search(s):
        return True
    return bool(EVENT_FILLER.search(s)) and len(s.split()) <= 12 and not _DIGITS.search(s)


def lead_index(title, sentences):
    """Index of the sentence that should open the post: the lead, unless a detail line
    clearly tells the headline's story better (lead off-topic or only background)."""
    try:
        import v13_story_dedup as dd
        tkeys = dd.fingerprint(_norm(title))
        if len(sentences) < 2 or len(tkeys) < 3:
            return 0
        base = len(dd.fingerprint(_norm(sentences[0])) & tkeys)
        best, best_i = base, 0
        for i, sentence in enumerate(sentences[1:4], start=1):
            score = len(dd.fingerprint(_norm(sentence)) & tkeys)
            if score > best:
                best, best_i = score, i
        if best_i and best >= 3 and best >= base + 2:
            return best_i
    except Exception:
        pass
    return 0


def is_redundant(sentence, context):
    """True when a detail line only repeats words already in title/lead."""
    try:
        import v13_story_dedup as dd
    except Exception:
        return False
    s = _norm(sentence)
    ctx = _norm(context)
    if set(_DIGITS.findall(s)) - set(_DIGITS.findall(ctx)):
        return False  # carries a number the reader has not seen yet
    fd = dd.fingerprint(s)
    if len(fd) < 2:
        return False
    new = fd - dd.fingerprint(ctx)
    return len(new) <= 1


FIXES = (
    (re.compile(r"(?<![" + P + r"])(?:هوتی|هوثی)(ها|های)?(?![" + P + r"])"), r"حوثی\1"),
    (re.compile(r"(?<![" + P + r"])قواهای(?![" + P + r"])"), "نیروهای"),
    (re.compile(r"(موشک(?: ?های)?)\s+کروی(?![" + P + r"])"), r"\1 کروز"),
    (re.compile(r"خلیج(?:\s+سند)?\s+هرمز"), "تنگه هرمز"),
    (re.compile(r"(?<![" + P + r"])وزیر اعظم(?![" + P + r"])"), "نخست وزیر"),
    (re.compile(r"سرگ ئی"), "سرگئی"),
    (re.compile(r"بارباریکه"), "باریکه"),
    (re.compile(r"(?<![" + P + r"])نایجریه"), "نیجریه"),
    (re.compile(r"دفتر بیضی(?: شکل)? سفید"), "دفتر بیضی کاخ سفید"),
    (re.compile(r"(?<![" + P + r"])طایز(?![" + P + r"])"), "تعز"),
    (re.compile(r"(?<![" + P + r"])موچا(?![" + P + r"])"), "مخا"),
    (re.compile(r"رشاد ال ?الیمی"), "رشاد العلیمی"),
    (re.compile(r"(?<![" + P + r"])تدوام(?![" + P + r"])"), "تداوم"),
    (re.compile(r"اختصاصیافت"), "اختصاص یافت"),
    (re.compile(r"(?<![" + P + r"])(?:کی اف|کییف)(?![" + P + r"])"), "کی یف"),
)


def fix_text(text):
    value = str(text or "")
    for rx, rep in FIXES:
        value = rx.sub(rep, value)
    return value


FOREIGN_SCRIPT = re.compile(r"[\u0370-\u03FF\u0400-\u04FF\u0590-\u05FF\u0900-\u097F"
                            r"\u3040-\u30FF\u4E00-\u9FFF\uAC00-\uD7AF]")
DANGLING_LEAD = re.compile(
    r"^(?:(?:این|آن)(?!\s+(?:هفته|ماه|سال|روزها|بار|روز)\b)\s|او\s|وی\s|آنها\s|آن ها\s|در نتیجه|همچنین\s|"
    r"اما\s|ولی\s|بنابراین\s|در همین حال|به همین دلیل|در (?:این|آن|همین)\s|"
    r"(?:گزارش داد|اعلام کرد|افزود|گفت)(?:\s|$)|"
    r"\S+\s+(?:این|آن)\s(?!(?:هفته|ماه|سال|روز|روزها|بار)(?:\s|$)))")
SEAS = ("دریای سیاه", "دریای سرخ", "دریای عمان", "دریای خزر", "دریای مدیترانه", "دریای بالتیک",
        "دریای چین جنوبی", "دریای عرب", "دریای آزوف", "دریای شمال", "دریای اژه", "دریای ژاپن")
WRONG_ROLE = re.compile(r"(?:نخست ?وزیر|صدراعظم)\s+(?:اوکراین\s+)?(?:،\s*)?(?:ولودیمیر\s+)?زلنسکی"
                        r"|(?:نخست ?وزیر|صدراعظم)\s+(?:آمریکا\s+)?(?:،\s*)?(?:دونالد\s+)?ترامپ")


def _first_sentence(text):
    parts = re.split(r"(?<=[.!؟؛])\s+", str(text or "").strip())
    return parts[0].strip() if parts and parts[0].strip() else ""


def extra_reasons(title, summary):
    reasons = []
    t, s = _norm(title), _norm(summary)
    if FOREIGN_SCRIPT.search(t + " " + s):
        reasons.append("foreign_script_letters")
    if DANGLING_LEAD.search(_first_sentence(s)):
        reasons.append("lead_starts_mid_context")
    t_seas = {x for x in SEAS if x in t}
    s_seas = {x for x in SEAS if x in s}
    if t_seas and s_seas and not (t_seas & s_seas):
        reasons.append("title_summary_place_mismatch")
    if WRONG_ROLE.search(t + " " + s):
        reasons.append("wrong_job_title")
    return reasons


PROMPT_MARK = "قواعد کیفیت نبض خبر"
PROMPT_RULES = """

قواعد کیفیت نبض خبر (اجباری):
- جمله اول خلاصه باید به تنهایی کامل باشد: چه کسی، چه کاری، کجا. با «این»، «او»، «وی»، «در نتیجه»، «همچنین»، «اما» یا «گزارش داد» شروع نشود.
- تیتر و خلاصه باید دقیقاً یک چیز بگویند؛ نام مکان، دریا، کشور، عدد و طرف‌ها در هر دو یکسان باشد.
- معنی را برعکس نکن: «رد کرد/تأیید کرد»، «دارد/ندارد»، «می‌تواند/نمی‌تواند»، «صلح‌آمیز/نظامی» را دقیقاً مثل متن اصلی بیاور.
- سمت افراد را دقیق بنویس (مثلاً زلنسکی رئیس‌جمهور اوکراین است).
- شکل رایج فارسی: حوثی (نه هوتی)، نیروهای دولتی (نه قواهای)، موشک کروز، تنگه هرمز، پهپاد، تعز، نیجریه، کی‌یف.
- فقط حروف فارسی؛ هیچ حرف روسی، لاتین یا خط دیگری وسط کلمه‌ها نیاید.
- جمله پرکننده ممنوع: «جزئیات بیشتری در دسترس نیست»، «این گزارش توسط ... منتشر شد»، «این ... نشان‌دهنده ... است»، و تکرار تیتر. اگر اطلاعات دیگری نیست، خلاصه را کوتاه‌تر بنویس.
- نظر، تحلیل یا قضاوت خودت را اضافه نکن.
"""


def _with_rules(prompt):
    prompt = str(prompt or "")
    if PROMPT_MARK in prompt or '"title"' not in prompt:
        return prompt
    return prompt + PROMPT_RULES


# --------------------------------------------------------------------------
# 4) Same incident within 12 hours (title + lead)
# --------------------------------------------------------------------------

HEAD_KEY = "_published_heads"
HEAD_WINDOW = 12 * 3600
HEAD_MAX = 80


def head_text(caption):
    kept = []
    for line in str(caption or "").splitlines():
        s = line.strip()
        if not s or s.startswith(("#", "━", "🔗", "💓", "▫")) or "t.me/" in s:
            continue
        if len(s) < 40 and "·" in s:
            continue  # topic header
        if len(s) < 30 and re.match(r"^(🔴|🟠|🌍|🇮🇷|💰|💻|⚽|🗣|⚔|🚨|🏛|⚖|🩺|🌦|⚠|📰|🔬|🚔|☢)", s):
            continue
        kept.append(s)
        if len(kept) >= 2:
            break
    return " ".join(kept)


def head_keys(caption):
    import v13_story_dedup as dd
    return {k for k in dd.fingerprint(head_text(caption)) if k not in dd.COMMON}


def same_incident(a, b):
    if len(a) < 5 or len(b) < 5:
        return False
    shared = len(a & b)
    return shared >= 6 and shared / min(len(a), len(b)) >= 0.5


def _recent_heads(health):
    now = time.time()
    items = health.get(HEAD_KEY)
    if not isinstance(items, list):
        return []
    return [x for x in items if isinstance(x, dict) and now - float(x.get("t", 0) or 0) <= HEAD_WINDOW]


# --------------------------------------------------------------------------
# 5) Editor gate: real security / mass-casualty / energy-attack news was
#    rejected as "local, limited casualties" (terror attack in Golshan,
#    10 stabbed in a Polish school, pipeline attack in Hasakah).
# --------------------------------------------------------------------------

_NUM = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
IRAN_SECURITY = re.compile(
    r"(?:تروریست|تروریستی|اشرار|حمله مسلحانه|درگیری مسلحانه|تیراندازی|گروگان|بمب|انفجار|"
    r"هلاکت|عملیات انتحاری|ترور)")
CEREMONY_WORDS = re.compile(r"(?:تشییع|مراسم|سالگرد|یادبود|بزرگداشت|گرامیداشت|چهلم|رزمایش|مانور)")
TOLL = re.compile(r"(\d+)\s*(?:نفر\s*)?(?:کشته|زخمی|مجروح|مصدوم|قربانی|جان باخته|جان باختند)"
                  r"|(?:کشته|زخمی|مجروح|مصدوم)\s+(?:شدن\s+)?(\d+)")
MANY_TOLL = re.compile(r"(?:ده ?ها|صدها)\s+(?:نفر\s+)?(?:کشته|زخمی|مجروح|مصدوم)")
ENERGY_ATTACK = re.compile(
    r"(?:حمله|انفجار|آتش|هدف قرار|اصابت|پهپاد|موشک)[^.؛]{0,40}(?:خط لوله|پالایشگاه|میدان نفتی|"
    r"میدان گازی|تاسیسات نفتی|تأسیسات نفتی|نفتکش|نفت کش|پایانه نفتی|نیروگاه)"
    r"|(?:خط لوله|پالایشگاه|میدان نفتی|میدان گازی|تاسیسات نفتی|تأسیسات نفتی|نفتکش|نفت کش|پایانه نفتی|نیروگاه)"
    r"[^.؛]{0,40}(?:حمله|انفجار|آتش گرفت|هدف قرار|اصابت)")
EDITOR_RULES = """
SECURITY AND MASS CASUALTIES ARE NEVER "LOCAL":
- A terrorist attack, armed clash, bombing, hostage-taking or killed attacker anywhere inside Iran is iran_national security news (happened=true, score 6-8), even in a small town.
- An attack, shooting, stabbing, crash or disaster with 10 or more dead or injured, in any country, is world news (score 6-8).
- An attack or explosion at an oil/gas pipeline, refinery, oil field, tanker or power plant in the Middle East is world news (score 6-8).
Ceremonies, funerals and anniversaries of such events stay LOW.

"""


def security_kind(candidate):
    """Why a story is first-tier security news the AI keeps underrating, or ""."""
    try:
        import v13_post_design as pd
        foreign_re = pd._FOREIGN_RE
    except Exception:
        foreign_re = None
    title = _norm(candidate.get("title", ""))
    if not title or CEREMONY_WORDS.search(title):
        return ""
    digits = title.translate(_NUM)
    tolls = [int(a or b) for a, b in TOLL.findall(digits) if (a or b).isdigit()]
    if (tolls and max(tolls) >= 10) or MANY_TOLL.search(title):
        return "mass-casualty"
    if ENERGY_ATTACK.search(title):
        return "energy-attack"
    category = _norm(candidate.get("category", ""))
    iranian = "ایران" in category or "ایران" in title
    if iranian and IRAN_SECURITY.search(title) and not (foreign_re and foreign_re.search(title)):
        return "iran-security"
    return ""


def _patch_editor_gate():
    import v13_editor_gate as eg
    if getattr(eg, "_text_polish", False):
        return
    orig_accepts = eg.ai_accepts

    def ai_accepts(verdict, candidate=None):
        if orig_accepts(verdict, candidate):
            return True
        if candidate is None:
            return False
        try:
            if eg.NON_EVENT.search(_norm(candidate.get("title", ""))):
                return False
            kind = security_kind(candidate)
            if kind and verdict.get("happened") and int(verdict.get("score", 0) or 0) >= 2:
                print(f"V13 TEXT POLISH: editor override ({kind}) -> {candidate.get('title', '')}", flush=True)
                return True
        except Exception:
            pass
        return False

    eg.ai_accepts = ai_accepts
    if "SECURITY AND MASS CASUALTIES" not in eg.PROMPT and "Story:\nTITLE" in eg.PROMPT:
        eg.PROMPT = eg.PROMPT.replace("Story:\nTITLE", EDITOR_RULES + "Story:\nTITLE", 1)
    # Old cached "local" rejections must be judged again under the new rules.
    eg.CACHE_VERSION = "v4"
    eg._text_polish = True


# --------------------------------------------------------------------------
# 6) Signature header instead of region/topic labels
# --------------------------------------------------------------------------

BRAND_HEADER = "💓 نبض خبر"
_FOOTER_PULSE = re.compile(r"(?m)^💓 نبض خبر: [▰▱]+\n?")


def signature_header(level, urgent=False, emoji="", label="", title=""):
    try:
        import v13_post_design as pd
        bar = pd.meter(level)
    except Exception:
        bar = "▰▰▰▱▱"
    return f"{BRAND_HEADER} {bar}"


def site_tags(item):
    """Website cards/pages: no topic tag (owner's request); a real breaking stamp only."""
    return '<span class="tag urgent">فوری</span>' if item.get("urgent") else ""


def drop_footer_pulse(caption):
    caption = str(caption or "")
    if not caption.startswith(BRAND_HEADER):
        return caption
    return _FOOTER_PULSE.sub("", caption)


# --------------------------------------------------------------------------
# Install
# --------------------------------------------------------------------------

_INSTALLED = {"done": False}


def install():
    if _INSTALLED["done"]:
        return
    parts = []

    try:
        import v13_post_design as pd
        orig_classify = pd.classify
        orig_build = pd.build_caption

        def classify(title, candidate=None):
            level, urgent, emoji, label = orig_classify(title, candidate)
            try:
                text = _norm(title)
                if is_sport(text):
                    emoji, label = "⚽", "ورزش"
                elif label == "ورزش" and SCIENCE.search(text):
                    iran = any(t in text for t in pd.IRAN_TERMS)
                    emoji, label = ("🇮🇷", "ایران") if iran else ("🌍", "جهان")
            except Exception:
                pass
            return level, urgent, emoji, label

        def build_caption(title, body, formatter):
            _CTX["lead"] = ""
            try:
                title = fix_text(title)
                body = fix_text(body)
                ftitle = formatter.format_title(title)
                sentences = pd._split(formatter.format_body(body))
                if sentences:
                    first = lead_index(ftitle, sentences)
                    if first:
                        print("V13 TEXT POLISH: detail line matches the headline better; made it the lead.",
                              flush=True)
                        sentences = [sentences[first]] + sentences[:first] + sentences[first + 1:]
                        body = " ".join(sentences)
                    _CTX["lead"] = sentences[0]
                    kept = [sentences[0]]
                    for sentence in sentences[1:]:
                        if is_filler(sentence):
                            continue
                        if is_redundant(sentence, " ".join([ftitle] + kept)):
                            continue
                        kept.append(sentence)
                    joined = " ".join(kept)
                    if len(joined) < 70 or len(joined.split()) < 12:
                        kept = sentences  # keep the post publishable; the thin-body gate decides
                    if len(kept) != len(sentences):
                        print(f"V13 TEXT POLISH: dropped {len(sentences) - len(kept)} filler/repeat line(s).",
                              flush=True)
                        body = " ".join(kept)
            except Exception as exc:
                print(f"V13 TEXT POLISH: detail filter skipped ({type(exc).__name__}).", flush=True)
            try:
                return drop_footer_pulse(orig_build(title, body, formatter))
            finally:
                _CTX["lead"] = ""

        pd.classify = classify
        pd.topic_of = topic_of
        pd.build_caption = build_caption
        pd.header_line = signature_header
        parts.append("labels+details")
        parts.append("signature-header")
        try:
            import v13_growth as growth
            growth._tags = site_tags
            parts.append("site-no-tags")
        except Exception as exc:
            print(f"V13 TEXT POLISH: site tag patch skipped ({type(exc).__name__})", flush=True)
    except Exception as exc:
        print(f"V13 TEXT POLISH: post design patch skipped ({type(exc).__name__}: {exc})", flush=True)

    try:
        import v13_ai_router as router
        orig_validate = router._validate
        orig_openai = router._openai_compatible_json
        orig_gemini = router._request_json

        def _validate(main, original_title, source, data, foreign):
            if isinstance(data, dict):
                data = dict(data)
                data["title"] = fix_text(data.get("title", ""))
                data["summary"] = fix_text(data.get("summary", ""))
            result = orig_validate(main, original_title, source, data, foreign)
            if not result:
                return result
            result = {"title": fix_text(result.get("title", "")),
                      "summary": fix_text(result.get("summary", ""))}
            reasons = extra_reasons(result["title"], result["summary"])
            if reasons:
                print("V13 TEXT POLISH: AI output rejected: " + " | ".join(reasons), flush=True)
                print(f"V13 TEXT POLISH: rejected title={result['title'][:160]!r}", flush=True)
                return None
            return result

        def _openai_compatible_json(main, provider, base_url, api_key, model, prompt, *args, **kwargs):
            return orig_openai(main, provider, base_url, api_key, model, _with_rules(prompt), *args, **kwargs)

        def _request_json(main, model, prompt, *args, **kwargs):
            return orig_gemini(main, model, _with_rules(prompt), *args, **kwargs)

        router._validate = _validate
        router._openai_compatible_json = _openai_compatible_json
        router._request_json = _request_json
        parts.append("ai-wording")
    except Exception as exc:
        print(f"V13 TEXT POLISH: AI router patch skipped ({type(exc).__name__}: {exc})", flush=True)

    try:
        import v13_story_dedup as dd
        orig_find = dd.find_duplicate
        orig_remember = dd.remember

        def find_duplicate(caption):
            match = orig_find(caption)
            if match:
                return match
            try:
                keys = head_keys(caption)
                if len(keys) < 5:
                    return None
                _, health = dd._health()
                for item in reversed(_recent_heads(health)):
                    if same_incident(keys, set(item.get("h") or [])):
                        print("V13 TEXT POLISH: same incident within 12h.", flush=True)
                        return item
            except Exception as exc:
                print(f"V13 TEXT POLISH: head check skipped ({type(exc).__name__}).", flush=True)
            return None

        def remember(caption):
            orig_remember(caption)
            try:
                keys = head_keys(caption)
                if len(keys) < 5:
                    return
                router_mod, health = dd._health()
                items = _recent_heads(health)
                items.append({"t": time.time(), "h": sorted(keys), "title": head_text(caption)[:120]})
                health[HEAD_KEY] = items[-HEAD_MAX:]
                router_mod._save_health(health)
            except Exception as exc:
                print(f"V13 TEXT POLISH: head remember skipped ({type(exc).__name__}).", flush=True)

        dd.find_duplicate = find_duplicate
        dd.remember = remember
        parts.append("12h-incident-dedup")
    except Exception as exc:
        print(f"V13 TEXT POLISH: dedup patch skipped ({type(exc).__name__}: {exc})", flush=True)

    try:
        _patch_editor_gate()
        parts.append("editor-security-rules")
    except Exception as exc:
        print(f"V13 TEXT POLISH: editor gate patch skipped ({type(exc).__name__}: {exc})", flush=True)

    _INSTALLED["done"] = True
    try:
        import v13_ai_router as router_mod
        health = router_mod._load_health()
        health["_text_polish"] = {"active": parts, "at": int(time.time())}
        router_mod._save_health(health)
    except Exception:
        pass
    print("V13 TEXT POLISH ACTIVE: " + ", ".join(parts), flush=True)
