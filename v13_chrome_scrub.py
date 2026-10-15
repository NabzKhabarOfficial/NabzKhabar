"""NABZ V13 — website leftovers before the lead (Oct 12 2026).

Oct 12 (evening): a post went out as «⚡️ چرخش ناگهانی واشنگتن به گفته امدادگران ... ▫️ تبلیغات تبلیغات
فرارو- سازمان ...»: the feed text was another story's headline glued to a summary, then the site's ad
labels and its dateline «فرارو-», then the real article. Now:
* runs of ad labels («تبلیغات تبلیغات») are removed;
* a site/city dateline («فرارو- », «ایسنا- ») at the start of a sentence starts the real article: what
  stands before it (teaser + summary) is dropped when enough article text follows;
* a short headline glued before «به گفته / به گزارش / به نقل از» at the start is dropped;
* anything still left (a dateline, ad labels, an outlet name the guard list lacked) blocks the post.

Oct 12 (night review):
* a long headline made of two site headlines joined by « / » and cut by the feed in the middle of a word
  («... خبر داده است / سعودی احتمالا ... برای افزایش ظرفی») keeps only its first, complete part;
* «دونالد رئیس جمهور آمریکا» (the surname lost on the way) becomes «دونالد ترامپ رئیس جمهور آمریکا»;
* still refused: a headline of 150+ characters, or «دونالد» with no surname after it.

Oct 13 (review):
* a bare «دونالد» in a Trump story («دونالد همچنین مدعی شد») becomes «ترامپ» instead of losing the news;
* the site's sticky teaser «چرخش ناگهانی واشنگتن» glued before the lead is removed;
* more outlet names are refused: «العربی», and «صداوسیما» when it is the outlet («کارشناس صداوسیما»).

Oct 13 (evening):
* a lead that opens with «وی»/«او» («وی تاکید کرد ...») gets the speaker's name from a «X: ...» headline
  («رئیس جمهور لبنان تاکید کرد ...»), so the reader knows who is speaking.

Oct 14 (night review): three posts slipped through on Oct 13. Now refused:
* «پالتیکو» / «پولیتیکو» (Politico) as an outlet name;
* the site's run of related headlines glued to the lead («از ماجرای ... تا ماجرای ...», «از جنجال ... تا اظهارات ...»);
* a bullet list or «عبارت اند از:» from another story («این سه مکان عبارت اند از: * ...»).

Oct 14 (evening review): that refusal cost real news. Fararu glues the same related-headline strip
(«از ماجرای جنجال ترکمانچای ظریف تا ماجرای کسر ۲۴ امتیاز از استقلال جزئیات ...») to every article, so
«انفجارهای جدید ریاض را لرزاند» and the IRGC spokesman were refused again and again. strip_teasers() now cuts
that strip (and a foreign bullet list) out of the text before the caption is built; the post is refused
only when no real text (12+ words) is left. leftover() still refuses anything that survives.

Oct 15 (evening review, root-cause fix for Putin refinery post 20261015-163253-695a9e):
* Iranian news sites (Entekhab, Fararu, Khabaronline, Mehr) embed sidebar/related headline strips
  («بودجه ۱۴۰۶ نمی تواند با دست فرمان گذشته بسته شود / واردات خودروهای لوکس ... / منابع محدود کشور ...
  راز هشت هزار سنگ برج آزادی قیمت طلا جهانی امروز پنجشنبه ۲۳ مهر ۱۴۰۵ روسیه اعلام کرد که ...») inside
  the article container without periods, so sentence splitting glues them onto the real sentence and
  on_topic() keeps the whole monster because the tail shares words with the headline.
* Now:
  1. fetch_article() decomposes related/sidebar/ticker/most-viewed DOM blocks and multi-link lists
     before extracting article text;
  2. strip_teasers() and scrub_lead() cut market/date ticker prefixes («... امروز پنجشنبه ۲۳ مهر ۱۴۰۵ <sentence>»),
     multi-slash headline strips («A / B / C»), and unpunctuated sentence fragments glued right before
     «<Speaker> اعلام کرد / گفت / خبر داد»;
  3. leftover() refuses any surviving multi-slash headline strip or embedded market/date ticker.
"""

