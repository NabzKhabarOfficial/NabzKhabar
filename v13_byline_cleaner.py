"""Deterministic cleanup for publisher/reporter bylines at the start of news text.

Also strips news-site page chrome that the article extractor sometimes keeps in the body
(Mehr/ISNA-style "۱۶ مهر ۱۴۰۵، ۲۲:۰۶ کد مطلب 6972118 بین الملل غرب آسیا ..." header with the
section breadcrumb repeated and the headline repeated), and keeps the Persian half-space
(ZWNJ) so words like «می‌شود» and «رسانه‌ها» are not split in two. Loaded agency terms
(«رژیم صهیونیستی»، «هلاکت»، «اشغالگر»، «ارتش متجاوز») are turned into neutral wording (NEUTRAL_TERMS).
Media attributions inside the body («به گزارش خبرگزاری ...»، «به نقل از رویترز») are removed in
every sentence, and a detail line that only says what some outlet wrote is dropped (strip_media).
"""
import re

_S = r"[\s\u200c]"  # a space or a half-space (ZWNJ)

GENERIC_SOURCE_RE = re.compile(
    r"^\s*(?:باشگاه" + _S + r"+خبرنگاران" + _S + r"+جوان|خبرگزاری" + _S + r"+(?:مهر|ایسنا|ایرنا|فارس|تسنیم|دانشجو|برنا|ایلنا)|"
    r"خبرگزاری" + _S + r"+صدا" + _S + r"*و" + _S + r"*سیما|رویترز|آسوشیتدپرس|فرانس" + _S + r"+پرس|الجزیره|العربیه|"
    r"بی" + _S + r"*بی" + _S + r"*سی|دویچه" + _S + r"+وله)\s*[,،:]?\s*",
    re.I,
)

REPORTER_LEAD_RE = re.compile(
    r"^\s*(?:[^.!؟\n]{1,120}?\s*[-–—]\s*)?(?=[^\n])",
    re.I,
)

# Owner rule (Oct 9 2026): no source on any post. A headline/lead that opens with a media
# attribution («الحدث به نقل از یک منبع آمریکایی: ...»، «بلومبرگ: ...») loses that opening.
_OUTLETS = (
    r"بلومبرگ|رویترز|الحدث|الجزیره|العربیه|المیادین|اکسیوس|آکسیوس|آسوشیتدپرس|یورونیوز|"
    r"سی" + _S + r"*ان" + _S + r"*ان|بی" + _S + r"*بی" + _S + r"*سی|فرانس" + _S + r"+پرس|"
    r"نیویورک" + _S + r"+تایمز|واشنگتن" + _S + r"+پست|وال" + _S + r"+استریت" + _S + r"+ژورنال|"
    r"فایننشال" + _S + r"+تایمز|تایمز" + _S + r"+اسرائیل|(?:شبکه|روزنامه|خبرگزاری|رسانه" + _S + r"*های)" + _S + r"+[^:\n]{1,25}"
)
ATTRIBUTION_RE = re.compile(
    r"^\s*(?![^:\n]*(?:گفت|اعلام|افزود|تأکید|تاکید|نوشت))(?:(?:" + _OUTLETS + r")[^:\n]{0,50}|[^:\n]{0,40}به" + _S + r"+نقل" + _S + r"+از[^:\n]{0,40}|"
    r"[^:\n]{0,30}منبع[^:\n]{0,30})\s*[:：]\s*(?=\S)"
)

KNOWN_PREFIXES = (
    "به گزارش خبرنگار", "به گزارش", "مینا عظیمی", "کیمیا قلی پور", "کیمیا قلی‌پور", "مرتضی قانع",
)

