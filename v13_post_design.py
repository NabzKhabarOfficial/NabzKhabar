"""NABZ V13 — post design layer.

Gives every news post the NABZ signature look without touching the news
engine:

* Caption layout: urgency/category tag, bold title, one-line lead, details
  in a tap-to-expand quote, the NABZ pulse meter, topical hashtags and the
  channel link footer. No source is ever mentioned.
* Telegram formatting is sent as message *entities* (never parse_mode), so no
  text escaping is needed and a rejected style can fall back to plain text.
* No inline button (removed at the owner's request); a one-time cleanup
  strips the join button from the few posts that already carried it.
* News card: title rendered on the photo over a dark gradient, red NABZ pulse
  bar and urgency badge. Any failure falls back to the classic watermark.

Everything here is fail-safe: if a step fails, the post goes out exactly as it
would have before this layer existed.
"""

import json
import os
import re
import shutil
import tempfile
import time

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps, features

CHANNEL_URL = "https://t.me/NabzKhabarOfficial"
SHORT_URL = "t.me/NabzKhabarOfficial"
HANDLE = "@NabzKhabarOfficial"
BRAND_FA = "نبض خبر"
FONT_PATH = "Vazirmatn-Bold.ttf"
BUTTON_TEXT = "💓 عضویت در نبض خبر"
ACCENT = (229, 28, 45)
JOIN_BUTTON = False  # owner asked to remove the button under posts
CLEANUP_FLAG = "_join_button_cleanup_done"  # persisted in ai_model_health.json
CLEANUP_LOOKBACK = 60
MAX_CAPTION = 980  # below content_enhancer's 1000-char cut, so it never trims us

_CURRENT = {"candidate": None, "blocked": ""}
_PLANS = []          # most recent caption plans (title, quote, header)
_UNBRANDED = set()   # photo paths whose branding is deferred to send time

# --------------------------------------------------------------------------
# Classification (deterministic, keyword based)
# --------------------------------------------------------------------------

IRAN_TERMS = (
    "ایران", "تهران", "سپاه", "خامنه", "پزشکیان", "عراقچی", "اصفهان",
    "مشهد", "تبریز", "شیراز", "خوزستان", "بندرعباس", "تنگه هرمز",
)
ECON_TERMS = (
    "دلار", "یورو", "طلا", "سکه", "بورس", "تورم", "نرخ بهره", "بانک مرکزی",
    "قیمت نفت", "بنزین", "اقتصاد", "تعرفه", "بازار", "ارز",
)
TECH_TERMS = (
    "هوش مصنوعی", "تراشه", "اپل", "گوگل", "مایکروسافت", "متا", "انویدیا",
    "سایبری", "اینترنت", "فناوری", "ماهواره", "ربات", "اسپیس ایکس",
)
SPORT_TERMS = ("فوتبال", "فینال", "جام جهانی", "المپیک", "لیگ", "تیم ملی")

CATEGORIES = (
    (IRAN_TERMS, "🇮🇷", "ایران"),
    (ECON_TERMS, "💰", "اقتصاد"),
    (TECH_TERMS, "💻", "فناوری"),
    (SPORT_TERMS, "⚽", "ورزش"),
)

TOPIC_TAGS = (
    ("ایران", "#ایران"), ("اسرائیل", "#اسرائیل"), ("نتانیاهو", "#اسرائیل"),
    ("آمریکا", "#آمریکا"), ("ترامپ", "#ترامپ"), ("روسیه", "#روسیه"),
    ("پوتین", "#روسیه"), ("اوکراین", "#اوکراین"), ("غزه", "#غزه"),
    ("لبنان", "#لبنان"), ("حزب الله", "#لبنان"), ("سوریه", "#سوریه"),
    ("عراق", "#عراق"), ("یمن", "#یمن"), ("عربستان", "#عربستان"),
    ("چین", "#چین"), ("ترکیه", "#ترکیه"), ("اروپا", "#اروپا"),
    ("ناتو", "#ناتو"), ("سازمان ملل", "#سازمان_ملل"), ("تنگه هرمز", "#تنگه_هرمز"),
    ("هسته ای", "#هسته_ای"), ("نفت", "#نفت"), ("دلار", "#دلار"), ("طلا", "#طلا"),
    ("هوش مصنوعی", "#هوش_مصنوعی"), ("زلزله", "#زلزله"), ("انتخابات", "#انتخابات"),
)