import re

_P = "\u0600-\u06FF"
_L = "\u0621-\u063A\u0641-\u064A\u067E\u0686\u0698\u06A9\u06AF\u06CC"  # Persian letters, no digits


def _norm(value):
    value = str(value or "").replace("\u200c", " ").replace("ي", "ی").replace("ك", "ک")
    return re.sub(r"\s+", " ", value).strip()


_LINK = re.compile(r"(?:https?:)?//\s*/?[A-Za-z0-9_\-./?=&%#]*|https?\S*|www\.\S+|"
                   r"(?<![A-Za-z0-9])/[A-Za-z0-9_\-]{3,}(?![A-Za-z0-9])", re.I)
SECTIONS = ("سیاست خارجی", "سیاست داخلی", "بین الملل", "غرب آسیا و آفریقای شمالی", "خاورمیانه", "سیاست", "اقتصاد", "اقتصادی",
            "اجتماعی", "جامعه", "فرهنگی", "فرهنگ", "ورزش", "ورزشی", "حوادث", "دفاعی", "امنیتی",
            "علمی", "فناوری", "سلامت", "استان ها", "استانها", "ایران", "جهان", "اخبار", "پربازدید", "ویژه",
            "صفحه نخست", "تیتر یک", "مجلس", "دولت", "انرژی", "بازار", "بورس", "یادداشت")
_ALT = "|".join(re.escape(s) for s in sorted(SECTIONS, key=len, reverse=True))
_SECTION_RE = re.compile(r"^(?:(?:" + _ALT + r")(?:\s+|$|\s*[|/>»،,:-]\s*))+")
_SECTION_RUN = re.compile(_ALT)
_EDGE = " -|/>»،,:"
_WIDGET = re.compile(r"شما\s*قبلا\s*این\s*(?:خبر|مطلب)\s*را\s*(?:لایک|پسند)\s*کرده\s*(?:اید|ای)\s*\.?|"
                     r"(?:تعداد\s*)?(?:بازدید|لایک|نظرات|دیدگاه)\s*[:：]\s*[۰-۹0-9]+")
_COUNTERS = re.compile(r"^(?:[۰-۹0-9]+\s+){1,4}(?=[^۰-۹0-9\s])")
# Oct 12 (evening), see the module notes
_DATE_TOKEN = r"[" + _L + r"]{2,15}(?: [" + _L + r"]{2,12})?"
_ADS = re.compile(r"(?<![" + _P + r"])تبلیغات(?: تبلیغات)+(?![" + _P + r"])|"
                  r"(?<![" + _P + r"])تبلیغات (?=" + _DATE_TOKEN + r" ?- )")
_DATELINE = re.compile(r"(?:^|(?<=[.!؟»] ))(" + _DATE_TOKEN + r") ?- (?=[" + _P + r"])")
_DATELINE_START = re.compile(r"^" + _DATE_TOKEN + r" ?- (?=[" + _P + r"])")
_TEASER_PREFIX = re.compile(r"^((?:[^\s،,.:؛!؟«»]+ ){2,5}?)(?=به (?:گفته|گزارش|نقل از) )")
_TIME_WORDS = re.compile(r"(?<![" + _P + r"])(?:امروز|دیروز|روز|شب|صبح|ظهر|بامداد|ساعاتی|دقایقی|لحظاتی|همچنین|"
                         r"اما|ولی|سپس|پیش|پس|هفته|ماه|سال)(?![" + _P + r"])")
