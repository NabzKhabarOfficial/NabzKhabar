"""NABZ KHABAR: final-guard repair + refusal memory (Oct 15 2026).

Oct 14 the final guard (v13_final_guard) refused 54 posts, many of them important (the Aramco hit
in Dhahran 7 times, "4 hurt in Riyadh" 4 times, the Mostafavi execution), because the LEAD still
named an outlet («به گزارش رویترز،»، «خبرگزاری رسمی عربستان») or the sentence splitter had cut a
quote in two («...ممکن است. ...» -> two sentences, each with one quote mark). The owner rule is
"no outlet name in a post", not "no post". So:

1. Repair before refusing. When the guard finds an outlet name or a broken quote, the post's
   sentences are repaired IN PLACE (v13_post_design builds the caption from this same list):
   * attribution naming an outlet is cut: «به گزارش رویترز،» / «، به نقل از الجزیره» are
     removed, «رویترز گزارش داد که ...» -> «طبق گزارش ها، ...», «رویترز به نقل از دو منبع ...»
     -> «دو منبع ...», «(رویترز)» removed; «خبرگزاری رسمی X» -> «رسانه رسمی X»;
   * sentences that one quote spans are joined again; a quote left open in the lead is closed,
     a detail line with a broken quote is dropped;
   * if the lead still names an outlet, the next sentence becomes the lead.
   The repair is used only when the guard then finds NOTHING (all its checks run again, incl.
   the off-topic-lead check); otherwise the post is refused exactly as before. The title is
   never changed: a title naming an outlet is still refused.
2. Remember refusals. A story the guard refused is saved as an editorial block (run_bot, 6 h),
   so it is not fetched, translated, judged and refused again on every run (Oct 14: the same
   Nepal-flood story 6 times, the Aramco story 7 times, each costing AI calls).

Fail-safe: any error leaves the guard's original verdict untouched.
"""

import re
import sys

_INSTALLED = {"done": False}


def _patterns():
    import v13_final_guard as fg
    s, out = fg._S, fg.OUTLET_NAMES.pattern
    on = (r"(?:(?:خبرگزاری|روزنامه|شبکه(?:" + s + r"+خبری)?|پایگاه(?:" + s + r"+خبری)?|وبگاه|نشریه|تلویزیون|رادیو)"
          + s + r"+)?" + out + r"(?:" + s + r"+(?:آمریکایی|انگلیسی|بریتانیایی|قطری|عربستانی|سعودی|روسی|فرانسوی|"
          r"اسرائیلی|عربی|آلمانی|ترکیه\u200cای|ترکیه ای))?")
    via = (r"(?:به" + s + r"+گزارش|به" + s + r"+نقل" + s + r"+از|طبق" + s + r"+گزارش|بنا" + s + r"*بر" + s + r"+گزارش|"
           r"بر" + s + r"*اساس" + s + r"+گزارش|به" + s + r"+نوشته|به" + s + r"+ادعای)")
    verbs = (r"(?:گزارش" + s + r"+(?:داد|داده" + s + r"+است|کرد)|نوشت|اعلام" + s + r"+کرد|فاش" + s + r"+کرد|"
             r"افشا" + s + r"+کرد|مدعی" + s + r"+شد)(?![" + fg._P + r"])")
    told = (r"(?:در" + s + r"+(?:گفت" + s + r"*و" + s + r"*گو|گفتگو|مصاحبه)" + s + r"+با|به)" + s + r"+" + on
            + r"(?=" + s + r"+(?:گفت|گفته|اعلام|تایید|تأیید|اظهار|افزود))")
    return [
        (re.compile(r"^\s*" + via + s + r"+[^،,.؛!؟]{0,40}?" + on + r"[^،,.؛!؟]{0,30}?[،,]\s*"), ""),
        (re.compile(r"\s*[،,]?\s*" + via + s + r"+[^،,.؛!؟]{0,40}?" + on + r"[^،,.؛!؟]{0,30}?(?=[،,.؛!؟]|$)"), ""),
        (re.compile(on + s + r"+(?:به" + s + r"+نقل" + s + r"+از|از" + s + r"+قول)" + s + r"+"), ""),
        (re.compile(on + r"(?:" + s + r"+(?:در|طی)" + s + r"+(?:گزارشی|مطلبی|گزارش" + s + r"+\S+))?" + s + r"+" + verbs
                    + r"(?:" + s + r"+که)?\s*[:،,]?\s*"), "طبق گزارش\u200cها، "),
        (re.compile(r"\s*[(\[]\s*" + on + r"\s*[)\]]"), ""),
        (re.compile(told), ""),
    ]