URGENT_WORDS = (
    "فوری", "حمله", "انفجار", "کشته", "زلزله", "جنگ", "موشک", "ترور",
    "سقوط", "آتش بس", "استعفا", "تحریم", "بمباران",
)


def _norm(value):
    value = str(value or "").replace("\u200c", " ").replace("ي", "ی").replace("ك", "ک")
    return re.sub(r"\s+", " ", value).strip()


BREAKING_WORDS = (
    "حمله", "انفجار", "کشته", "زلزله", "ترور", "سقوط هواپیما", "بمباران",
    "موشک", "استعفا", "آتش بس", "اعلام جنگ", "کودتا", "تیراندازی",
)
BREAKING_MAX_AGE_SECONDS = 90 * 60
NOT_BREAKING_WORDS = (
    "تشییع", "مراسم", "سالگرد", "یادبود", "بزرگداشت", "گرامیداشت", "هشدار", "تهدید",
    "احتمال", "سالروز", "خاطره", "روایت", "تحلیل", "یادداشت", "مصاحبه", "واکنش",
)
FOREIGN_TERMS = (
    "آمریکا", "ترامپ", "اسرائیل", "نتانیاهو", "روسیه", "پوتین", "اوکراین", "غزه",
    "کرانه باختری", "لبنان", "سوریه", "عراق", "یمن", "عربستان", "چین", "ترکیه", "اروپا",
    "آلمان", "فرانسه", "انگلیس", "بریتانیا", "ژاپن", "هند", "پاکستان", "افغانستان",
    "برزیل", "ونزوئلا", "مکزیک", "کانادا", "استرالیا", "مصر", "قطر", "امارات", "کره",
    "ناتو", "سازمان ملل", "اتحادیه اروپا", "آفریقا", "کامرون", "تایوان",
    "صهیونیست", "فلسطین", "حماس", "حزب الله", "تل آویو", "کرانه", "بغداد", "دمشق", "بیروت",
    "ریاض", "مسکو", "واشنگتن", "پکن", "لندن", "پاریس", "برلین", "کی یف", "سئول",
)
_FOREIGN_RE = re.compile(
    r"(?<![\u0600-\u06FF\w])(?:" + "|".join(re.escape(t) for t in FOREIGN_TERMS)
    + r")(?:ی|ها|ای)?(?![\u0600-\u06FF\w])")


def _age_seconds(candidate):
    try:
        value = candidate.get("age_seconds")
        return None if value is None else float(value)
    except Exception:
        return None


def classify(title, candidate=None):
    """Return (level 1..5, urgent flag, category emoji, category label).

    "فوری" is reserved for real breaking news: a hard-breaking event word in
    the title, a high editorial tier, and (when known) a fresh story.
    """
    text = _norm(title)
    candidate = candidate or {}
    try:
        tier = int(candidate.get("publication_tier") or 0)
        score = int(candidate.get("intelligence_score") or 0)
    except Exception:
        tier, score = 0, 0
    breaking_word = any(w in text for w in BREAKING_WORDS)
    age = _age_seconds(candidate)
    fresh = age is None or age <= BREAKING_MAX_AGE_SECONDS
    calm = any(w in text for w in NOT_BREAKING_WORDS)
    urgent = breaking_word and fresh and tier >= 3 and not calm

    if urgent:
        level = 5
    elif (tier >= 4 and score >= 12) or score >= 16:
        level = 4
    elif tier == 3:
        level = 3 + (1 if score >= 12 else 0)
    else:
        level = 3

    emoji, label = "🌍", "جهان"
    cat = _norm(candidate.get("category", ""))
    if candidate.get("_major_sports") or "ورزش" in cat:
        emoji, label = "⚽", "ورزش"
    elif any(t in text for t in IRAN_TERMS) or (
            "ایران" in cat and not _FOREIGN_RE.search(text)):
        emoji, label = "🇮🇷", "ایران"
    else:
        for terms, e, l in CATEGORIES:
            if any(t in text for t in terms):
                emoji, label = e, l
                break
    return level, urgent, emoji, label