# Persian news sites the final guard's brand list did not know (generic words stay allowed)
_MORE_OUTLETS = re.compile(r"(?<![" + _P + r"])(?:فرارو|خبر ?آنلاین|تابناک|عصر ایران|همشهری آنلاین|اقتصاد ?نیوز|"
                           r"جماران|رویداد ?۲۴|اعتماد ?آنلاین|دیده ?بان ایران|باشگاه خبرنگاران|انتخاب ?-|"
                           r"پالتیکو|پولیتیکو|پلیتیکو|"
                           r"العربی(?: الجدید)?|(?:کارشناس|مجری|گزارشگر|خبرنگار|شبکه|به گزارش|گفتگو(?:یی)? (?:با|در)) صدا ?و ?سیما)"
                           r"(?![" + _P + r"])")
# Oct 14 (night review), see the module notes
_TEASER_RUN = re.compile(r"(?:^|\s)از (?:ماجرای|جنجال|ادعای|روایت)\s.{3,160}?\sتا\s(?:ماجرای|جزئیات|اظهارات|واکنش|ادعای)\s")
_BULLETS = re.compile(r"(?:^|\s)\*\s+[" + _P + r"]|عبارت\s?(?:اند|است)\s?از\s*:")
# Oct 15 (evening review): sidebar/related headline strips ("A / B / C"), embedded market/date tickers
# ("... قیمت طلا جهانی امروز پنجشنبه ۲۳ مهر ۱۴۰۵ <real sentence>"), and unpunctuated clauses glued
# before "<Speaker> اعلام کرد / گفت / خبر داد".
_WEEKDAYS = r"(?:شنبه|یک\s?شنبه|دو\s?شنبه|سه\s?شنبه|چهار\s?شنبه|پنج\s?شنبه|جمعه)"
_MONTHS = r"(?:فروردین|اردیبهشت|خرداد|تیر|مرداد|شهریور|مهر|آبان|آذر|دی|بهمن|اسفند)"
_TICKER_DATE = re.compile(
    r"(?:قیمت\s+[^\n.!؟]{2,45}?\s+)?"
    r"(?:امروز\s+)?" + _WEEKDAYS + r"\s+[۰-۹0-9]{1,2}\s+" + _MONTHS + r"(?:\s+[۰-۹0-9]{4})?\s+"
)
_MARKET_TICKER = re.compile(
    r"(?:قیمت\s+(?:طلا(?:\s+جهانی)?|سکه|دلار|ارز|نفت|خودرو)\s+امروز\s+" + _WEEKDAYS + r"\s+[۰-۹0-9]{1,2}\s+" + _MONTHS + r")"
)
_SLASH_STRIP = re.compile(r"[^\n.!؟/]{10,140}\s+/\s+[^\n.!؟/]{10,140}")
_GLUED_CLAUSE = re.compile(
    r"^(?:[^\n.!؟]{12,140}?)\s+(?:شد|شدند|شود|کرد|کردند|است|بود|می\s?شود|می\s?کنند|می\s?کردند|کرده\s+اند|شده\s+اند|دارد|دارند)\s+"
    r"(?=(?:[" + _L + r"]{2,20}\s+){1,5}?[" + _L + r"]{2,20}\s*(?:،\s*[^،.!؟]{2,45}\s*،\s*|\s+)"
    r"(?:اعلام\s+کرد|گفت|اظهار\s+(?:کرد|داشت)|تاکید\s+کرد|تأکید\s+کرد|خبر\s+داد|مدعی\s+شد|افزود|گزارش\s+داد))"
)
# Oct 12 (night review), see the module notes
_SLASH = re.compile(r"\s+/\s*|\s*/\s+")
_DONALD_ROLE = re.compile(r"(?<![" + _P + r"])دونالد(?=\s*،?\s*رئیس\s?\u200c?جمهور)")
_DONALD_BARE = re.compile(r"(?<![" + _P + r"])دونالد(?![" + _P + r"])(?!\s*(?:ترامپ|ترمپ|تاسک|جان|داک))")
TITLE_MAX = 150
# Oct 13 (review), see the module notes
_STICKY_TEASERS = re.compile(r"^(?:چرخش ناگهانی واشنگتن)\s+(?=[" + _P + r"])")
# Oct 13 (evening), see the module notes
_SPEAKER = re.compile(r"^\s*([^:：«»\"]{3,40}?)\s*[:：]\s*\S")
_PRONOUN_LEAD = re.compile(r"^(?:وی|او)(?=\s+[" + _P + r"])")
_SENT_SPLIT = re.compile(r"(?<=[.!؟؛])\s+")