def _tidy(x):
    x = re.sub(r"\s+", " ", x).strip()
    x = re.sub(r"\s+([،,.؛!؟])", r"\1", x)
    x = re.sub(r"^[،,؛:\s]+", "", x)
    x = re.sub(r"[،,]\s*([.!؟؛])", r"\1", x)
    x = re.sub(r"^که\s+", "", x)
    x = re.sub(r"(طبق گزارش\u200cها،)\s*طبق گزارش\u200cها،", r"\1", x)
    return x


def _strip_outlets(sentence, rules):
    x = re.sub(r"خبرگزاری[\s\u200c]+رسمی", "رسانه رسمی", str(sentence or ""))
    end = re.search(r"[.!؟؛]$", x.strip())
    for rx, rep in rules:
        x = rx.sub(rep, x)
    x = _tidy(x)
    if end and x and not re.search(r"[.!؟؛»]$", x):
        x += end.group(0)
    return x


def _join_quotes(sents):
    """Sentences that one «...» quote spans are joined back (the splitter cut at a period inside it)."""
    out, pieces = [], []
    for s in sents:
        pieces.append(s)
        buf = " ".join(pieces)
        if buf.count("«") <= buf.count("»"):
            out.append(buf)
            pieces = []
    if pieces:  # a quote never closed: keep the pieces apart, the lead fix below handles it
        out.extend(pieces)
    fixed = []
    for i, s in enumerate(out):
        o, c = s.count("«"), s.count("»")
        if o == c:
            fixed.append(s)
        elif i == 0 and o > c:
            fixed.append(re.sub(r"([.!؟]?)\s*$", "»" * (o - c) + r"\1", s, count=1))
        elif i == 0:
            fixed.append(s.replace("»", "", c - o))
        # a detail line with a broken quote is dropped
    return fixed


def variants(sentences):
    rules = _patterns()
    base = [str(s or "") for s in sentences]
    v1 = [x for x in (_strip_outlets(s, rules) for s in _join_quotes(base)) if len(x.split()) >= 3]
    out = [v1]
    if len(v1) >= 2:
        out.append(v1[1:])
    return out


def install():
    if _INSTALLED["done"]:
        return
    import v13_final_guard as fg
    original = fg.problems

    def problems(title, sentences):
        found = original(title, sentences)
        try:
            if not found or not isinstance(sentences, list):
                return found
            if not {r for r, _ in found} & {"media-source", "cut-quote"}:
                return found
            for cand in variants(sentences):
                if not cand or cand == sentences:
                    continue
                if not original(title, cand):
                    sentences[:] = cand
                    try:
                        print("V13 GUARD REPAIR: " + ", ".join(sorted({r for r, _ in found}))
                              + " fixed in the text instead of refusing -> " + str(title or "")[:100], flush=True)
                    except Exception:
                        pass
                    return []
        except Exception as exc:
            print(f"V13 GUARD REPAIR: skipped ({type(exc).__name__}: {exc})", flush=True)
        return found

    fg.problems = problems
    original_log = fg._log

    def log(title, found):
        original_log(title, found)
        try:
            rb = sys.modules.get("run_bot")
            if rb is None:
                return
            cand = {}
            try:
                import v13_post_design as pd
                cand = pd._CURRENT.get("candidate") or {}
            except Exception:
                pass
            key = rb._norm_title(cand.get("title") or title)
            if key:
                rb._editorial_blocks_this_run.setdefault(key, "final_guard:" + str(found[0][0]))
        except Exception:
            pass

    fg._log = log
    _INSTALLED["done"] = True
    print("V13 GUARD REPAIR ACTIVE: outlet names and split quotes are fixed in the text; refusals remembered 6 h", flush=True)