def hashtags(title, limit=2):
    text = _norm(title)
    tags = []
    for word, tag in TOPIC_TAGS:
        if word in text and tag not in tags:
            tags.append(tag)
        if len(tags) >= limit:
            break
    return " ".join(tags)


# Topic tag: each post gets a label describing what the story is about,
# instead of generic "urgent"/"important" stamps (owner's request).
TOPICS = (
    ("⚔️", "نظامی", ("حمله", "موشک", "پهپاد", "بمباران", "ارتش", "نظامی", "ناو", "تفنگدار",
                     "جنگ", "پایگاه", "یورش", "ترور", "شلیک", "درگیری", "آتش بس", "سپاه")),
    ("🚨", "حادثه", ("انفجار", "آتش سوزی", "سقوط", "زلزله", "سیل", "تصادف", "مصدوم",
                     "غرق", "ریزش", "طوفان", "حادثه")),
    ("⚖️", "قضایی", ("دادگاه", "اعدام", "دیوان", "حکم", "محاکمه", "بازداشت", "زندان", "قوه قضاییه")),
    ("🏛", "سیاست", ("وزیر", "سفارت", "سفیر", "دیپلماتیک", "مذاکره", "رئیس جمهور", "مجلس",
                     "انتخابات", "تحریم", "سازمان ملل", "دولت", "پارلمان", "نخست وزیر", "کنگره")),
    ("💰", "اقتصاد", ECON_TERMS + ("نفت", "صادرات", "واردات", "دیزل", "گازوئیل", "تجارت", "میلیارد")),
    ("💻", "فناوری", TECH_TERMS),
    ("🩺", "سلامت", ("بیماری", "واکسن", "ویروس", "بیمارستان", "سلامت", "دارو", "شیوع")),
    ("🌦", "آب و هوا", ("هواشناسی", "بارش", "باران", "برف", "گرما", "سرما", "خشکسالی")),
)


def topic_of(title, label):
    text = _norm(title)
    if label == "ورزش":
        return "⚽", "ورزش"
    for emoji, name, words in TOPICS:
        if any(w in text for w in words):
            return emoji, name
    return "📰", "خبر"


def header_line(level, urgent, emoji, label, title=""):
    t_emoji, t_name = topic_of(title, label)
    if label == "ورزش":
        return f"{t_emoji} {t_name}"
    return f"{emoji} {label} · {t_emoji} {t_name}"


def meter(level):
    level = max(1, min(5, int(level)))
    return "▰" * level + "▱" * (5 - level)


# --------------------------------------------------------------------------
# Caption
# --------------------------------------------------------------------------

def _split(text):
    parts = re.split(r"(?<=[.!؟؛])\s+", str(text or "").strip())
    return [p.strip() for p in parts if p.strip()]