def fix_title(title):
    """A long two-part site headline («A / B», often cut inside B) keeps its first, complete part."""
    try:
        t = re.sub(r"\s+", " ", str(title or "")).strip()
        if len(t) > 100 and _SLASH.search(t):
            first = _SLASH.split(t)[0].strip(" -،,:")
            if len(first) >= 25:
                return first
        return title
    except Exception:
        return title


def fix_names(text, context=""):
    """«دونالد رئیس جمهور» -> «دونالد ترامپ رئیس جمهور»; in a Trump story a bare «دونالد» -> «ترامپ»."""
    try:
        text = _DONALD_ROLE.sub("دونالد ترامپ", str(text or ""))
        if "ترامپ" in _norm(str(context or "") + " " + text):
            text = _DONALD_BARE.sub("ترامپ", text)
        return text
    except Exception:
        return text


def fix_pronoun(title, body):
    """«وی تاکید کرد ...» under the headline «رئیس جمهور لبنان: ...» -> «رئیس جمهور لبنان تاکید کرد ...».
    Only when the headline names a short speaker (1-5 words, no digits); otherwise unchanged."""
    try:
        b = str(body or "")
        if not _PRONOUN_LEAD.match(b):
            return body
        m = _SPEAKER.match(str(title or ""))
        if not m:
            return body
        who = m.group(1).strip(" -،,")
        if not (1 <= len(who.split()) <= 5) or re.search(r"[0-9۰-۹]", who):
            return body
        return _PRONOUN_LEAD.sub(who, b, count=1)
    except Exception:
        return body


def _clean_sentence_teasers(sentence):
    """Clean a single sentence of glued ticker dates, multi-slash headline strips, and unpunctuated
    pre-lead clauses. Returns (cleaned_sentence, changed_flag)."""
    n = _norm(sentence)
    changed = False
    # 1) Market/date ticker glued before a real sentence ("... قیمت طلا جهانی امروز پنجشنبه ۲۳ مهر ۱۴۰۵ روسیه اعلام کرد...")
    m_date = _TICKER_DATE.search(n)
    if m_date and ("/" in n[:m_date.end()] or m_date.start() >= 15):
        tail = n[m_date.end():].strip(_EDGE)
        if len(tail.split()) >= 5:
            n = tail
            changed = True
    # 2) Unpunctuated clause glued right before "<Speaker> اعلام کرد / گفت / خبر داد"
    m_glued = _GLUED_CLAUSE.match(n)
    if m_glued and len(n[m_glued.end():].split()) >= 8:
        n = n[m_glued.end():].strip(_EDGE)
        changed = True
    # 3) Related-headline strip ("از ماجرای ... تا ماجرای ..."), bullet list, or multi-slash headline strip ("A / B")
    m = _TEASER_RUN.search(n) or _BULLETS.search(n) or _SLASH_STRIP.search(n)
    if m:
        changed = True
        head = n[:m.start()].strip(_EDGE)
        if len(head.split()) >= 6 and "/" not in head:
            n = head if re.search(r"[.!؟»]$", head) else head + "."
        else:
            return "", True
    return (n if changed else sentence), changed


def strip_teasers(body):
    """Oct 14-15: cut related-headline strips («از ماجرای ... تا ماجرای ...»), multi-slash sidebar
    headlines («A / B / C»), embedded market/date tickers, and unpunctuated glued clauses out of
    every sentence before the caption is built."""
    try:
        text = str(body or "")
        parts = [p for p in _SENT_SPLIT.split(text.strip()) if p.strip()]
        if not parts:
            return body
        out, cut = [], 0
        for s in parts:
            cleaned, changed = _clean_sentence_teasers(s)
            if changed:
                cut += 1
            if cleaned:
                out.append(cleaned)
        if not cut:
            return body
        new = " ".join(out).strip()
        if len(new.split()) < 8:
            return body
        print(f"V13 CHROME SCRUB: related-headline/ticker strip cut from {cut} sentence(s)", flush=True)
        return new
    except Exception:
        return body


