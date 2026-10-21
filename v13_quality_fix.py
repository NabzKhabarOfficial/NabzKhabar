"""NABZ KHABAR: quality fixes from the Oct 17 review of every post published that day (13:40 Tehran).

* Loaded wording still went out: «سوختن در آتش اعتماد به ارتش تروریست آمریکا»، «بیش از ۳۴۰ کودک را به
  شهادت رسانده». Every AI translation / rewrite now gets neutral wording (ارتش تروریست آمریکا -> ارتش آمریکا,
  به شهادت رساند -> کشت, به شهادت رسیدند / شهید شدند -> کشته شدند), and a post that still calls an army or a
  country "terrorist" is refused by the final guard ("loaded-wording").
* A lead starting with «در حالی که ...» (a dangling clause, the headline's subject missing) is refused like
  «این در حالی است که» ("dangling-lead").
* The same headline went out twice, 30 minutes apart («هشدار سرپرست وزارت دفاع به آمریکا درباره تأثیر قدرت
  موشکی ایران»): the same-event judge now calls it a repeat without asking any AI when every meaningful word of
  a published headline (5+ words) is in the new headline and it adds at most 2 words (an update adds more).

Oct 18, 20:50 Tehran (review of all 92 posts published since Oct 17 16:00):
* machine-translated words: «سوزش» for a fire (-> «آتش‌سوزی»), «رزورت» (-> «استراحتگاه»), «کلکلته» (-> «کلکته»);
  «۲۰ شهید و زخمی» (-> «۲۰ کشته و زخمی») in every AI output;
* outlet names the guard did not know: «ان بی سی»، «سی ان ان»، «سی بی اس»، «ای بی سی»، «فاکس نیوز»;
* six events went out twice (Kolkata crowd crush, settlers attacking EU diplomats, the Alberta base fire,
  Netanyahu on a nuclear Iran, two Hegseth posts 31 s apart, Zelensky / Starlink): nemo called them "new" when the
  strong models were out of quota. Now a nemo "new" for a post that shares 4+ meaningful words (and half of the
  earlier headline's words) with a published headline counts as a repeat; "update" and "reaction" still pass.
  Posts allowed earlier in the same run are added to the judge's list, so two posts of one event in one run
  are caught too.

Oct 18, 21:10 Tehran (live channel read, t.me/s/NabzKhabarOfficial): a lead with no subject went out
(«⚡️ تأکید کرد: ایران هیچ گاه ...» under a Pezeshkian headline), and provincial items passed although the editor
gate vetoes them («مدیرکل پزشکی قانونی خوزستان: ...», Oct 16 «فرماندار چابهار: ...»), so some rescue path skips
the gate. The final guard now refuses a lead that starts with a bare verb («تأکید کرد»، «گفت»، «افزود» ...)
and a headline led by a provincial / city official unless a hard event happened ("local-level"). «ناراضیتی» ->
«نارضایتی».
Oct 19, 15:40 Tehran (first full read of docs/review/telegram_log.json, 65 sends since Oct 18 22:00):
* «رئیس وزیر اسرائیل» -> «نخست‌وزیر»; «رئیس جمهور پیشین آمریکا، ترامپ» (Trump is the sitting president) ->
  «رئیس‌جمهور آمریکا، ترامپ»; «آتش سوزی آتش سوزی» / «آتش آتش‌سوزی» and any two words written twice in a row
  are written once; «عکاس واشینگتن پست» -> «یک عکاس خبری» (a reporter of an outlet stays in the story without the
  outlet's name); outlet variants the guard did not know: «واشینگتن پست», «رادیو فردا», «دویچه وله», «یورونیوز»,
  «ایندیپندنت», «فرانس ۲۴», «هاآرتص», «یدیعوت آحارونوت», «الشرق الاوسط».
* provincial items still went out because their headline does not START with an official's title: «رئیس پلیس
  راهور بوشهر: ...», «سرپرست پلیس آگاهی خوزستان: ...». A headline whose speaker (the part before «:») is an
  official of a province or provincial city is now "local-level" unless a hard event happened; advance notices of
  controlled blasts («انفجار کنترل شده مهمات در دزفول», «عملیات انفجار در معدن کهک») are always "local-notice".
Oct 21, 14:30 Tehran (review of every post since Oct 19 15:40, telegram_log + live channel):
* loaded labels still went out: «رژیم جولانی», «مستعمره نشینان اسرائیلی», «تجاوزات», «مزدوران سعودی»,
  «پهپادهای انتحاری», «تجزیه طلب», «ماجراجویی نظامی», «کشته شدن تروریست». Neutral wording now: دولت جولانی,
  شهرک‌نشینان, حملات, نیروهای وابسته به عربستان, پهپادهای انفجاری, جدایی‌طلب, اقدام نظامی, فرد مسلح / حمله‌ی
  مسلحانه («تروریست» stays when it is attributed or a designation list: «در فهرست تروریستی», «... را تروریست نامید»).
  A post that still carries one of these labels is refused ("loaded-wording").
* «جروزالم پست» (headline and lead) -> «یک رسانه‌ی اسرائیلی» (also «تایمز اسرائیل»); «مارک روبینو» -> «مارکو روبیو»;
  «غزه و نوار غزه» -> «نوار غزه»; «کشته بارتر» -> «مرگبارتر».
* trivial provincial items: «زلزله در نزدیکی راور کرمان ثبت شد» (a small quake, nobody hurt) -> "small-quake";
  «فرماندار اراک: خبر انفجار ... کذب است» (a local denial passed because of the word «انفجار») -> "local-level";
  «آتش سوزی پژو پارس در محور سرباز–کهیری دو جان باخت» (a road crash / car fire in Iran, under five dead) ->
  "local-crash".
Oct 21, 15:00 Tehran:
* a headline with two claims joined by «؛» where the text supports only one («قیمت نفت ... افزایش یافت؛ طلا ...
  کاهش یافت» with nothing about oil; «ویتکاف ...؛ زلنسکی از توقف حملات ... سخن گفت» with no Zelensky in the text):
  the AI title keeps only the claims the text supports; a post that still has an unsupported claim is refused
  ("headline-body-gap").
* commentary is not news: a headline about a debate / column / opinion piece («مناظره ...»، «یادداشت ...»،
  «سرمقاله ...»، «دیدگاه ...») or a bare question headline («آیا ... ؟») is refused ("opinion").
Any error = the bot runs as before.
"""