def build_caption(title, body, formatter):
    """Signature caption; returns "" when the content is not publishable."""
    title = formatter.format_title(title)
    body = formatter.format_body(body)
    if not title or not body:
        if _CURRENT.get("candidate") is not None:
            # A news story that cannot be formatted cleanly is not published
            # in the old raw layout either.
            _CURRENT["blocked"] = "unformattable-text"
        return ""
    sentences = _split(body)
    try:
        import v13_relevance_gate
        problem = v13_relevance_gate.caption_problem(title, sentences)
    except Exception:
        problem = ""
    if problem:
        # Block the whole post; the sender guard refuses it (no fallback text).
        _CURRENT["blocked"] = problem
        print(f"V13 POST QUALITY: blocked ({problem}) -> {title}", flush=True)
        return ""
    if not sentences:
        return ""

    level, urgent, emoji, label = classify(title, _CURRENT.get("candidate"))
    urgent = False  # no "urgent"/"important" stamps; the topic tag says what it is
    header = header_line(level, urgent, emoji, label, title)
    card_label = topic_of(title, label)[1]
    lead = f"⚡️ {sentences[0]}"
    details = sentences[1:4]
    tags = hashtags(title)
    footer = "\n".join([f"💓 نبض خبر: {meter(level)}"] + ([tags] if tags else []) + [
        "━━━━━━━━━━",
        f"🔗 {SHORT_URL}",
    ])

    while True:
        quote = "\n".join(f"▫️ {d}" for d in details)
        blocks = [header, title, lead] + ([quote] if quote else []) + [footer]
        caption = "\n\n".join(blocks)
        if len(caption) <= MAX_CAPTION or not details:
            break
        details = details[:-1]
    if len(caption) > MAX_CAPTION:
        return ""

    _PLANS.append({"title": title, "quote": quote, "header": header,
                   "level": level, "urgent": urgent, "label": card_label})
    del _PLANS[:-20]
    return caption


def _plan_for(text):
    text = str(text or "")
    if SHORT_URL not in text:
        return None
    for plan in reversed(_PLANS):
        if plan["title"] and plan["title"] in text:
            return plan
    return None


def _u16(value):
    return len(value.encode("utf-16-le")) // 2


def entities_for(text, plan):
    result = []
    for sub, kind in ((plan.get("header"), "bold"), (plan.get("title"), "bold"),
                      (plan.get("quote"), "expandable_blockquote")):
        if not sub:
            continue
        i = text.find(sub)
        if i < 0:
            continue
        result.append({"type": kind, "offset": _u16(text[:i]), "length": _u16(sub)})
    result.sort(key=lambda e: e["offset"])
    return result


# --------------------------------------------------------------------------
# Telegram transport: add caption entities, fall back to plain on 400
# --------------------------------------------------------------------------

_SEND_RE = re.compile(r"/bot[^/]+/(sendPhoto|sendVideo|sendMessage)(?:$|\?)")
_original_request = requests.Session.request


def _rewind(files):
    if isinstance(files, dict):
        for value in files.values():
            obj = value[1] if isinstance(value, tuple) and len(value) > 1 else value
            try:
                obj.seek(0)
            except Exception:
                pass


def _cleanup_old_buttons(session, url, method_name, payload, response):
    """One time: remove the join button from posts published while it existed."""
    try:
        import v13_ai_router
        health = v13_ai_router._load_health()
        if health.get(CLEANUP_FLAG):
            return
        if getattr(response, "status_code", 0) != 200:
            return
        import v13_standalone
        if str(payload.get("chat_id")) != str(getattr(v13_standalone, "CHANNEL_ID", "")):
            return  # only clean the news channel itself
        message_id = int(response.json()["result"]["message_id"])
        edit_url = str(url).replace(method_name, "editMessageReplyMarkup")
        empty = json.dumps({"inline_keyboard": []})
        cleared = 0
        for mid in range(message_id - 1, max(0, message_id - 1 - CLEANUP_LOOKBACK), -1):
            try:
                r = _original_request(session, "POST", edit_url, data={
                    "chat_id": payload.get("chat_id"), "message_id": mid, "reply_markup": empty,
                }, timeout=10)
                if getattr(r, "status_code", 0) == 200:
                    cleared += 1
            except Exception:
                pass
            time.sleep(0.1)
        health = v13_ai_router._load_health()
        health[CLEANUP_FLAG] = True
        v13_ai_router._save_health(health)
        print(f"V13 POST DESIGN: join button removed from {cleared} earlier post(s).", flush=True)
    except Exception as exc:
        print(f"V13 POST DESIGN: button cleanup skipped ({type(exc).__name__}).", flush=True)