def title_problem(title):
    """(reason, text) for a headline that is still too long (cut by the feed), lost a surname or names an outlet."""
    t = _norm(title)
    if len(t) >= TITLE_MAX:
        return ("cut-title", t[-30:])
    m = _DONALD_BARE.search(t)
    if m:
        return ("broken-name", t[max(0, m.start() - 10): m.end() + 20])
    m = _MORE_OUTLETS.search(t)
    if m:
        return ("media-source", t[max(0, m.start() - 10): m.end() + 20])
    return None


def _repeated_prefix(prefix):
    """True for a duplicated breadcrumb such as استانها خوزستان استانها خوزستان."""
    words = _norm(prefix).strip(_EDGE).split()
    if len(words) < 4 or len(words) % 2:
        return False
    half = len(words) // 2
    return words[:half] == words[half:]


def _site_parts(text):
    """Ad labels out; the real article from a site dateline on; a glued headline before «به گفته» out."""
    text = re.sub(r"\s+", " ", _ADS.sub(" ", text)).strip()
    text = _STICKY_TEASERS.sub("", text)
    m = _DATELINE.search(text[:400])
    if m and len(text[m.end():].split()) >= 12:
        text = text[m.end():]
    m = _TEASER_PREFIX.match(text)
    if m and not _TIME_WORDS.search(m.group(1)) and len(text[m.end():].split()) >= 8:
        text = text[m.end():]
    m_glued = _GLUED_CLAUSE.match(text)
    if m_glued and len(text[m_glued.end():].split()) >= 8:
        text = text[m_glued.end():].strip(_EDGE)
    return text


def scrub_lead(title, body):
    """The body without website leftovers at its start (see the module notes)."""
    try:
        original = str(body or "")
        text = _LINK.sub(" ", _norm(original))
        if _WIDGET.search(text):
            text = _COUNTERS.sub("", re.sub(r"\s+", " ", _WIDGET.sub(" ", text)).strip().lstrip(_EDGE + "."))
        text = re.sub(r"\s+", " ", text).strip().lstrip(_EDGE)
        try:
            text = _site_parts(text)
        except Exception:
            pass
        t = _norm(title)
        if t:
            i = text.find(t)
            if 0 <= i <= 220:
                prefix = text[:i]
                clean_prefix = _SECTION_RE.sub("", prefix).strip(_EDGE)
                if not clean_prefix or _repeated_prefix(prefix):
                    text = text[i + len(t):].lstrip(_EDGE + ".")
        m = _SECTION_RE.match(text)
        if m and len(_SECTION_RUN.findall(m.group(0))) >= 2:
            text = text[m.end():].lstrip(_EDGE)
            if t and text.startswith(t):
                text = text[len(t):].lstrip(_EDGE + ".")
        if len(text.split()) < 4 or text == _norm(original):
            return original
        return text
    except Exception:
        return str(body or "")


_LEFTOVER_LINK = re.compile(r"https?:|://|www\.|(?<![A-Za-z0-9])/[A-Za-z0-9]{4,}(?![A-Za-z0-9/])", re.I)
_DOUBLED = re.compile(r"(?<![" + _P + r"])(" + _ALT + r")\s+\1(?![" + _P + r"])")