import re
import time

NEUTRAL = (
    (re.compile(r"ارتش\s+(?:تروریست(?:ی)?|تروریستی)\s+(آمریکا|اسرائیل|ایالات\s+متحده)"), r"ارتش \1"),
    (re.compile(r"(آمریکا|اسرائیل)ی?\s+تروریست(?![\u0600-\u06FF])"), r"\1"),
    (re.compile(r"به\s+شهادت\s+رسانده"), "کشته"),
    (re.compile(r"به\s+شهادت\s+رساندند"), "کشتند"),
    (re.compile(r"به\s+شهادت\s+رساند"), "کشت"),
    (re.compile(r"به\s+شهادت\s+رسیدند"), "کشته شدند"),
    (re.compile(r"به\s+شهادت\s+رسید"), "کشته شد"),
    (re.compile(r"شهید\s+شدند"), "کشته شدند"),
    (re.compile(r"([0-9\u06F0-\u06F9]+)\s+شهید(?![\u0600-\u06FF])"), r"\1 کشته"),
    (re.compile(r"(?<![\u0600-\u06FF\u200c])سوزش(?![\u0600-\u06FF])"), "آتش‌سوزی"),
    (re.compile(r"(?<![\u0600-\u06FF])ر(?:ی)?زورت(?![\u0600-\u06FF])"), "استراحتگاه"),
    (re.compile(r"کلکلته"), "کلکته"),
    (re.compile(r"ناراضیتی"), "نارضایتی"),
    (re.compile(r"(?<![\u0600-\u06FF])رئیس[\s\u200c]+وزیر(?![\u0600-\u06FF])"), "نخست‌وزیر"),
    (re.compile(r"رئیس[\s\u200c]*جمهور(?:ی)?[\s\u200c]+(?:پیشین|سابق)[\s\u200c]+(?:آمریکا|ایالات[\s\u200c]+متحده)"
                r"(?=،?[\s\u200c]*(?:دونالد[\s\u200c]+)?ترامپ)"), "رئیس‌جمهور آمریکا"),
    (re.compile(r"((?:دونالد[\s\u200c]+)?ترامپ،?[\s\u200c]*)رئیس[\s\u200c]*جمهور(?:ی)?[\s\u200c]+(?:پیشین|سابق)"), "\\1رئیس‌جمهور"),
    (re.compile(r"آتش[\s\u200c]*(?:سوزی[\s\u200c]+)?آتش[\s\u200c]*سوزی"), "آتش‌سوزی"),
    (re.compile(r"(?<![\u0600-\u06FF])([\u0600-\u06FF]{2,}[\s\u200c]+[\u0600-\u06FF]{2,})[\s\u200c]+\1(?![\u0600-\u06FF])"), r"\1"),
)
OUTLET_WORDS = (r"(?:روزنامه[\s\u200c]+|شبکه[\s\u200c]+|نشریه[\s\u200c]+)?(?:واشی?نگتن[\s\u200c]+پست|نیویورک[\s\u200c]+تایمز|وال[\s\u200c]+استریت[\s\u200c]+ژورنال|"
                r"گاردین|رویترز|آسوشیتد[\s\u200c]*پرس|فرانس[\s\u200c]+پرس|الجزیره|العربیه|بی[\s\u200c]*بی[\s\u200c]*سی|سی[\s\u200c]*ان[\s\u200c]*ان|اسکای[\s\u200c]*نی?وز)")
