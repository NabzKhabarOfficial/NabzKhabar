"""Image cards for the NabzKhabar daily boards (weather, car prices).

Cards are rendered with Pillow + raqm (Persian shaping) and the bundled
Vazirmatn fonts. Every public function returns None on any problem so the
caller can fall back to the classic text board.
"""
from __future__ import annotations

import math
import os
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, features

W = 1080
BRAND = "نبض خبر"
HANDLE = "@NabzKhabarOfficial"
FA_DIGITS = str.maketrans("0123456789-.", "۰۱۲۳۴۵۶۷۸۹−٫")
FONT_FILES = {
    "bold": ("Vazirmatn-Bold.ttf", "/usr/local/share/fonts/google/vazirmatn/Vazirmatn[wght].ttf"),
    "regular": ("Vazirmatn-Regular.ttf", "/usr/local/share/fonts/google/vazirmatn/Vazirmatn[wght].ttf"),
}
_FONTS: dict = {}

INK = (236, 240, 247)
MUTED = (150, 162, 182)
ACCENT = (229, 28, 45)
CARD = (21, 28, 42)
CARD2 = (17, 23, 35)
LINE = (38, 48, 68)


def fa(value) -> str:
    return str(value).translate(FA_DIGITS)


def supported() -> bool:
    try:
        return bool(features.check("raqm")) and all(_font_path(k) for k in FONT_FILES)
    except Exception:
        return False


def _font_path(kind):
    for p in FONT_FILES[kind]:
        if os.path.exists(p):
            return p
    return ""


def font(size, kind="bold"):
    key = (size, kind)
    if key not in _FONTS:
        f = ImageFont.truetype(_font_path(kind), size)
        try:
            f.set_variation_by_name("Bold" if kind == "bold" else "Regular")
        except Exception:
            pass
        _FONTS[key] = f
    return _FONTS[key]


def rtl(d, xy, text, f, fill, anchor="ra"):
    d.text(xy, text, font=f, fill=fill, anchor=anchor, direction="rtl")


def tlen(d, text, f):
    return d.textlength(text, font=f, direction="rtl")


def _fit(d, text, size, kind, max_w, min_size=20):
    f = font(size, kind)
    while tlen(d, text, f) > max_w and size > min_size:
        size -= 1
        f = font(size, kind)
    return f


def _background(h, top, bottom):
    img = Image.new("RGB", (W, h), bottom)
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = min(1.0, y / max(1, h * 0.55))
        c = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        d.line([(0, y), (W, y)], fill=c)
    return img