# ---------------------------------------------------------------- page chrome
_D = r"[0-9۰-۹]"
_MONTHS = r"(?:فروردین|اردیبهشت|خرداد|تیر|مرداد|شهریور|مهر|آبان|آذر|دی|بهمن|اسفند)"
DATE_TIME_RE = re.compile(_D + r"{1,2}\s+" + _MONTHS + r"\s+" + _D + r"{4}\s*[،,\-–]?\s*(?:ساعت\s*)?" + _D + r"{1,2}:" + _D + r"{2}")
CODE_RE = re.compile(r"کد" + _S + r"*(?:مطلب|خبر)\s*[:：]?\s*" + _D + r"+")
# Oct 10: «⚡️ تاریخ انتشار: ۳۷ : ۲۲ - ۱۸ مهر ۱۴۰۵ بین الملل >> آمریکا ...»: a "published" label,
# the time printed right-to-left with spaces around the colon, the date after it, and a
# breadcrumb joined with ">>". DATE_TIME_RE (date first, "22:37") did not see it.
_TIME = _D + r"{1,2}\s*:\s*" + _D + r"{2}"
_DATE = _D + r"{1,2}\s+" + _MONTHS + r"\s+" + _D + r"{4}"
PUBLISHED_RE = re.compile(
    r"(?:⚡️?\s*)?(?:تاریخ" + _S + r"+(?:انتشار|انتشار" + _S + r"+خبر)|زمان" + _S + r"+انتشار|انتشار)\s*[:：]\s*"
    r"(?:" + _TIME + r"\s*[-–،,]?\s*(?:" + _DATE + r")?|" + _DATE + r"\s*[-–،,]?\s*(?:ساعت\s*)?(?:" + _TIME + r")?)"
    r"|" + _TIME + r"\s*[-–]\s*" + _DATE)
CRUMB_RE = re.compile(r"^\s*(?:>>|»|›|>)\s*")
# Section names news sites print above an article (breadcrumb). Only removed at the very
# start of the body, never inside a sentence.
SECTIONS = (
    "غرب آسیا و آفریقای شمالی", "آسیا و اقیانوسیه", "آمریکا و اروپا", "اروپا و آمریکا", "آفریقا",
    "بین الملل", "بین‌الملل", "سیاست خارجی", "سیاست داخلی", "سیاست", "اقتصاد", "جامعه", "حوادث",
    "فرهنگ و هنر", "علم و فناوری", "دانش و فناوری", "ورزش", "استان ها", "استان‌ها", "دفاع و امنیت",
    "انتظامی و حوادث", "مجلس", "دولت", "اخبار", "عمومی", "پربازدید", "خلاصه خبر",
)
_SECTION_RE = re.compile(
    r"^\s*(?:" + "|".join(sorted((re.escape(s).replace(r"\ ", _S + "+").replace("\u200c", _S) for s in SECTIONS),
                                 key=len, reverse=True)) + r")(?=[\s\u200c،,:\-–]|$)\s*[،,:\-–]?\s*"
)


# ---------------------------------------------------------------- neutral wording
# Owner rule (Oct 9 2026): wire-agency loaded terms become neutral, BBC/Reuters-style words.
# Longest phrases first; ZWNJ and space are both accepted inside a phrase.
NEUTRAL_TERMS = (
    ("ارتش اشغالگر رژیم صهیونیستی", "ارتش اسرائیل"),
    ("ارتش رژیم صهیونیستی", "ارتش اسرائیل"),
    ("رژیم اشغالگر قدس", "اسرائیل"),
    ("رژیم غاصب صهیونیستی", "اسرائیل"),
    ("رژیم صهیونیستی", "اسرائیل"),
    ("رژیم صهیونیست", "اسرائیل"),
    ("سخنگوی صهیونیست ها", "سخنگوی اسرائیل"),
    ("نظامیان صهیونیست", "نظامیان اسرائیلی"),
    ("نظامی صهیونیست", "نظامی اسرائیلی"),
    ("نظامی اشغالگر", "نظامی اسرائیلی"),
    ("نظامیان اشغالگر", "نظامیان اسرائیلی"),
    ("صهیونیست ها", "اسرائیلی‌ها"),
    ("صهیونیست‌ها", "اسرائیلی‌ها"),
    ("صهیونیستی", "اسرائیلی"),
    ("صهیونیست", "اسرائیلی"),
    ("به هلاکت رسیدند", "کشته شدند"),
    ("به هلاکت رسید", "کشته شد"),
    ("هلاک شدند", "کشته شدند"),
    ("هلاک شد", "کشته شد"),
    ("هلاکت", "کشته شدن"),
    # Oct 9: loaded war wording in the newsroom's own voice (BBC/Reuters style).
    ("ارتش متجاوز آمریکا", "ارتش آمریکا"),
    ("ارتش متجاوز", "ارتش"),
    ("متجاوزان آمریکایی", "نیروهای آمریکایی"),
    ("نظامیان متجاوز", "نظامیان"),
    ("تجاوز نظامی", "حمله نظامی"),
    ("تجاوز آمریکا", "حمله آمریکا"),
    ("تجاوز اسرائیل", "حمله اسرائیل"),
)