REPORTER_OF_OUTLET = re.compile(r"(عکاس|خبرنگار|گزارشگر|روزنامه[\s\u200c]*نگار|فیلمبردار)(?:ان)?[\s\u200c]+" + OUTLET_WORDS + r"(?![\u0600-\u06FF])")
REPORTER_WORD = {"عکاس": "یک عکاس خبری", "خبرنگار": "یک خبرنگار", "گزارشگر": "یک گزارشگر", "فیلمبردار": "یک فیلمبردار خبری"}
EXTRA_OUTLETS = (r"(?:شبکه\s+)?(?:ان[\s\u200c]*بی[\s\u200c]*سی|سی[\s\u200c]*ان[\s\u200c]*ان|سی[\s\u200c]*بی[\s\u200c]*اس|"
                 r"ای[\s\u200c]*بی[\s\u200c]*سی(?![\s\u200c]*نیوز\s*ایران)|فاکس[\s\u200c]*نیوز|واشینگتن[\s\u200c]+پست|"
                 r"رادیو[\s\u200c]+فردا|دویچه[\s\u200c]*وله|یورو[\s\u200c]*نیوز|ایندیپندنت|فرانس[\s\u200c]*(?:۲۴|24)|"
                 r"ها[\s\u200c]*آرتص|ها[\s\u200c]*آرتز|یدیعوت(?:[\s\u200c]+آحارونوت)?|الشرق[\s\u200c]+الاوسط)|")
RUN_HEADS = []  # headlines the same-event judge allowed in this run
LOADED = re.compile(r"ارتش\s+تروریست|تروریست(?:ی)?\s+(?:آمریکا|اسرائیل)|(?:آمریکا|اسرائیل)ی?\s+تروریست(?![\u0600-\u06FF])")
DANGLING = re.compile(r"^\s*(?:در\s+حالی\s+که\s|(?:تأکید|تاکید|اعلام|اظهار|عنوان|اضافه|خاطرنشان|تصریح)\s+(?:کرد|کردند)|"
                      r"(?:گفت|افزود|ادامه\s+داد|یادآور\s+شد)(?![\u0600-\u06FF]))")
LOCAL_HEAD = re.compile(r"^\s*(?:مدیر\s*کل(?!\s+(?:آژانس|سازمان|یونسکو|صندوق|بانک|فائو|اینترپل|یونیسف|دفتر\s+سازمان))|معاون\s+استاندار(?![\u0600-\u06FF])|استاندار(?![\u0600-\u06FF])(?!\s+تهران)|فرماندار(?![\u0600-\u06FF])|بخشدار|شهردار|امام\s+جمعه|"
                        r"رئیس\s+(?:شورای\s+شهر|دادگستری\s+استان|پلیس\s+راه\s+استان)|نماینده\s+مردم|فرمانده\s+سپاه\s+استان)")