def _styled_request(self, method, url, *args, **kwargs):
    try:
        match = _SEND_RE.search(str(url))
    except Exception:
        match = None
    if not match:
        return _original_request(self, method, url, *args, **kwargs)

    key = "data" if isinstance(kwargs.get("data"), dict) else (
        "json" if isinstance(kwargs.get("json"), dict) else None)
    if key is None:
        return _original_request(self, method, url, *args, **kwargs)
    payload = kwargs[key]
    is_text = match.group(1) == "sendMessage"
    text = payload.get("text" if is_text else "caption")
    plan = _plan_for(text)
    if (not plan or "parse_mode" in payload or "reply_markup" in payload
            or "entities" in payload or "caption_entities" in payload):
        response = _original_request(self, method, url, *args, **kwargs)
        _cleanup_old_buttons(self, url, match.group(1), payload, response)
        return response

    extra = {}
    if JOIN_BUTTON:
        extra["reply_markup"] = {"inline_keyboard": [[{"text": BUTTON_TEXT, "url": CHANNEL_URL}]]}
    ents = entities_for(str(text), plan)
    if ents:
        extra["entities" if is_text else "caption_entities"] = ents
    if not extra:
        response = _original_request(self, method, url, *args, **kwargs)
        _cleanup_old_buttons(self, url, match.group(1), payload, response)
        return response
    styled = dict(payload)
    for k, v in extra.items():
        styled[k] = json.dumps(v, ensure_ascii=False) if key == "data" else v
    styled_kwargs = dict(kwargs)
    styled_kwargs[key] = styled

    response = _original_request(self, method, url, *args, **styled_kwargs)
    if getattr(response, "status_code", 0) == 400:
        # 400 means nothing was published, so a plain resend cannot duplicate.
        print("V13 POST DESIGN: styled post rejected (400); resending plain.", flush=True)
        _rewind(kwargs.get("files"))
        response = _original_request(self, method, url, *args, **kwargs)
    _cleanup_old_buttons(self, url, match.group(1), payload, response)
    return response


# --------------------------------------------------------------------------
# News card renderer
# --------------------------------------------------------------------------

def _font(size, path=None):
    font = ImageFont.truetype(path or FONT_PATH, size)
    try:
        font.set_variation_by_name("Bold")  # variable fonts only
    except Exception:
        pass
    return font


def card_supported():
    try:
        return bool(features.check("raqm")) and os.path.exists(FONT_PATH)
    except Exception:
        return False


def _wrap(draw, text, font, max_w):
    lines, cur = [], []
    for word in text.split():
        trial = " ".join(cur + [word])
        if cur and draw.textlength(trial, font=font, direction="rtl") > max_w:
            lines.append(" ".join(cur))
            cur = [word]
        else:
            cur.append(word)
    if cur:
        lines.append(" ".join(cur))
    return lines


def _pulse(draw, x_right, y_mid, w, h, width):
    # ECG-style heartbeat line, drawn right-to-left to match RTL layout.
    pts = [(0, 0), (0.30, 0), (0.38, -0.25), (0.46, 0), (0.52, 0.0),
           (0.58, -1.0), (0.66, 0.85), (0.72, 0), (0.80, -0.2), (0.86, 0), (1.0, 0)]
    poly = [(x_right - p[0] * w, y_mid + p[1] * h / 2) for p in pts]
    draw.line(poly, fill=ACCENT + (255,), width=width, joint="curve")