def _phrase_re(phrase):
    body = re.escape(phrase).replace(r"\ ", _S + "+").replace("\u200c", _S)
    return re.compile(r"(?<![\w\u0600-\u06FF])" + body + r"(?![\w\u0600-\u06FF])")


_NEUTRAL = [(_phrase_re(a), b) for a, b in NEUTRAL_TERMS]


def neutral(value):
    text = str(value or "")
    for pat, repl in _NEUTRAL:
        text = pat.sub(repl, text)
    return text


def strip_chrome(text, title=""):
    """Remove the page header (date/time, article code, section breadcrumb, repeated headline)
    from the start of an article body. Text that has no such header is returned unchanged."""
    raw = str(text or "")
    if not (CODE_RE.search(raw[:400]) or DATE_TIME_RE.search(raw[:400]) or PUBLISHED_RE.search(raw[:400])):
        return raw
    head, tail = raw[:400], raw[400:]
    head = CODE_RE.sub(" ", head)
    head = PUBLISHED_RE.sub(" ", head)
    head = DATE_TIME_RE.sub(" ", head)
    head = re.sub(r"\s{2,}", " ", head).lstrip(" ⚡️|-–—:،,")
    for _ in range(12):
        new = _SECTION_RE.sub("", head, count=1)
        if new == head:
            break
        head = new
    text = (head + tail).strip()
    # A page header was found, so whatever short run of words stands before the repeated
    # headline (rest of the breadcrumb «>> آمریکا», a sub-headline «خبرنگار ... دو مقام:») is
    # page chrome too. Cut it with the headline, only if a real lead (12+ words) remains.
    rx = _title_re(title)
    m = rx.search(text[:450]) if rx else None
    if m and m.start() > 0:
        prefix = text[:m.start()]
        if len(prefix.split()) <= 22 and not re.search(r"[.!؟]", prefix):
            rest = text[m.end():].lstrip(" .:،,-–—|")
            if len(rest.split()) >= 12:
                text = rest
    text = CRUMB_RE.sub("", text, count=1) if CRUMB_RE.match(text) and not text[:1].isalnum() else text
    t = re.sub(r"\s+", " ", str(title or "").replace("\u200c", " ")).strip()
    if len(t) >= 12:
        for _ in range(2):
            probe = text.replace("\u200c", " ")
            if probe.startswith(t):
                text = text[len(t):].lstrip(" .:،,-–—")
            else:
                break
    return text


def clean(value):
    text = str(value or "")
    text = text.replace("\u200f", " ")
    for _ in range(2):
        before = text
        text = GENERIC_SOURCE_RE.sub("", text, count=1)
        for prefix in KNOWN_PREFIXES:
            pat = re.escape(prefix).replace(r"\ ", _S + "+").replace("\u200c", _S)
            text = re.sub(r"^\s*" + pat + r"\s*[-–—:،]?\s*", "", text, flags=re.I)
        # After a recognized publisher, remove the reporter/desk credit ending
        # at a dash. Example: "باشگاه خبرنگاران جوان، اعظم پورکند - lead".
        if before != text and re.match(r"^\s*[^.!؟\n]{1,160}\s*[-–—]\s+", text):
            text = re.sub(r"^\s*[^.!؟\n]{1,160}\s*[-–—]\s+", "", text, count=1)
        if text == before:
            break
    text = ATTRIBUTION_RE.sub("", text, count=1)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