PROVINCES = (r"(?:آذربایجان|اردبیل|اصفهان|البرز|ایلام|بوشهر|چهارمحال|بختیاری|خراسان|خوزستان|زنجان|سمنان|سیستان|بلوچستان|"
             r"فارس|قزوین|(?<![\u0600-\u06FF])قم(?![\u0600-\u06FF])|کردستان|کرمان|کرمانشاه|کهگیلویه|گلستان|گیلان|لرستان|مازندران|"
             r"(?<![\u0600-\u06FF])مرکزی(?![\u0600-\u06FF])|هرمزگان|همدان|(?<![\u0600-\u06FF])یزد(?![\u0600-\u06FF])|"
             r"اهواز|مشهد|تبریز|شیراز|کرج|رشت|ساری|ارومیه|زاهدان|بندرعباس|کیش|قشم|دزفول|آبادان|خرمشهر|بیرجند|گرگان|"
             r"خرم[\s\u200c]*آباد|سنندج|بجنورد|شهرکرد|یاسوج|اراک|کاشان|نیشابور|سبزوار|بابل|آمل|قزوین|زنجان|اردبیل|"
             r"شهرستان|استانداری|فرمانداری)")
OFFICIAL = re.compile(r"(?:رئیس|سرپرست|فرمانده|معاون|مدیر|دادستان|استاندار|فرماندار|بخشدار|شهردار|نماینده|سخنگوی|دبیر|مسئول|رئیس[\s\u200c]*کل)")
PROVINCE_RX = re.compile(PROVINCES)
LOCAL_NOTICE = re.compile(r"انفجار(?:[\s\u200c]*های)?[\s\u200c]+کنترل[\s\u200c]*شده|عملیات[\s\u200c]+انفجار[\s\u200c]+(?:در[\s\u200c]+)?معدن|"
                          r"انهدام[\s\u200c]+(?:کنترل[\s\u200c]*شده[\s\u200c]+)?مهمات|خنثی[\s\u200c]*سازی[\s\u200c]+مهمات[\s\u200c]+عمل[\s\u200c]*نکرده")

# a real event in a provincial official's headline (not statistics: «جان باختگان تصادفات» is not «جان باختند»)
SPEAKER_HARD = re.compile(r"کشته[\s\u200c]+(?:شد|شدند)|جان[\s\u200c]+باخت(?:ند)?(?![\u0600-\u06FF])|زخمی[\s\u200c]+شدند|"
                          r"انفجار(?![\s\u200c]+کنترل)|زلزله|زمین[\s\u200c]*لرزه|سیل|آتش[\s\u200c]*سوزی|حمله|"
                          r"شلیک|سقوط|گروگان[\s\u200c]*گیری|ترور")

_TERR_ATTR = re.compile(r"(?:فهرست|تحریم|سازمان[\s\u200c]*های|عنوان|نامید|نامیده|خواند|خوانده|اتهام|متهم)$")
_TERR_AFTER = re.compile(r"[\s\u200c]*(?:»|نامید|نامیده|خواند|خوانده|دانست|توصیف|معرفی)")


def _terr(word):
    def sub(m):
        before = m.string[max(0, m.start() - 24):m.start()].rstrip(" \u200c")
        after = m.string[m.end():m.end() + 14]
        if _TERR_ATTR.search(before) or "«" in before[-3:] or _TERR_AFTER.match(after):
            return m.group(0)  # attributed, or a designation list: the word stays
        return word
    return sub


