"""NABZ V13 — website leftovers before the lead (Oct 12 2026).

Owner report: a post went out as «⚡️ https:// /x3dj3P سیاست سیاست خارجی سیاست سیاست خارجی
<the headline again> وزیر امور خارجه ...» with the tag #عراق on a story about «عراقچی».
The source page's short link, its section breadcrumb and the headline were glued before the
real lead, and the topic tags matched part of a word.

* scrub_lead(title, body): removes links, a section breadcrumb (two or more section names in a
  row, or section names right before the repeated headline) and the repeated headline from the
  START of the text. A lone real word such as «ایران» or «دولت» at the start is kept.
* leftover(sentences): the last check for v13_final_guard; a link, a doubled section name or a
  like/view counter widget («شما قبلا این خبر را لایک کرده اید») still there blocks the post.
* tag_hit(word, text): whole-word match for topic tags («عراق» never matches «عراقچی»).
Fail-safe: any doubt returns the text unchanged.
"""

import re

_P = "\u0600-\u06FF"


def _norm(value):
    value = str(value or "").replace("\u200c", " ").replace("ي", "ی").replace("ك", "ک")
    return re.sub(r"\s+", " ", value).strip()


_LINK = re.compile(r"(?:https?:)?//\s*/?[A-Za-z0-9_\-./?=&%#]*|https?\S*|www\.\S+|"
                   r"(?<![A-Za-z0-9])/[A-Za-z0-9_\-]{3,}(?![A-Za-z0-9])", re.I)
SECTIONS = ("سیاست خارجی", "سیاست داخلی", "بین الملل", "خاورمیانه", "سیاست", "اقتصاد", "اقتصادی",
            "اجتماعی", "جامعه", "فرهنگی", "فرهنگ", "ورزش", "ورزشی", "حوادث", "دفاعی", "امنیتی",
            "علمی", "فناوری", "سلامت", "استان ها", "ایران", "جهان", "اخبار", "پربازدید", "ویژه",
            "صفحه نخست", "تیتر یک", "مجلس", "دولت", "انرژی", "بازار", "بورس", "یادداشت")
_ALT = "|".join(re.escape(s) for s in sorted(SECTIONS, key=len, reverse=True))
_SECTION_RE = re.compile(r"^(?:(?:" + _ALT + r")(?:\s+|$|\s*[|/>»،,:-]\s*))+")
_SECTION_RUN = re.compile(_ALT)
_EDGE = " -|/>»،,:"
# Oct 12 (feed review): «۰ ۰ شما قبلا این خبر را لایک کرده اید .» went out as the whole lead.
_WIDGET = re.compile(r"شما\s*قبلا\s*این\s*(?:خبر|مطلب)\s*را\s*(?:لایک|پسند)\s*کرده\s*(?:اید|ای)\s*\.?|"
                     r"(?:تعداد\s*)?(?:بازدید|لایک|نظرات|دیدگاه)\s*[:：]\s*[۰-۹0-9]+")
_COUNTERS = re.compile(r"^(?:[۰-۹0-9]+\s+){1,4}(?=[^۰-۹0-9\s])")


def scrub_lead(title, body):
    """The body without website leftovers at its start (see the module notes)."""
    try:
        original = str(body or "")
        text = _LINK.sub(" ", _norm(original))
        if _WIDGET.search(text):  # the like/view counters («۰ ۰») go only together with the widget
            text = _COUNTERS.sub("", re.sub(r"\s+", " ", _WIDGET.sub(" ", text)).strip().lstrip(_EDGE + "."))
        text = re.sub(r"\s+", " ", text).strip().lstrip(_EDGE)
        t = _norm(title)
        if t:
            i = text.find(t)
            if 0 <= i <= 120 and _SECTION_RE.sub("", text[:i]).strip(_EDGE) == "":
                text = text[i + len(t):].lstrip(_EDGE + ".")
        m = _SECTION_RE.match(text)
        if m and len(_SECTION_RUN.findall(m.group(0))) >= 2:  # a breadcrumb, not one real word
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
    """(reason, text) when a link or a doubled section name is still in the post, else None."""
    for s in sentences or []:
        s = _norm(s)
        m = _LEFTOVER_LINK.search(s) or _DOUBLED.search(s) or _WIDGET.search(s)
        if m:
            return ("page-chrome", s[max(0, m.start() - 10): m.end() + 30])
    return None


def tag_hit(word, text):
    """Whole-word match: «عراق» must not match «عراقچی»."""
    return re.search(r"(?<![" + _P + r"\w])" + re.escape(word) + r"(?:ی|ها|های|ای)?(?![" + _P + r"\w])",
                     _norm(text)) is not None


_DONE = {"done": False}


def install():
    """Called by v13_final_guard.install(). Cleans the body before v13_post_design builds the
    caption, makes its topic tags whole-word, and adds the leftover check as the last guard."""
    if _DONE["done"]:
        return
    import v13_post_design as pd
    original_build = pd.build_caption

    def build_caption(title, body, formatter):
        return original_build(title, scrub_lead(title, body), formatter)

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
        hit = leftover(sentences)
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
    print("V13 CHROME SCRUB ACTIVE: no link, section breadcrumb or repeated headline before the lead.", flush=True)