# ---------------------------------------------------------------- attribution inside the body
# Owner rule (Oct 9 2026): no media source anywhere in a post, not only at its start.
# Seen on Oct 9: «به گزارش خبرگزاری مهر نیویورک تایمز، آکادمی سوئد ...» in a detail line and
# «یک رسانه آمریکایی با اشاره به ...، ...» as a whole detail line. Officials and speakers
# («به گفته سپاه»، «ترامپ گفت») are never touched; only media outlets are.
_MEDIA = (
    r"(?:خبرگزاری|خبرنگار|رسانه|روزنامه|نشریه|پایگاه" + _S + r"+خبری|سایت" + _S + r"+خبری|وب" + _S + r"*سایت|"
    r"شبکه" + _S + r"+(?:خبری|تلویزیونی)|تلویزیون|صدا" + _S + r"*و" + _S + r"*سیما|ایسنا|ایرنا|تسنیم|ایلنا|برنا|"
    r"بلومبرگ|رویترز|الحدث|الجزیره|العربیه|المیادین|اکسیوس|آکسیوس|آسوشیتدپرس|یورونیوز|"
    r"سی" + _S + r"*ان" + _S + r"*ان|بی" + _S + r"*بی" + _S + r"*سی|فرانس" + _S + r"+پرس|"
    r"نیویورک" + _S + r"+تایمز|واشنگتن" + _S + r"+پست|وال" + _S + r"+استریت" + _S + r"+ژورنال|"
    r"فایننشال" + _S + r"+تایمز|تایمز" + _S + r"+اسرائیل|گاردین|اسکای" + _S + r"+نیوز|فاکس" + _S + r"+نیوز|"
    r"ان" + _S + r"*بی" + _S + r"*سی|سی" + _S + r"*بی" + _S + r"*اس|اکونومیست|پولیتیکو|اسپوتنیک|تاس)"
)
_VIA = r"(?:به" + _S + r"+گزارش|به" + _S + r"+نقل" + _S + r"+از)"
_LEAD_ATTR = re.compile(r"^\s*" + _VIA + r"\s*[^،,.!؟\n]{0,30}?" + _MEDIA + r"[^،,.!؟\n]{0,40}[،,]\s*")
_MID_ATTR = re.compile(r"[،,]\s*" + _VIA + r"\s*[^،,.!؟\n]{0,30}?" + _MEDIA + r"[^،,.!؟\n]{0,30}[،,]\s*")
_TAIL_ATTR = re.compile(r"[،,]?\s*" + _VIA + r"\s*[^،,.!؟\n]{0,30}?" + _MEDIA + r"[^،,.!؟\n]{0,30}(?=[.!؟]?\s*$)")
# «مهر» and «فارس» are also a month and a province: only right after «به گزارش».
_DIRECT_AGENCY = re.compile(r"(?:^|[،,])\s*" + _VIA + r"\s*(?:مهر|فارس)\s*[،,]\s*")
_MEDIA_SUBJECT = (r"^\s*(?:یک|چند|برخی)?\s*(?:" + _MEDIA + r")(?:" + _S + r"*(?:های|ها))?")
# «رویترز گزارش داد که ایران ...» -> «ایران ...»
_REPORTED_THAT = re.compile(_MEDIA_SUBJECT + r"[^،,.!؟\n]{0,40}?\s(?:گزارش" + _S + r"+داد|نوشت|"
                            r"گزارش" + _S + r"+کرد|مدعی" + _S + r"+شد|اعلام" + _S + r"+کرد)(?![\u0600-\u06FF])\s*(?:که\s+)?[،,]?\s*")