_MERC = {"سعودی": "عربستان", "آمریکایی": "آمریکا", "اماراتی": "امارات", "اسرائیلی": "اسرائیل"}
NEUTRAL_V6 = (
    (re.compile(r"رژیم[\s\u200c]+(?:صهیونیستی|اشغالگر(?:[\s\u200c]+قدس)?)"), "اسرائیل"),
    (re.compile(r"رژیم[\s\u200c]+جولانی"), "دولت جولانی"),
    (re.compile(r"مستعمره[\s\u200c]*نشین"), "شهرک‌نشین"),
    (re.compile(r"(?<![\u0600-\u06FF])تجاوزات(?![\u0600-\u06FF])"), "حملات"),
    (re.compile(r"مزدوران[\s\u200c]+(سعودی|آمریکایی|اماراتی|اسرائیلی)"), lambda m: "نیروهای وابسته به " + _MERC[m.group(1)]),
    (re.compile(r"(?<![\u0600-\u06FF])مزدوران(?![\u0600-\u06FF])"), "نیروهای وابسته"),
    (re.compile(r"پهپاد([\s\u200c]*های)?[\s\u200c]+انتحاری"), lambda m: "پهپاد" + (m.group(1) or "") + " انفجاری"),
    (re.compile(r"ماجراجویی(?:[\s\u200c]*های)?[\s\u200c]+نظامی"), "اقدام نظامی"),
    (re.compile(r"تجزیه[\s\u200c]*طلب"), "جدایی‌طلب"),
    (re.compile(r"(حمله|حملات|عملیات|اقدام)([\s\u200c]*(?:های|ها))?[\s\u200c]+تروریستی(?![\u0600-\u06FF])"),
     lambda m: m.group(1) + (m.group(2) or "") + " مسلحانه"),
    (re.compile(r"(?<![\u0600-\u06FF\u200c])تروریستی(?![\u0600-\u06FF])"), _terr("مسلح")),
    (re.compile(r"(?<![\u0600-\u06FF\u200c])تروریست[\s\u200c]*ها(?![\u0600-\u06FF])"), _terr("افراد مسلح")),
    (re.compile(r"(?<![\u0600-\u06FF\u200c])تروریست(?![\u0600-\u06FF\u200c])"), _terr("فرد مسلح")),
    (re.compile(r"روبینو"), "روبیو"),
    (re.compile(r"مارک[\s\u200c]+روبیو"), "مارکو روبیو"),
    (re.compile(r"(?<![\u0600-\u06FF])غزه[\s\u200c]+و[\s\u200c]+نوار[\s\u200c]+غزه"), "نوار غزه"),
    (re.compile(r"کشته[\s\u200c]*بارتر"), "مرگبارتر"),
    (re.compile(r"(?:روزنامه[\s\u200c]+|نشریه[\s\u200c]+|پایگاه[\s\u200c]+)?(?:جروزالم|اورشلیم)[\s\u200c]*پست"), "یک رسانه‌ی اسرائیلی"),
    (re.compile(r"(?:روزنامه[\s\u200c]+|نشریه[\s\u200c]+|پایگاه[\s\u200c]+)?تایمز[\s\u200c]+(?:[اآ]و[\s\u200c]+)?اسرائیل"), "یک رسانه‌ی اسرائیلی"),
)
LOADED_V6 = re.compile(r"رژیم[\s\u200c]+(?:صهیونیستی|اشغالگر|جولانی)|مستعمره[\s\u200c]*نشین|مزدوران|تجاوزات|"
                       r"پهپاد(?:[\s\u200c]*های)?[\s\u200c]+انتحاری|جروزالم[\s\u200c]*پست|اورشلیم[\s\u200c]*پست")
FA_NUM = {"یک": 1, "دو": 2, "سه": 3, "چهار": 4, "پنج": 5, "شش": 6, "هفت": 7, "هشت": 8, "نه": 9, "ده": 10}
QUAKE = re.compile(r"زلزله|زمین[\s\u200c]*لرزه")
MAGNITUDE = re.compile(r"([0-9\u06F0-\u06F9]+(?:[.\u066B/][0-9\u06F0-\u06F9]+)?)[\s\u200c]*(?:ریشتر|درجه|ریکتر)")
HURT = re.compile(r"کشته|زخمی|مصدوم|مجروح|جان[\s\u200c]*باخت|خسارت|تخریب|آوار|ویران")
DENIAL = re.compile(r"کذب|تکذیب|شایعه|صحت[\s\u200c]+ندارد|واقعیت[\s\u200c]+ندارد")
CRASH = re.compile(r"تصادف|واژگونی|واژگون|برخورد[\s\u200c]+(?:دو|سه|چند)?[\s\u200c]*(?:خودرو|دستگاه)|"
                   r"آتش[\s\u200c]*سوزی[\s\u200c]+(?:خودرو|پژو|پراید|سمند|پیکان|تیبا|اتوبوس|کامیون|وانت)|"
                   r"(?<![\u0600-\u06FF])(?:پژو|پراید|سمند|پیکان|تیبا|وانت)(?![\u0600-\u06FF])")
