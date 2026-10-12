"""NABZ V13 — website leftovers before the lead (Oct 12 2026)."""

import re

_P = "\u0600-\u06FF"


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


def _repeated_prefix(prefix):
    """True for a duplicated breadcrumb such as استانها خوزستان استانها خوزستان."""
    words = _norm(prefix).strip(_EDGE).split()
    if len(words) < 4 or len(words) % 2:
        return False
    half = len(words) // 2
    return words[:half] == words[half:]


def scrub_lead(title, body):
    """The body without website leftovers at its start (see the module notes)."""
    try:
        original = str(body or "")
        text = _LINK.sub(" ", _norm(original))
        if _WIDGET.search(text):
            text = _COUNTERS.sub("", re.sub(r"\s+", " ", _WIDGET.sub(" ", text)).strip().lstrip(_EDGE + "."))
        text = re.sub(r"\s+", " ", text).strip().lstrip(_EDGE)
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
    """Called by v13_final_guard.install()."""
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
    print("V13 CHROME SCRUB ACTIVE: duplicated breadcrumbs and page chrome are blocked.", flush=True)