# What clean() leaves when it removed a leading outlet name: «رویترز گزارش داد که X» -> «گزارش داد که X».
_ORPHAN_VERB = re.compile(r"^\s*(?:گزارش" + _S + r"+داد|گزارش" + _S + r"+داده" + _S + r"+است|نوشت)(?![\u0600-\u06FF])\s*(?:که\s+)?[،,:]?\s*")
# A detail line is dropped only when an outlet is its subject AND it is a reporting line
# («یک رسانه آمریکایی با اشاره به ... زیر سوال برده است»). «خبرنگاران الجزیره کشته شدند» or
# «روزنامه‌نگاران تجمع کردند» are news, not attribution, and stay.
_MEDIA_SUBJECT_RE = re.compile(_MEDIA_SUBJECT + r"(?![\u0600-\u06FF])(?!" + _S + r"*نگار)")
_REPORTING = re.compile(r"(?<![\u0600-\u06FF])(?:گزارش" + _S + r"+(?:داد|داده|کرد)|نوشت|نوشته|مدعی" + _S + r"+شد|"
                        r"ادعا" + _S + r"+کرد|با" + _S + r"+اشاره" + _S + r"+به|به" + _S + r"+نقل" + _S + r"+از|"
                        r"افشا" + _S + r"+کرد|فاش" + _S + r"+کرد|زیر" + _S + r"+سوال|زیر" + _S + r"+سؤال|"
                        r"تحلیل" + _S + r"+کرد|مدعی" + _S + r"+است|می" + _S + r"*نویسد|می" + _S + r"*گوید)"
                        r"(?![\u0600-\u06FF])")


# ---------------------------------------------------------------- page chrome without a date
# Oct 10: «اخبار اجتماعی پلیس ۰ نفر <headline again> دادستان ...»: section breadcrumb + a like
# counter + the repeated headline, glued in front of the real lead (no date/code, so strip_chrome
# did not fire), and a "related story" teaser line «: دوباره جنگ می شود ؟» at the end.
def _title_re(title):
    words = [w for w in re.split(r"[\s\u200c]+", str(title or "").strip()) if w]
    if len(words) < 4:
        return None
    return re.compile((_S + r"+").join(re.escape(w) for w in words))


def strip_echo(text, title=""):
    """Cut a short junk prefix that ends with the repeated headline. A body that simply starts
    with the headline is left alone; the cut is kept only if a real lead remains."""
    raw = str(text or "")
    rx = _title_re(title)
    if not rx:
        return raw
    m = rx.search(raw[:400])
    if not m or m.start() == 0:
        return raw
    prefix = raw[:m.start()].strip()
    if not prefix or len(prefix.split()) > 12 or re.search(r"[.!؟]", prefix):
        return raw
    # Only page chrome: a counter/number or a section name, and no verb of a real sentence.
    looks_chrome = (bool(re.search(r"(?:^|\s)[0-9۰-۹]+\s*(?:نفر|بازدید|دیدگاه|نظر|لایک|پسند)(?:\s|$)", prefix))
                    or bool(_SECTION_RE.match(prefix)))
    if not looks_chrome or _VERBISH.search(prefix):
        return raw
    rest = raw[m.end():].lstrip(" .:،,-–—|/")
    return rest if len(rest.split()) >= 12 else raw


_VERBISH = re.compile(r"(?<![\u0600-\u06FF])(?:کرد|کردند|شد|شدند|گفت|است|اعلام|کند|کنند|می" + _S + r"*\S+|داد|دارد|بود|خواهد|افزود)(?![\u0600-\u06FF])")
_TEASER = re.compile(r"^\s*[:：؛،,\-–—|]")


def _split_sentences(text):
    return [p for p in re.split(r"(?<=[.!؟؛])\s+", str(text or "").strip()) if p.strip()]


# Oct 10: «باراک راوید، خبرنگار آکسیوس نوشت: دو مقام ... به من گفتند که ...» -> the reporter's
# name, desk and outlet go, and his «به من گفتند» becomes a plain «گفتند».
_JOURNALIST_LEAD = re.compile(
    r"(?:^|(?<=[.!؟:،]\s))\s*(?:[^\s،,.!؟:]+\s+){0,3}?[^\s،,.!؟:]+\s*[،,]\s*"
    r"(?:خبرنگار|روزنامه" + _S + r"*نگار|تحلیلگر|سردبیر|گزارشگر|ستون" + _S + r"*نویس)" + _S + r"+"
    r"(?:ارشد" + _S + r"+)?(?:سیاسی" + _S + r"+|نظامی" + _S + r"+|کاخ" + _S + r"+سفید" + _S + r"+)?[^،,.!؟:]{0,20}?"
    r"(?:" + _MEDIA + r")[^،,.!؟:]{0,25}?\s+(?:نوشت|گفت|گزارش" + _S + r"+داد|افزود|مدعی" + _S + r"+شد)"
    r"(?![\u0600-\u06FF])\s*(?:که\s+)?[:：،,]?\s*")