DEATHS = re.compile(r"([0-9\u06F0-\u06F9]+|یک|دو|سه|چهار|پنج|شش|هفت|هشت|نه|ده)[\s\u200c]+(?:نفر[\s\u200c]+)?(?:کشته|جان[\s\u200c]*باخت|فوتی|مصدوم|زخمی)")


def _num(s):
    s = str(s).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٫", "0123456789."))
    if s in FA_NUM:
        return FA_NUM[s]
    try:
        return float(s.replace("/", "."))
    except ValueError:
        return None


def small_quake(title, text):
    """A minor earthquake (under 4.5, nobody hurt): not news for the channel."""
    if not QUAKE.search(str(title or "")) or HURT.search(text):
        return False
    mags = [m for m in (_num(x) for x in MAGNITUDE.findall(text)) if m is not None]
    if mags:
        return max(mags) < 4.5
    t = str(title or "")
    return bool(re.search(r"ثبت[\s\u200c]+شد", t) and PROVINCE_RX.search(t))


def local_crash(title, text):
    """A road crash / car fire inside Iran with fewer than five dead: a provincial item."""
    t = str(title or "")
    if not CRASH.search(t):
        return False
    if not (PROVINCE_RX.search(t) or re.search(r"(?<![\u0600-\u06FF])محور(?![\u0600-\u06FF])", t)):
        return False
    counts = [n for n in (_num(x) for x in DEATHS.findall(text)) if n is not None]
    return not counts or max(counts) < 5


TITLE_STOP = set("""از با به در که را و یا این آن برای تا بر یک های ها می شد شود شده شدند کرد کردند کرده است بود بودند
خواهد گفت گفته سخن داد دادند یافت یافته دارد ندارد هم نیز پس پیش روی درباره علیه بین میان خود او آنها ما شما
اعلام تاکید تأکید ادامه جدید""".split())
OPINION = re.compile(r"(?<![\u0600-\u06FF])(?:مناظره|یادداشت|سرمقاله|دیدگاه|گفت[\s\u200c]*و[\s\u200c]*گوی[\s\u200c]+ویژه)(?![\u0600-\u06FF])")


def _words(text):
    return [w for w in re.findall(r"[\u0600-\u06FF]{3,}", str(text or "").replace("\u200c", ""))
            if w not in TITLE_STOP]


def part_supported(part, body):
    """True when at least half of a headline part's meaningful words (or their 4-letter stems) are in the text."""
    words = _words(part)
    if len(words) < 2:
        return True
    text = str(body or "").replace("\u200c", "")
    have = sum(1 for w in words if w in text or w[:4] in text)
    return have * 2 >= len(words)


def repair_title(title, body):
    """Drop the «؛» parts of a headline that the text does not support (keeps at least one part)."""
    t = str(title or "")
    if "؛" not in t or not str(body or "").strip():
        return t
    parts = [x.strip() for x in t.split("؛") if x.strip()]
    keep = [x for x in parts if part_supported(x, body)]
    if not keep or len(keep) == len(parts):
        return t
    return "؛ ".join(keep)


def headline_gap(title, body):
    t = str(title or "")
    if "؛" not in t or not str(body or "").strip():
        return False
    return any(not part_supported(x, body) for x in t.split("؛") if x.strip())


def is_opinion(title):
    t = str(title or "").strip()
    return bool(OPINION.search(t) or (t.endswith("؟") and re.match(r"^\s*آیا(?![\u0600-\u06FF])", t)))


def local_speaker(title):
    """True when the headline's speaker (before «:») is an official of a province / provincial city."""
    t = str(title or "")
    if ":" not in t:
        return False
    speaker = t.split(":", 1)[0]
    if len(speaker.split()) > 10:
        return False
    return bool(OFFICIAL.search(speaker) and PROVINCE_RX.search(speaker))


MIN_WORDS = 5
NEMO_NEW_SHARED = 4
_DONE = {"v": False}


def neutral(text):
    text = str(text or "")
    for rx, good in NEUTRAL_V6 + NEUTRAL:
        text = rx.sub(good, text)
    text = REPORTER_OF_OUTLET.sub(lambda m: REPORTER_WORD.get(m.group(1), "یک روزنامه‌نگار"), text)
    return text