def _glow(img, xy, r, color, alpha=90):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse([xy[0] - r, xy[1] - r, xy[0] + r, xy[1] + r], fill=color + (alpha,))
    layer = layer.filter(ImageFilter.GaussianBlur(r // 2))
    img.paste(layer, (0, 0), layer)


def _pulse(d, x_right, y, w, h, width=5):
    pts = [(0, 0), (0.30, 0), (0.38, -0.25), (0.46, 0), (0.52, 0.0), (0.58, -1.0),
           (0.66, 0.85), (0.72, 0), (0.80, -0.2), (0.86, 0), (1.0, 0)]
    d.line([(x_right - p[0] * w, y + p[1] * h / 2) for p in pts], fill=ACCENT, width=width, joint="curve")


def _header(img, title, subtitle, date_text, accent):
    d = ImageDraw.Draw(img)
    rtl(d, (W - 60, 70), BRAND, font(44), INK, "rm")
    bw = tlen(d, BRAND, font(44))
    _pulse(d, W - 60 - bw - 20, 70, 130, 40)
    d.text((60, 70), HANDLE, font=font(26, "regular"), fill=MUTED, anchor="lm")
    rtl(d, (W - 60, 130), title, font(78), INK)
    rtl(d, (W - 60, 232), subtitle, font(32, "regular"), MUTED)
    pill = font(30)
    pw = tlen(d, date_text, pill)
    d.rounded_rectangle([60, 140, 60 + pw + 48, 200], radius=30, fill=accent)
    rtl(d, (60 + pw + 24, 170), date_text, pill, (255, 255, 255), "rm")


def _footer(img, y, note):
    d = ImageDraw.Draw(img)
    d.line([(60, y), (W - 60, y)], fill=LINE, width=2)
    rtl(d, (W - 60, y + 42), note, font(24, "regular"), MUTED, "rm")
    d.text((60, y + 42), "t.me/NabzKhabarOfficial", font=font(24, "regular"), fill=MUTED, anchor="lm")


# ------------------------------------------------------------------ weather
def _kind(code):
    code = int(code or 0)
    if code == 0:
        return "sun"
    if code in (1, 2):
        return "partly"
    if code == 3:
        return "cloud"
    if code in (45, 48):
        return "fog"
    if code in (71, 73, 75, 77, 85, 86):
        return "snow"
    if code in (95, 96, 99):
        return "storm"
    if code >= 51:
        return "rain"
    return "cloud"


def _cloud(d, cx, cy, s, fill):
    d.ellipse([cx - s * 0.95, cy - s * 0.15, cx - s * 0.15, cy + s * 0.55], fill=fill)
    d.ellipse([cx - s * 0.55, cy - s * 0.55, cx + s * 0.35, cy + s * 0.45], fill=fill)
    d.ellipse([cx + s * 0.05, cy - s * 0.25, cx + s * 0.85, cy + s * 0.55], fill=fill)
    d.rounded_rectangle([cx - s * 0.75, cy + s * 0.1, cx + s * 0.7, cy + s * 0.55], radius=int(s * 0.22), fill=fill)


def _sun(d, cx, cy, s):
    for i in range(8):
        a = i * math.pi / 4
        d.line([(cx + math.cos(a) * s * 0.62, cy + math.sin(a) * s * 0.62),
                (cx + math.cos(a) * s * 0.92, cy + math.sin(a) * s * 0.92)], fill=(255, 196, 61), width=max(3, int(s * 0.12)))
    d.ellipse([cx - s * 0.45, cy - s * 0.45, cx + s * 0.45, cy + s * 0.45], fill=(255, 205, 64))


def icon(d, kind, cx, cy, s=34):
    if kind == "sun":
        _sun(d, cx, cy, s)
    elif kind == "partly":
        _sun(d, cx + s * 0.3, cy - s * 0.3, s * 0.75)
        _cloud(d, cx - s * 0.1, cy + s * 0.1, s * 0.8, (226, 232, 242))
    elif kind == "cloud":
        _cloud(d, cx, cy, s, (196, 205, 220))
    elif kind == "fog":
        for i in range(3):
            y = cy - s * 0.45 + i * s * 0.45
            d.rounded_rectangle([cx - s * 0.85, y, cx + s * 0.85, y + s * 0.2], radius=int(s * 0.1), fill=(176, 186, 204))
    else:
        _cloud(d, cx, cy - s * 0.25, s * 0.9, (176, 188, 208))
        if kind == "rain":
            for i in range(3):
                x = cx - s * 0.45 + i * s * 0.45
                d.line([(x, cy + s * 0.45), (x - s * 0.14, cy + s * 0.85)], fill=(88, 170, 255), width=max(3, int(s * 0.12)))
        elif kind == "snow":
            for i in range(3):
                x = cx - s * 0.45 + i * s * 0.45
                d.ellipse([x - s * 0.1, cy + s * 0.55, x + s * 0.1, cy + s * 0.75], fill=(240, 248, 255))
        else:
            d.polygon([(cx + s * 0.05, cy + s * 0.3), (cx - s * 0.25, cy + s * 0.75), (cx, cy + s * 0.7),
                       (cx - s * 0.15, cy + s * 1.05), (cx + s * 0.3, cy + s * 0.55), (cx + s * 0.05, cy + s * 0.6)],
                      fill=(255, 205, 64))


def _temp_color(t):
    stops = [(-10, (110, 170, 255)), (5, (90, 200, 250)), (18, (120, 220, 150)),
             (28, (255, 200, 70)), (36, (255, 130, 60)), (45, (240, 60, 60))]
    if t <= stops[0][0]:
        return stops[0][1]
    for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
        if t <= t1:
            k = (t - t0) / (t1 - t0)
            return tuple(int(c0[i] + (c1[i] - c0[i]) * k) for i in range(3))
    return stops[-1][1]


def render_weather(rows, jalali_date, out_path, weather_text=None):
    """rows: list of dicts city,temp,tmin,tmax,code,rain. Returns path or None."""
    try:
        if not supported() or not rows:
            return None
        weather_text = weather_text or (lambda c: "")
        vals = [r for r in rows if r.get("tmin") is not None and r.get("tmax") is not None]
        lo = math.floor(min(r["tmin"] for r in vals)) if vals else 0
        hi = math.ceil(max(r["tmax"] for r in vals)) if vals else 40
        span = max(1, hi - lo)

        row_h, top = 76, 470
        h = top + 60 + len(rows) * row_h + 150
        img = _background(h, (14, 38, 74), (8, 12, 22))
        _glow(img, (W - 160, 120), 220, (255, 190, 80), 60)
        _header(img, "هواشناسی امروز", "دمای کمینه و بیشینه و احتمال بارش در مراکز استان‌ها", fa(jalali_date), (37, 99, 235))
        d = ImageDraw.Draw(img)

        hot = max(vals, key=lambda r: r["tmax"]) if vals else None
        cold = min(vals, key=lambda r: r["tmin"]) if vals else None
        wet = max(rows, key=lambda r: r.get("rain") or 0)
        chips = []
        if hot:
            chips.append(("گرم‌ترین", hot["city"], fa(f"{hot['tmax']:.0f}°"), (255, 130, 60)))
        if cold:
            chips.append(("سردترین", cold["city"], fa(f"{cold['tmin']:.0f}°"), (90, 170, 255)))
        if wet and (wet.get("rain") or 0) > 0:
            chips.append(("پرباران‌ترین", wet["city"], fa(f"{wet['rain']:.0f}٪"), (88, 200, 255)))
        cw = (W - 120 - 24 * (len(chips) - 1)) / max(1, len(chips))
        for i, (label, city, val, col) in enumerate(chips):
            x1 = W - 60 - i * (cw + 24)
            x0 = x1 - cw
            d.rounded_rectangle([x0, 300, x1, 420], radius=24, fill=CARD, outline=LINE, width=2)
            d.rounded_rectangle([x1 - 10, 320, x1 - 4, 400], radius=3, fill=col)
            rtl(d, (x1 - 28, 316), label, font(24, "regular"), MUTED)
            vf = font(44)
            vw = d.textlength(val, font=vf)
            rtl(d, (x1 - 28, 352), city, _fit(d, city, 34, "bold", cw - 28 - vw - 48, 20), INK)
            d.text((x0 + 24, 360), val, font=vf, fill=col, anchor="lm")

        x0, x1 = 60, W - 60
        hy = top + 22
        rtl(d, (x1 - 24, hy), "شهر", font(22), MUTED, "rm")
        rtl(d, (x1 - 300, hy), "کمینه", font(22), MUTED, "rm")
        d.text((x0 + 160, hy), "بیشینه", font=font(22), fill=MUTED, anchor="lm")
        d.text((x0 + 24, hy), "بارش", font=font(22), fill=MUTED, anchor="lm")
        bx0, bx1 = x0 + 270, x1 - 380
        for idx, r in enumerate(rows):
            y0 = top + 50 + idx * row_h
            d.rounded_rectangle([x0, y0, x1, y0 + row_h - 10], radius=18, fill=CARD if idx % 2 == 0 else CARD2)
            cy = y0 + (row_h - 10) / 2
            avail = 270 - 24 - 21 - 18  # space between the row edge and the weather icon
            cf = _fit(d, r["city"], 30, "bold", avail, 22)
            rtl(d, (x1 - 24, cy - 2), r["city"], cf, INK, "rm")
            cw_city = tlen(d, r["city"], cf)
            cond = weather_text(r.get("code", 0))
            if cond and cw_city + 12 + tlen(d, cond, font(19, "regular")) <= avail:
                rtl(d, (x1 - 36 - cw_city, cy + 2), cond, font(19, "regular"), MUTED, "rm")
            icon(d, _kind(r.get("code", 0)), x1 - 270, cy, 21)
            d.rounded_rectangle([bx0, cy - 5, bx1, cy + 5], radius=5, fill=LINE)
            if r.get("tmin") is not None and r.get("tmax") is not None:
                a_ = bx1 - (r["tmin"] - lo) / span * (bx1 - bx0)
                b_ = bx1 - (r["tmax"] - lo) / span * (bx1 - bx0)
                left, right = min(a_, b_), max(a_, b_)
                seg = Image.new("RGB", (max(10, int(right - left)), 10))
                sd = ImageDraw.Draw(seg)
                for px in range(seg.width):
                    t = r["tmax"] - (r["tmax"] - r["tmin"]) * px / max(1, seg.width - 1)
                    sd.line([(px, 0), (px, 10)], fill=_temp_color(t))
                mask = Image.new("L", seg.size, 0)
                ImageDraw.Draw(mask).rounded_rectangle([0, 0, seg.width - 1, 9], radius=5, fill=255)
                img.paste(seg, (int(left), int(cy - 5)), mask)
                d.text((bx1 + 22, cy), fa(f"{r['tmin']:.0f}°"), font=font(28, "regular"), fill=MUTED, anchor="lm")
                d.text((bx0 - 22, cy), fa(f"{r['tmax']:.0f}°"), font=font(30), fill=INK, anchor="rm")
            rain = r.get("rain")
            rc = (88, 170, 255) if (rain or 0) >= 30 else MUTED
            d.ellipse([x0 + 24, cy - 8, x0 + 38, cy + 8], fill=rc)
            d.polygon([(x0 + 25, cy - 3), (x0 + 37, cy - 3), (x0 + 31, cy - 16)], fill=rc)
            d.text((x0 + 50, cy), "—" if rain is None else fa(f"{rain:.0f}٪"), font=font(26), fill=rc, anchor="lm")
        _footer(img, h - 110, "هواشناسی روزانه · به‌وقت تهران")
        img.save(out_path, quality=92)
        return out_path
    except Exception as exc:
        print(f"DAILY CARDS: weather render failed: {type(exc).__name__}: {exc}", flush=True)
        return None


# ------------------------------------------------------------------ cars
def _change_kind(change):
    s = str(change or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    if not re.search(r"\d", s) or re.fullmatch(r"[\s0,٬.\-—]*", s):
        return 0
    if "-" in s or "−" in s or "کاهش" in s or "▼" in s:
        return -1
    return 1


def _millions(text):
    """'1,630,000,000تا 2,620,000,000' -> '۱٬۶۳۰ تا ۲٬۶۲۰' (million toman). '' when no number."""
    s = str(text or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    nums = [int(n.replace(",", "").replace("٬", "")) for n in re.findall(r"\d[\d,٬]*", s)]
    nums = [n for n in nums if n >= 1_000_000]
    if not nums:
        return ""

    def one(n):
        m = n / 1_000_000
        txt = f"{m:,.0f}" if m >= 100 or m == int(m) else f"{m:,.1f}"
        return fa(txt.replace(",", "٬"))

    lo, hi = min(nums[:2]), max(nums[:2])
    return one(lo) if lo == hi else f"{one(lo)} تا {one(hi)}"


def render_cars(items, update_date, out_path):
    """items: list of (label, market, factory, change). Returns path or None."""
    try:
        if not supported() or not items:
            return None
        row_h, top = 86, 330
        h = top + 70 + len(items) * row_h + 140
        img = _background(h, (52, 18, 26), (9, 11, 18))
        _glow(img, (W - 140, 110), 220, (229, 28, 45), 55)
        date_short = re.sub(r"\s+امروز.*$", "", str(update_date)).strip() or str(update_date)
        _header(img, "قیمت روز خودرو", "بازار آزاد و کارخانه · ارقام به میلیون تومان", fa(date_short)[:28], ACCENT)
        d = ImageDraw.Draw(img)

        # column boxes (right edge, max width) so no value can run into its neighbour
        name_r, name_w = W - 90, 230
        mk_r, mk_w = W - 410, 250
        fc_r, fc_w = W - 690, 190
        xc = 84
        hy = top + 28
        d.rounded_rectangle([60, top, W - 60, top + 56], radius=18, fill=(40, 22, 30))
        rtl(d, (name_r, hy), "خودرو", font(26), MUTED, "rm")
        rtl(d, (mk_r, hy), "بازار", font(26), MUTED, "rm")
        rtl(d, (fc_r, hy), "کارخانه", font(26), MUTED, "rm")
        d.text((xc, hy), "تغییر", font=font(26), fill=MUTED, anchor="lm")

        y = top + 70
        for i, (label, market, factory, change) in enumerate(items):
            if i % 2 == 0:
                d.rounded_rectangle([60, y, W - 60, y + row_h - 8], radius=16, fill=CARD)
            cy = y + (row_h - 8) / 2
            rtl(d, (name_r, cy), label, _fit(d, label, 30, "bold", name_w), INK, "rm")
            mt = _millions(market) or "—"
            rtl(d, (mk_r, cy), mt, _fit(d, mt, 32, "bold", mk_w), (255, 214, 102), "rm")
            ft = _millions(factory) or "—"
            rtl(d, (fc_r, cy), ft, _fit(d, ft, 26, "regular", fc_w), MUTED, "rm")
            k = _change_kind(change)
            if k:
                col = (52, 211, 120) if k > 0 else (248, 92, 92)
                tri = [(xc, cy + 8), (xc + 18, cy + 8), (xc + 9, cy - 8)] if k > 0 else \
                      [(xc, cy - 8), (xc + 18, cy - 8), (xc + 9, cy + 8)]
                d.polygon(tri, fill=col)
                txt = re.sub(r"[+\-−▲▼]", "", str(change)).strip()
                txt = fa(txt)[:8]
                d.text((xc + 28, cy), txt, font=_fit(d, txt, 24, "bold", 92), fill=col, anchor="lm")
            else:
                d.text((xc, cy), "—", font=font(24, "regular"), fill=MUTED, anchor="lm")
            y += row_h
        _footer(img, h - 110, "قیمت‌ها تقریبی است")
        img.save(out_path, quality=92)
        return out_path
    except Exception as exc:
        print(f"DAILY CARDS: car render failed: {type(exc).__name__}: {exc}", flush=True)
        return None


# ------------------------------------------------------------------ sports
def render_sports(rows, jalali_date, out_path):
    """rows from daily_sports.select(). Returns path or None."""
    try:
        if not supported() or not rows:
            return None
        row_h, top = 128, 330
        h = top + len(rows) * row_h + 150
        img = _background(h, (10, 58, 40), (8, 12, 20))
        _glow(img, (W - 150, 110), 230, (34, 197, 94), 55)
        _header(img, "مسابقات مهم امروز", "ساعت‌ها به وقت تهران", fa(jalali_date), (22, 163, 74))
        d = ImageDraw.Draw(img)
        y = top
        for i, r in enumerate(rows):
            x0, x1 = 60, W - 60
            d.rounded_rectangle([x0, y, x1, y + row_h - 16], radius=22, fill=CARD if i % 2 == 0 else CARD2)
            if r.get("iran"):
                for k, col in enumerate(((35, 159, 64), (240, 240, 240), (218, 0, 0))):
                    d.rectangle([x1 - 8, y + 14 + k * 30, x1 - 2, y + 14 + (k + 1) * 30], fill=col)
            cy = y + (row_h - 16) / 2
            league = r["league"] if r["league"].startswith(r["sport"]) else r["sport"] + " · " + r["league"]
            meta = league + ((" · " + r["stage"]) if r.get("stage") else "")
            rtl(d, (x1 - 28, cy - 30), meta[:60], font(22, "regular"), MUTED, "rm")
            match = f"{r['host']}  –  {r['guest']}"
            f = font(34)
            while tlen(d, match, f) > 640 and f.size > 24:
                f = font(f.size - 2)
            rtl(d, (x1 - 28, cy + 14), match, f, INK, "rm")
            # time / score block on the left
            bx0, bx1 = x0 + 20, x0 + 230
            if r.get("live") or r.get("finished"):
                col = (248, 92, 92) if r.get("live") else (120, 130, 150)
                d.rounded_rectangle([bx0, cy - 40, bx1, cy + 8], radius=16, fill=col)
                d.text(((bx0 + bx1) / 2, cy - 16), fa(r.get("score") or "—"), font=font(30), fill=(255, 255, 255), anchor="mm")
                tag = "زنده" if r.get("live") else "پایان"
                rtl(d, ((bx0 + bx1) / 2, cy + 30), tag, font(20, "regular"), MUTED, "mm")
            else:
                d.rounded_rectangle([bx0, cy - 40, bx1, cy + 8], radius=16, fill=(22, 163, 74))
                d.text(((bx0 + bx1) / 2, cy - 16), fa(r["time"]), font=font(34), fill=(255, 255, 255), anchor="mm")
                if r.get("broadcast"):
                    b = r["broadcast"]
                    bf = font(19, "regular")
                    while tlen(d, b, bf) > 240 and len(b) > 8:
                        b = b[:-2]
                    rtl(d, ((bx0 + bx1) / 2, cy + 30), b, bf, (134, 239, 172), "mm")
            y += row_h
        _footer(img, h - 110, "ساعت‌ها به وقت تهران")
        img.save(out_path, quality=92)
        return out_path
    except Exception as exc:
        print(f"DAILY CARDS: sports render failed: {type(exc).__name__}: {exc}", flush=True)
        return None