_TO_ME = re.compile(r"(?<![\u0600-\u06FF])به" + _S + r"+من" + _S + r"+(گفتند|گفت|گفته" + _S + r"*اند|اطلاع" + _S + r"+دادند)(?![\u0600-\u06FF])")


def strip_journalist(text):
    raw = str(text or "")
    out = _JOURNALIST_LEAD.sub(" ", raw)
    if out != raw:  # only the removed reporter's own «به من گفتند»
        out = _TO_ME.sub(r"\1", out, count=1)
    return re.sub(r"[ \t]{2,}", " ", out).strip()


def strip_media(text):
    """Remove media attributions from every sentence of a body. A detail sentence whose
    subject is a media outlet (it only says what some outlet wrote) is dropped; the lead is
    always kept so the post stays publishable."""
    out = []
    text = strip_journalist(text)
    for i, sentence in enumerate(_split_sentences(text)):
        s = _DIRECT_AGENCY.sub(" ", sentence)
        s = _LEAD_ATTR.sub("", s.strip(), count=1)
        s = _MID_ATTR.sub(" ", s)
        s = _TAIL_ATTR.sub("", s)
        rest = _ORPHAN_VERB.sub("", _REPORTED_THAT.sub("", s, count=1), count=1)
        if rest != s and len(rest.split()) >= 5:
            s = rest
        s = re.sub(r"[ \t]{2,}", " ", s).strip()
        if i > 0 and _TEASER.search(s):
            continue  # «: دوباره جنگ می شود ؟» is a link teaser, not a sentence
        if i > 0 and _MEDIA_SUBJECT_RE.search(s) and not s.lstrip().startswith("خبرنگار") and _REPORTING.search(s):
            continue
        if s:
            out.append(s)
    return " ".join(out) if out else str(text or "")


# ---------------------------------------------------------------- cut headlines + outlet leads
# Oct 11: a long Entekhab headline («ترامپ ...: ...وحشتناک است/ ... دارند/ ما با حوثی ها در ار») was
# cut at 180 characters in the middle of a word, the repeated headline was removed from the body
# with the same cut, so the post opened with «تباط هستیم/ ...». The detail lines still carried
# «پایگاه خبری تحلیلی انتخاب (Entekhab.ir) :» and «به گزارش انتخاب،», which no outlet list knew.
TITLE_MAX = 180
_SEG_END = re.compile(r"\s*[/؛|]\s*")
_DOMAIN = re.compile(r"\(?\b[A-Za-z0-9][A-Za-z0-9-]*\.(?:ir|com|net|org|info|news|co|tv|io)\b\)?", re.I)
_DOMAIN_LEAD = re.compile(r"^\s*[^:：\n]{0,60}?\(?\b[A-Za-z0-9][A-Za-z0-9-]*\.(?:ir|com|net|org|info|news|co|tv|io)\b\)?\s*[:：]\s*", re.I)
_SITE_LEAD = re.compile(r"^\s*(?:پایگاه|سایت|وب" + _S + r"*سایت)" + _S + r"+(?:خبری|اطلاع" + _S + r"*رسانی|تحلیلی)[^:：\n]{0,40}[:：]\s*")
# «به گزارش انتخاب،» (any outlet name, 1-3 words). Officials stay: «به گزارش وزارت بهداشت،» is a
# source of the fact itself, and «به نقل از ترامپ» marks a quote, so neither is touched.
_OFFICIAL = r"(?:وزارت|سازمان|ارتش|سپاه|پلیس|دولت|دادستان|ستاد|اداره|فرمانداری|استانداری|هلال|اورژانس|سخنگو|مرکز|نیروی|ناجا|قوه|مجلس|بانک)"
_ANY_VIA = re.compile(r"(?:^|(?<=[.!؟:]\s))\s*به" + _S + r"+گزارش" + _S + r"+(?!" + _OFFICIAL + r")(?:[^\s،,.!؟:]+" + _S + r"+){0,2}[^\s،,.!؟:]+\s*[،,]\s*")
_READ_ON = re.compile(r"در" + _S + r"+ادامه" + _S + r"+(?:می" + _S + r"*آید|می" + _S + r"*خوانید|آمده" + _S + r"+است|بخوانید)")