def _install_router():
    import v13_ai_router as r
    prev = r._validate
    if getattr(prev, "_v13_neutral", False):
        return

    def validate(main, original_title, source, data, foreign):
        if isinstance(data, dict):
            data = dict(data)
            for k in ("title", "summary"):
                data[k] = neutral(data.get(k, ""))
            try:
                data["title"] = repair_title(data.get("title", ""), data.get("summary", ""))
            except Exception:
                pass
        return prev(main, original_title, source, data, foreign)

    validate._v13_neutral = True
    r._validate = validate


def _install_guard():
    import v13_relevance_gate as rg
    import v13_final_guard as fg
    prev = rg.caption_problem
    if getattr(prev, "_v13_quality", False):
        return

    def caption_problem(title, sentences):
        reason = prev(title, sentences)
        if reason:
            return reason
        try:
            if fg._BOARD.search(str(title or "")):
                return ""
            sents = [str(x or "") for x in sentences or []]
            whole = " ".join([str(title or "")] + sents)
            found = []
            m = LOADED.search(whole) or LOADED_V6.search(whole)
            if m:
                found.append(("loaded-wording", m.group(0)))
            if sents and DANGLING.search(sents[0]):
                found.append(("dangling-lead", sents[0][:60]))
            if LOCAL_NOTICE.search(str(title or "")):
                found.append(("local-notice", str(title or "")[:60]))
            if is_opinion(title):
                found.append(("opinion", str(title or "")[:60]))
            if headline_gap(title, " ".join(sents)):
                found.append(("headline-body-gap", str(title or "")[:60]))
            if small_quake(title, whole):
                found.append(("small-quake", str(title or "")[:60]))
            if local_crash(title, whole):
                found.append(("local-crash", str(title or "")[:60]))
            if local_speaker(title) and not LOCAL_HEAD.search(str(title or "")):
                hard = bool(SPEAKER_HARD.search(str(title or ""))) and not DENIAL.search(str(title or ""))
                try:
                    import v13_editor_gate as g
                    hard = hard or bool(g.war_zone(title))
                except Exception:
                    pass
                if not hard:
                    found.append(("local-level", str(title or "")[:60]))
            if LOCAL_HEAD.search(str(title or "")):
                try:
                    import v13_editor_gate as g
                    hard = bool(g.HARD_HAPPENED.search(g._norm(title)) or g.war_zone(title))
                except Exception:
                    hard = True
                if DENIAL.search(str(title or "")):
                    hard = False
                if not hard:
                    found.append(("local-level", str(title or "")[:60]))
        except Exception:
            return ""
        if not found:
            return ""
        fg._log(title, found)
        print("V13 FINAL GUARD: refused (" + ", ".join(f"{a}: {b}" for a, b in found) + f") -> {str(title or '')[:120]}",
              flush=True)
        return "final-guard:" + found[0][0]

    caption_problem._v13_quality = True
    rg.caption_problem = caption_problem


def same_headline(ej, prompt):
    """Item number of a published headline whose meaningful words are all in the new post, else 0."""
    try:
        head = prompt.split("NEW POST (about to be published):", 1)[1].split("ALREADY PUBLISHED", 1)[0].strip()
        listing = prompt.split("ALREADY PUBLISHED in the last 24 hours:", 1)[1].split("Does the NEW POST", 1)[0]
        dd = ej._dd()
        common = getattr(dd, "COMMON", set())
        first = head.splitlines()[0] if head.splitlines() else head
        hf = set(dd.fingerprint(first)) - set(common)
        for line in listing.splitlines():
            m = re.match(r"^\s*(\d+)\.\s*(.+)$", line)
            if not m:
                continue
            tf = set(dd.fingerprint(m.group(2))) - set(common)
            if len(tf) >= MIN_WORDS and tf <= hf and len(hf - tf) <= 2:  # a real update adds words
                return int(m.group(1))
    except Exception:
        return 0
    return 0