def render_card(src_path, out_path, title, level=3, label="جهان", font_path=None, urgent=False):
    """Draw the NABZ news card. Returns True only when out_path was written."""
    img = Image.open(src_path)
    img = ImageOps.exif_transpose(img).convert("RGB")
    w, h = img.size
    if w < 420 or h < 300:
        return False
    # Normalise to Telegram's 1280px long side for consistent, crisp text.
    factor = 1280.0 / max(w, h)
    if abs(factor - 1) > 0.02:
        img = img.resize((max(1, int(w * factor)), max(1, int(h * factor))), Image.LANCZOS)
    W, H = img.size
    # Scale type by the *height* on wide photos so the title never swallows
    # a landscape image (sea, crowds, skylines stay visible).
    u = min(W, H * 1.25) / 1080.0
    margin = int(40 * u)

    probe = ImageDraw.Draw(img)
    size = int(46 * u)
    min_size = int(36 * u)
    max_lines = 2
    lines = []
    while True:
        tfont = _font(size, font_path)
        lines = _wrap(probe, title, tfont, W - 2 * margin)
        if len(lines) <= max_lines or size <= min_size:
            break
        size = int(size * 0.92)
    if len(lines) > max_lines:
        lines = []  # too long for a tidy card: brand bar only, title stays in the caption
    line_h = int(size * 1.4)

    brand_font = _font(int(24 * u), font_path)
    handle_font = _font(int(20 * u), font_path)
    badge_font = _font(int(24 * u), font_path)

    brand_row = int(50 * u)
    title_h = (int(20 * u) + len(lines) * line_h) if lines else 0
    block_h = title_h + int(16 * u) + brand_row + margin // 2
    if block_h > int(H * 0.40) and lines:
        lines, title_h = [], 0
        block_h = int(16 * u) + brand_row + margin // 2
    band_h = min(int(H * 0.48), block_h + int(70 * u))

    # Dark gradient for legibility.
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    top = H - band_h
    for y in range(top, H):
        t = (y - top) / max(1, band_h)
        od.line([(0, y), (W, y)], fill=(6, 8, 14, int(225 * min(1.0, t * 1.2) ** 1.3)))
    base = img.convert("RGBA")
    base.alpha_composite(overlay)
    d = ImageDraw.Draw(base, "RGBA")

    right = W - margin
    y = H - block_h
    if lines:
        # Red accent bar above the title.
        d.rounded_rectangle((right - int(80 * u), y, right, y + max(4, int(6 * u))),
                            radius=3, fill=ACCENT + (255,))
        y += int(20 * u)
        for line in lines:
            d.text((right + 2, y + 2), line, font=tfont, fill=(0, 0, 0, 150), anchor="ra", direction="rtl")
            d.text((right, y), line, font=tfont, fill=(255, 255, 255, 255), anchor="ra", direction="rtl")
            y += line_h
    y += int(6 * u)
    d.line([(margin, y), (right, y)], fill=(255, 255, 255, 55), width=max(1, int(2 * u)))
    y_mid = y + brand_row // 2 + int(4 * u)
    d.text((right, y_mid), BRAND_FA, font=brand_font, fill=(255, 255, 255, 245),
           anchor="rm", direction="rtl")
    bw = d.textlength(BRAND_FA, font=brand_font, direction="rtl")
    _pulse(d, right - bw - int(14 * u), y_mid, int(96 * u), int(28 * u), max(2, int(3 * u)))
    d.text((margin, y_mid), HANDLE, font=handle_font, fill=(210, 216, 226, 230), anchor="lm")

    # Top-right badge: live "فوری" for breaking news, otherwise the category.
    badge = "فوری" if urgent else label
    pad_x, pad_y = int(18 * u), int(9 * u)
    tw = d.textlength(badge, font=badge_font, direction="rtl")
    dot = int(11 * u) if urgent else 0
    bx2, by1 = W - margin, margin
    bx1 = bx2 - int(tw) - 2 * pad_x - (dot + int(10 * u) if dot else 0)
    by2 = by1 + int(26 * u) + 2 * pad_y
    fill = ACCENT + (240,) if urgent else (8, 12, 18, 170)
    d.rounded_rectangle((bx1, by1, bx2, by2), radius=int(14 * u), fill=fill,
                        outline=(255, 255, 255, 90), width=max(1, int(2 * u)))
    cy = (by1 + by2) // 2
    d.text((bx2 - pad_x, cy), badge, font=badge_font, fill=(255, 255, 255, 255),
           anchor="rm", direction="rtl")
    if dot:
        cx = bx1 + pad_x + dot // 2
        d.ellipse((cx - dot // 2, cy - dot // 2, cx + dot // 2, cy + dot // 2), fill=(255, 255, 255, 255))

    base.convert("RGB").save(out_path, "JPEG", quality=92, optimize=True)
    return True


# --------------------------------------------------------------------------
# Install
# --------------------------------------------------------------------------

def install(core, formatter):
    # 1) Caption layout: the editorial formatter's install() resolves the
    #    module-level build_caption at call time, so swapping it is enough.
    original_formatter_caption = formatter.build_caption

    def designed_caption(title, body):
        try:
            value = build_caption(title, body, formatter)
            if value:
                return value
        except Exception as exc:
            print(f"V13 POST DESIGN: caption fallback ({type(exc).__name__})", flush=True)
        return original_formatter_caption(title, body)

    formatter.build_caption = designed_caption

    # 2) Remember which story is being processed (urgency + category).
    inner_process = core.process_news

    def process_news(candidate, *args, **kwargs):
        _CURRENT["candidate"] = candidate if isinstance(candidate, dict) else None
        _CURRENT["blocked"] = ""
        try:
            return inner_process(candidate, *args, **kwargs)
        finally:
            _CURRENT["candidate"] = None
            _CURRENT["blocked"] = ""

    core.process_news = process_news

    # 3) Defer photo branding to send time, where the title is known.
    classic_watermark = core.add_watermark

    def add_watermark(input_path, output_path):
        if card_supported() and input_path != output_path:
            try:
                shutil.copyfile(input_path, output_path)
                _UNBRANDED.add(output_path)
                return output_path
            except Exception:
                pass
        return classic_watermark(input_path, output_path)

    core.add_watermark = add_watermark

    inner_send_photo = core.send_photo

    def send_photo(path, caption):
        send_path, temp = path, None
        if path in _UNBRANDED:
            _UNBRANDED.discard(path)
            try:
                fd, temp = tempfile.mkstemp(suffix=".jpg")
                os.close(fd)
                plan = _plan_for(caption)
                done = False
                if plan:
                    try:
                        done = render_card(path, temp, plan["title"], plan["level"], plan["label"],
                                           urgent=bool(plan.get("urgent")))
                    except Exception as exc:
                        print(f"V13 NEWS CARD: render failed ({type(exc).__name__}); classic watermark.", flush=True)
                if done:
                    print("V13 NEWS CARD: rendered.", flush=True)
                else:
                    done = classic_watermark(path, temp) == temp
                if done:
                    send_path = temp
            except Exception as exc:
                print(f"V13 NEWS CARD: branding skipped ({type(exc).__name__}).", flush=True)
        try:
            return inner_send_photo(send_path, caption)
        finally:
            if temp and os.path.exists(temp):
                try:
                    os.remove(temp)
                except Exception:
                    pass

    core.send_photo = send_photo

    # Content-level duplicate guard, outermost around the senders.
    try:
        import v13_story_dedup
        v13_story_dedup.install(core, _CURRENT)
    except Exception as exc:
        print(f"V13 STORY DEDUP: not installed ({type(exc).__name__}: {exc})", flush=True)

    # Relevance (foreign soft-local) + post-quality gate.
    try:
        import v13_relevance_gate
        v13_relevance_gate.install(core, _CURRENT)
    except Exception as exc:
        print(f"V13 RELEVANCE GATE: not installed ({type(exc).__name__}: {exc})", flush=True)

    # Growth: website pages + nightly digest (outermost, records real sends).
    try:
        import v13_growth
        v13_growth.install(core, _CURRENT, _plan_for)
    except Exception as exc:
        print(f"V13 GROWTH: not installed ({type(exc).__name__}: {exc})", flush=True)

    # 4) Caption entities at the transport level (+ one-time button cleanup).
    if requests.Session.request is not _styled_request:
        requests.Session.request = _styled_request

    print("V13 POST DESIGN ACTIVE: news card + signature caption (no join button).", flush=True)