def smart_cut(title, limit=TITLE_MAX):
    """Shorten a long headline at a segment end («/»، «؛»), else at a word end; never mid-word."""
    t = re.sub(r"\s+", " ", str(title or "")).strip()
    if len(t) <= limit:
        return t
    head = t[:limit + 1]
    ends = [m.start() for m in _SEG_END.finditer(head) if m.start() >= 40]
    if ends:
        return head[:ends[-1]].strip(" /؛|،,:")
    return head.rsplit(" ", 1)[0].strip(" /؛|،,:")


def looks_cut(title):
    """A headline that some earlier step cut at the length limit (ends inside a list or word)."""
    t = str(title or "").strip()
    return len(t) >= TITLE_MAX - 8 and not re.search(r"[.!؟»)\]\"']$", t) and bool(_SEG_END.search(t))


def repair_cut(title, body):
    """Headline cut in the middle: keep its complete segments and drop the body's first sentence
    when it is the headline's leftover tail (it contains a «/» list, which a lead never does)."""
    if not looks_cut(title):
        return title, body
    ends = [m.start() for m in _SEG_END.finditer(title) if m.start() >= 40]
    new_title = title[:ends[-1]].strip(" /؛|،,:") if ends else title.rsplit(" ", 1)[0]
    sents = _split_sentences(body)
    if sents and "/" in sents[0][:160] and len(" ".join(sents[1:]).split()) >= 12:
        body = " ".join(sents[1:])
    return new_title, body


def _words(s):
    return {w for w in re.split(r"[\s\u200c،,.!؟:؛]+", str(s or "")) if len(w) > 1}


def strip_outlet_leads(text):
    """Per sentence: «X (Site.ir) :»، «پایگاه خبری ... :» and any «به گزارش X،» go; «در ادامه
    می آید» teasers and near-copies of an earlier sentence are dropped (the lead always stays)."""
    out = []
    for i, sentence in enumerate(_split_sentences(text)):
        s = _DOMAIN_LEAD.sub("", sentence, count=1)
        s = _SITE_LEAD.sub("", s, count=1)
        s = _ANY_VIA.sub(" ", s)
        s = _DOMAIN.sub(" ", s)
        s = re.sub(r"[ \t]{2,}", " ", s).strip(" :،,")
        if not s:
            continue
        if i > 0 and _READ_ON.search(s):
            continue
        w = _words(s)
        if out and w and any(len(w & _words(o)) >= 0.8 * len(w) for o in out):
            continue  # the same sentence again (the lead repeated after a site header)
        out.append(s)
    return " ".join(out) if out else str(text or "")


# ---------------------------------------------------------------- page widgets + off-topic lines
# Oct 11: «⚡️ ۰ ۰ شما قبلا این خبر را لایک کرده اید .» as the lead, two "related news" links
# («ماجرای واریز سود سهام عدالت ...»، «از جنجال آفرینی تازه میرسلیم ...») as details, and
# «کپی شد پ ، پـ» (the copy button and the font-size buttons) glued to the real sentence.
# Root cause: the article extractor keeps the page's buttons, counters and related-story links.
# Two rules, for every site: widget text is cut out, and a line that has nothing to do with the
# headline is not part of the story.
_WIDGET = re.compile(
    r"(?:شما" + _S + r"+قبلا[^.!؟\n]{0,40}?(?:لایک|پسندیده|ذخیره)[^.!؟\n]{0,20}?(?:اید|اید" + _S + r"*\.)|"
    r"(?:لینک" + _S + r"+)?کپی" + _S + r"+(?:شد|لینک|کردن)|لینک" + _S + r"+کوتاه|"
    r"(?<![\u0600-\u06FF])پ" + _S + r"*[،,]?" + _S + r"*پـ(?![\u0600-\u06FF])|"
    r"اشتراک" + _S + r"*گذاری|بیشتر" + _S + r"+بخوانید|(?:اخبار|مطالب|خبرهای)" + _S + r"+مرتبط|"
    r"ارسال" + _S + r"+(?:نظر|دیدگاه)|تعداد" + _S + r"+(?:بازدید|نظرات)|برچسب" + _S + r"*(?:ها)?" + _S + r"*[:：]|"
    r"پربازدید" + _S + r"*ترین" + _S + r"*ها?|نسخه" + _S + r"+چاپی|دانلود" + _S + r"+(?:فیلم|عکس)|"
    r"^\s*(?:[0-9۰-۹]+" + _S + r"+){2,}(?=[\u0600-\u06FF]))")  # «۰ ۰ شما ...» like/comment counters