def shared_with_published(ej, prompt):
    """Item number of a published headline sharing NEW_SHARED+ meaningful words (and half its words), else 0."""
    try:
        head = prompt.split("NEW POST (about to be published):", 1)[1].split("ALREADY PUBLISHED", 1)[0].strip()
        listing = prompt.split("ALREADY PUBLISHED in the last 24 hours:", 1)[1].split("Does the NEW POST", 1)[0]
        dd = ej._dd()
        common = set(getattr(dd, "COMMON", set()))
        hf = set(dd.fingerprint(head)) - common
        best, best_n = 0, 0
        for line in listing.splitlines():
            m = re.match(r"^\s*(\d+)\.\s*(.+)$", line)
            if not m:
                continue
            tf = set(dd.fingerprint(m.group(2))) - common
            n = len(tf & hf)
            if n >= NEMO_NEW_SHARED and n * 2 >= len(tf) and n > best_n:
                best, best_n = int(m.group(1)), n
        return best
    except Exception:
        return 0


def _install_judge():
    import v13_event_judge as ej
    prev = ej.ask
    if getattr(prev, "_v13_same_headline", False):
        return

    def ask(prompt, skip=""):
        text = str(prompt or "")
        if text.startswith("You are the duplicate checker"):
            n = same_headline(ej, text)
            if n:
                return {"verdict": "repeat", "match": n, "why": "same headline words (rule)", "model": "rule/same-headline"}
            got = prev(prompt, skip=skip)
            if (got and str(got.get("model", "")).startswith("mistral/")
                    and str(got.get("verdict", "")).strip().lower() == "new"):
                n = shared_with_published(ej, text)
                if n:
                    return {"verdict": "repeat", "match": n, "why": "nemo said new, 4+ shared words (rule)",
                            "model": "rule/nemo-new-overlap"}
            return got
        return prev(prompt, skip=skip)

    ask._v13_same_headline = True
    ej.ask = ask

    prev_pub = ej.published
    if not getattr(prev_pub, "_v13_run_heads", False):
        def published(health, now=None):
            out = list(prev_pub(health, now))
            have = {x.get("title", "") for x in out}
            t = now or time.time()
            for h in RUN_HEADS:
                if h and h not in have:
                    out.insert(0, {"t": t, "title": h})
            return out[:ej.MAX_PUBLISHED + len(RUN_HEADS)]

        published._v13_run_heads = True
        ej.published = published

    prev_judge = ej.judge
    if not getattr(prev_judge, "_v13_run_heads", False):
        def judge(caption):
            got = prev_judge(caption)
            if got is None:
                try:
                    head = ej._head(caption).strip()
                    first = head.splitlines()[0] if head else ""
                    if len(first) >= 12:
                        RUN_HEADS.append(first[:110])
                except Exception:
                    pass
            return got

        judge._v13_run_heads = True
        ej.judge = judge


def _install_outlets():
    import v13_final_guard as fg
    p = fg.OUTLET_NAMES.pattern
    if getattr(fg, "_v13_extra_outlets", False):  # (Oct 19: the old «فاکس» marker was already in the
        return                                      # guard's own list, so these names were never added)
    if "(?:بلومبر" in p:
        p = p.replace("(?:بلومبر", "(?:" + EXTRA_OUTLETS + "بلومبر", 1)
    elif "|بلومبر" in p:
        p = p.replace("|بلومبر", "|" + EXTRA_OUTLETS + "بلومبر", 1)
    else:
        return
    fg.OUTLET_NAMES = re.compile(p, fg.OUTLET_NAMES.flags)
    fg._v13_extra_outlets = True


def install():
    if _DONE["v"]:
        return
    for fix in (_install_router, _install_guard, _install_judge, _install_outlets):
        try:
            fix()
        except Exception as exc:
            print(f"V13 QUALITY FIX: {fix.__name__} not installed ({type(exc).__name__}: {exc})", flush=True)
    try:
        import v13_review_log  # every Telegram send + every refused story, for Brain's daily review
        v13_review_log.install()
    except Exception as exc:
        print(f"V13 QUALITY FIX: review log not installed ({type(exc).__name__}: {exc})", flush=True)
    _DONE["v"] = True
    print("V13 QUALITY FIX ACTIVE: neutral wording (v6 labels), dangling «در حالی که» leads, same-headline repeats, "
          "nemo-new overlap repeats, run-local headlines, extra outlet names, provincial speakers, blast notices, "
          "small quakes, local crashes, local denials, headline-body gaps, opinion pieces", flush=True)