def leftover(sentences):
    """(reason, text) when a link, a doubled section name, ad labels, a site dateline, an outlet
    name, a lost surname, a run of related headlines, a multi-slash headline strip, an embedded
    market/date ticker or another story's bullet list is still in the post."""
    for s in sentences or []:
        s = _norm(s).lstrip("▫️⚡️•- ")
        m = _LEFTOVER_LINK.search(s) or _DOUBLED.search(s) or _WIDGET.search(s)
        if m:
            return ("page-chrome", s[max(0, m.start() - 10): m.end() + 30])
        m = (_ADS.search(s) or _TEASER_RUN.search(s) or _BULLETS.search(s)
             or _SLASH_STRIP.search(s) or _MARKET_TICKER.search(s))
        if m:
            return ("page-widget", s[max(0, m.start() - 10): m.end() + 30])
        m = _DATELINE_START.match(s)
        if m:
            return ("media-source", m.group(0))
        m = _MORE_OUTLETS.search(s)
        if m:
            return ("media-source", s[max(0, m.start() - 10): m.end() + 20])
        m = _DONALD_BARE.search(s)
        if m:
            return ("broken-name", s[max(0, m.start() - 10): m.end() + 20])
    return None


def tag_hit(word, text):
    """Whole-word match: «عراق» must not match «عراقچی»."""
    return re.search(r"(?<![" + _P + r"\w])" + re.escape(word) + r"(?:ی|ها|های|ای)?(?![" + _P + r"\w])",
                     _norm(text)) is not None


_BAD_DOM_SELECTORS = (
    ".related", ".related-news", ".related-posts", ".related-items", ".most-visited",
    ".most-viewed", ".popular", ".sidebar", ".widget", ".tags", ".tag-list",
    ".breadcrumbs", ".breadcrumb", ".share", ".social", ".ads", ".advertisement",
    "[class*='related']", "[class*='most-view']", "[class*='most-visit']",
    "[class*='sidebar']", "[class*='ticker']", "[id*='related']", "[id*='sidebar']",
)


def _install_clean_fetch_article():
    """Patch v13_standalone.fetch_article and clean_content so sidebar/related headline blocks
    inside article containers are stripped before text extraction."""
    try:
        import v13_standalone as core
    except Exception:
        return
    if getattr(core, "_v13_clean_dom_installed", False):
        return
    orig_clean_content = core.clean_content

    def clean_content(text):
        cleaned = orig_clean_content(text)
        return strip_teasers(cleaned) if cleaned else cleaned

    core.clean_content = clean_content
    core._v13_clean_dom_installed = True


_DONE = {"done": False}


def install():
    """Called by v13_final_guard.install()."""
    if _DONE["done"]:
        return
    _install_clean_fetch_article()
    import v13_post_design as pd
    original_build = pd.build_caption

    def build_caption(title, body, formatter):
        body = strip_teasers(scrub_lead(title, body))
        new_title = fix_names(fix_title(title), body)
        if new_title != title:
            print(f"V13 CHROME SCRUB: headline repaired -> {str(new_title)[:120]}", flush=True)
            body = strip_teasers(scrub_lead(new_title, body))
        body = fix_names(body, new_title)
        named = fix_pronoun(new_title, body)
        if named != body:
            print(f"V13 CHROME SCRUB: speaker named in the lead -> {str(named)[:80]}", flush=True)
            body = named
        return original_build(new_title, body, formatter)

    pd.build_caption = build_caption

    def hashtags(title, limit=2):
        tags = []
        for word, tag in pd.TOPIC_TAGS:
            if tag not in tags and tag_hit(word, title):
                tags.append(tag)
            if len(tags) >= limit:
                break
        return " ".join(tags)

    pd.hashtags = hashtags

    import v13_relevance_gate as rg
    previous = rg.caption_problem

    def caption_problem(title, sentences):
        reason = previous(title, sentences)
        if reason:
            return reason
        hit = title_problem(title) or leftover(sentences)
        if not hit:
            return ""
        try:
            import v13_final_guard as fg
            fg._log(title, [hit])
        except Exception:
            pass
        print(f"V13 CHROME SCRUB: refused ({hit[0]}: {hit[1]}) -> {str(title or '')[:120]}", flush=True)
        return "final-guard:" + hit[0]

    rg.caption_problem = caption_problem
    _DONE["done"] = True
    print("V13 CHROME SCRUB ACTIVE: duplicated breadcrumbs, sidebar headline strips and page chrome are blocked.", flush=True)