_STOP = set("در به از که و را با این آن برای درباره تا یک هم می شد کرد است ما او خود ها های گفت اعلام "
            "کرده شده باید بود خواهد خواهیم نیز اما یا بر پس روی وی آنها ایشان چه چرا کند کنند".split())


def _keys(text):
    out = set()
    for w in re.split(r"[\s\u200c،,.!؟:؛«»\"'()\[\]/|\-–—]+", str(text or "").replace("ي", "ی").replace("ك", "ک")):
        if len(w) < 3 or w in _STOP or w.isdigit():
            continue
        out.add(w[:4] if len(w) >= 5 else w)
    return out


def strip_widgets(text):
    """Cut page buttons/counters out of every sentence; drop what is left if it is a scrap."""
    out = []
    for sentence in _split_sentences(text):
        s = _WIDGET.sub(" ", sentence)
        s = re.sub(r"[ \t]{2,}", " ", s).strip(" .:،,⚡️")
        if len(s.split()) >= 4:
            out.append(s if re.search(r"[.!؟؛»]$", s) else s + ("." if sentence.rstrip().endswith(".") else ""))
    return " ".join(out)


def on_topic(title, text):
    """Keep the lines that belong to the headline's story. The lead must share at least two
    words with the headline; a detail line at least one with the headline or the lead.
    Returns "" when no lead belongs to the headline (the post is then not published)."""
    tk = _keys(title)
    if len(tk) < 3:
        return text
    out, lead_k = [], set()
    for s in _split_sentences(text):
        k = _keys(s)
        if not out:
            if len(k & tk) >= 2:
                out.append(s)
                lead_k = k
            continue
        if k & (tk | lead_k):
            out.append(s)
    return " ".join(out)


def install(core):
    for name in ("build_caption",):
        original = getattr(core, name, None)
        if not callable(original):
            continue
        def wrapped(title, body, _original=original):
            t = clean(title)
            t, body = repair_cut(t, body)
            b = strip_outlet_leads(strip_media(strip_echo(clean(strip_chrome(body, t)), t)))
            b = on_topic(t, strip_widgets(b))
            return _original(neutral(t), neutral(b))
        setattr(core, name, wrapped)
    # The formatter cut every headline at 180 characters, even in the middle of a word.
    try:
        import v13_editorial_formatter as ef
        if not getattr(ef.format_title, "_smart", False):
            plain = ef.format_title

            def format_title(title, _plain=plain):
                value = _plain(smart_cut(ef._clean(title)) if len(ef._clean(title)) > TITLE_MAX else title)
                return value
            format_title._smart = True
            ef.format_title = format_title
    except Exception as exc:
        print(f"V13 BYLINE CLEANER: smart title cut not installed ({type(exc).__name__})", flush=True)
    # Last line of defence after all cleanup: refuse a post that still breaks an owner rule.
    try:
        import v13_final_guard
        v13_final_guard.install()
    except Exception as exc:
        print(f"V13 FINAL GUARD: not installed ({type(exc).__name__}: {exc})", flush=True)
    print("V13 BYLINE CLEANER ACTIVE: publisher lead-ins and page headers removed, neutral wording on, media attribution stripped in every sentence.")
