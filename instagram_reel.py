"""NABZ Instagram Reels: turn a news photo + headline into an 8 second reel.

The reel is a 1080x1920 vertical video: the news photo slowly zooms (Ken
Burns) over a blurred backdrop, the NABZ brand bar and headline fade in, and
a soft heartbeat sound plays underneath (the "pulse" of NABZ). Reels reach
the Explore page far more often than photos.

Everything is fail-safe: render_reel() returns None when anything is missing
(ffmpeg, font, text shaping) so the caller can post the classic photo.
"""

import inspect
import os
import re
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, features

W, H = 1080, 1920
FPS = 30
DURATION = 8
FONT_CANDIDATES = ("Vazirmatn-Bold.ttf", "/usr/local/share/fonts/google/vazirmatn/Vazirmatn[wght].ttf")
ACCENT = (229, 28, 45)
BRAND_FA = "نبض خبر"
HANDLE = "@NabzKhabarOfficial"
CTA = "خبرهای لحظه‌ای در تلگرام نبض خبر"
# Instagram's Reels UI covers the bottom ~22% and a column on the right.
SAFE_RIGHT = 150
SAFE_LEFT = 70


def _font_path():
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    return ""


def _font(size):
    font = ImageFont.truetype(_font_path(), size)
    try:
        font.set_variation_by_name("Bold")
    except Exception:
        pass
    return font


def supported():
    try:
        return bool(shutil.which("ffmpeg")) and bool(_font_path()) and bool(features.check("raqm"))
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
    pts = [(0, 0), (0.30, 0), (0.38, -0.25), (0.46, 0), (0.52, 0.0),
           (0.58, -1.0), (0.66, 0.85), (0.72, 0), (0.80, -0.2), (0.86, 0), (1.0, 0)]
    draw.line([(x_right - p[0] * w, y_mid + p[1] * h / 2) for p in pts],
              fill=ACCENT + (255,), width=width, joint="curve")


def _base(photo):
    """Blurred, darkened full-screen backdrop."""
    bg = ImageOps.fit(photo, (W, H), Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(28))
    dark = Image.new("RGB", (W, H), (6, 8, 14))
    return Image.blend(bg, dark, 0.45)


FG_TOP = 290
FG_MAX_H = 700


def _foreground(photo):
    """The photo itself, full width, at most FG_MAX_H tall (center crop)."""
    scale = W / photo.width
    h = max(1, int(photo.height * scale))
    photo = photo.resize((W, h), Image.LANCZOS)
    if h > FG_MAX_H:
        top = (h - FG_MAX_H) // 2
        photo = photo.crop((0, top, W, top + FG_MAX_H))
    return photo


def _overlay(title, topic, lead, fg_bottom):
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    top_shade = Image.new("RGBA", (W, 260), (0, 0, 0, 0))
    td = ImageDraw.Draw(top_shade)
    for y in range(260):
        td.line([(0, y), (W, y)], fill=(6, 8, 14, int(200 * (1 - y / 260))))
    ov.alpha_composite(top_shade, (0, 0))
    brand = _font(54)
    right = W - SAFE_LEFT
    d.text((right, 150), BRAND_FA, font=brand, fill=(255, 255, 255, 255), anchor="rm", direction="rtl")
    bw = d.textlength(BRAND_FA, font=brand, direction="rtl")
    _pulse(d, right - bw - 24, 150, 170, 52, 6)
    d.text((SAFE_LEFT, 150), HANDLE, font=_font(30), fill=(215, 220, 230, 235), anchor="lm")

    # The lead is a second editorial layer, so this is not merely a photo with a resized caption.
    max_w = W - SAFE_LEFT - SAFE_RIGHT
    size, lines = 70, []
    while True:
        tfont = _font(size)
        lines = _wrap(d, title, tfont, max_w)
        if len(lines) <= 3 or size <= 52:
            break
        size -= 4
    lines = lines[:4]
    line_h = int(size * 1.45)
    block_h = 90 + len(lines) * line_h + 110
    y0 = min(fg_bottom - 50, 1500 - block_h)
    shade_top = y0 - 170
    shade = Image.new("RGBA", (W, H - shade_top), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    for y in range(H - shade_top):
        t = min(1.0, y / 170)
        sd.line([(0, y), (W, y)], fill=(6, 8, 14, int(225 * t)))
    ov.alpha_composite(shade, (0, shade_top))
    rx = W - SAFE_RIGHT
    pill_font = _font(34)
    pw = d.textlength(topic, font=pill_font, direction="rtl")
    d.rounded_rectangle((rx - pw - 44, y0, rx, y0 + 62), radius=31, fill=ACCENT + (245,))
    d.text((rx - 22, y0 + 31), topic, font=pill_font, fill=(255, 255, 255, 255), anchor="rm", direction="rtl")
    y = y0 + 90
    for line in lines:
        d.text((rx + 3, y + 3), line, font=tfont, fill=(0, 0, 0, 160), anchor="ra", direction="rtl")
        d.text((rx, y), line, font=tfont, fill=(255, 255, 255, 255), anchor="ra", direction="rtl")
        y += line_h
    y += 24
    d.rounded_rectangle((rx - 110, y, rx, y + 8), radius=4, fill=ACCENT + (255,))
    lead_font = _font(32)
    lead_lines = _wrap(d, lead, lead_font, max_w)
    for line in lead_lines[:2]:
        y += 52
        d.text((rx, y), line, font=lead_font, fill=(225, 230, 238, 240), anchor="ra", direction="rtl")
    d.text((rx, y + 50), CTA, font=_font(34), fill=(225, 230, 238, 240), anchor="rm", direction="rtl")
    return ov


AUDIO = (
    "aevalsrc='0.55*sin(2*PI*52*t)*exp(-16*mod(t,0.9))"
    "+0.38*sin(2*PI*46*t)*exp(-16*mod(t-0.24,0.9))*gte(mod(t,0.9),0.24)"
    "+0.035*sin(2*PI*220*t)*(0.6+0.4*sin(2*PI*0.25*t))':s=44100:d={d}"
)

TOPICS = (
    ("نظامی", ("حمله", "موشک", "پهپاد", "بمباران", "ارتش", "نظامی", "ناو", "تفنگدار", "جنگ", "پایگاه", "یورش", "سپاه")),
    ("حادثه", ("انفجار", "آتش سوزی", "سقوط", "زلزله", "سیل", "تصادف", "مصدوم", "حادثه")),
    ("ورزش", ("فوتبال", "والیبال", "کشتی گیر", "کشتی آزاد", "تیم ملی", "قهرمان", "مدال", "تکواندو", "المپیک")),
    ("قضایی", ("دادگاه", "اعدام", "دیوان", "محاکمه", "بازداشت", "زندان")),
    ("سیاست", ("وزیر", "سفارت", "سفیر", "دیپلماتیک", "مذاکره", "رئیس جمهور", "مجلس", "انتخابات", "تحریم", "سازمان ملل")),
    ("اقتصاد", ("دلار", "طلا", "سکه", "بورس", "تورم", "اقتصاد", "بازار", "نفت", "صادرات", "قیمت")),
    ("فناوری", ("هوش مصنوعی", "فناوری", "گوشی", "اینترنت", "سایبری", "ماهواره")),
)


def topic_of(title, category=""):
    text = re.sub(r"\s+", " ", str(title or "").replace("\u200c", " "))
    for name, words in TOPICS:
        if any(w in text for w in words):
            return name
    return {"ورزش": "ورزش", "فناوری": "فناوری"}.get(category, "خبر")


def render_reel(photo_path, title, topic, out_dir, lead=""):
    """Return (video_path, cover_path) or None."""
    if not supported() or not title:
        return None
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base_p, fg_p, ov_p = out_dir / "base.jpg", out_dir / "fg.jpg", out_dir / "ov.png"
    video_p, cover_p = out_dir / "reel.mp4", out_dir / "cover.jpg"
    try:
        with Image.open(photo_path) as im:
            photo = ImageOps.exif_transpose(im).convert("RGB")
        if photo.width < 320 or photo.height < 240:
            return None
        _base(photo).save(base_p, quality=92)
        fg = _foreground(photo)
        fg.save(fg_p, quality=94)
        fg_y = FG_TOP
        ov = _overlay(title, topic or "خبر", lead or "خلاصه خبر را در چند ثانیه ببینید", fg_y + fg.height)
        ov.save(ov_p)

        cover = Image.open(base_p).convert("RGBA")
        cover.paste(fg, (0, fg_y))
        cover.alpha_composite(ov)
        cover.convert("RGB").save(cover_p, quality=92)

        frames = FPS * DURATION
        zoom = f"zoompan=z='min(1+0.10*on/{frames},1.10)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{fg.height}:fps={FPS}"
        graph = (
            f"[1:v]scale={W * 2}:-2,{zoom}[fg];"
            f"[0:v][fg]overlay=0:{fg_y}[bg];"
            f"[2:v]format=rgba,fade=in:st=0.4:d=0.7:alpha=1[ov];"
            f"[bg][ov]overlay=0:0,format=yuv420p[v]"
        )
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-loop", "1", "-framerate", str(FPS), "-t", str(DURATION), "-i", str(base_p),
            "-loop", "1", "-framerate", str(FPS), "-t", str(DURATION), "-i", str(fg_p),
            "-loop", "1", "-framerate", str(FPS), "-t", str(DURATION), "-i", str(ov_p),
            "-f", "lavfi", "-i", AUDIO.format(d=DURATION),
            "-filter_complex", graph, "-map", "[v]", "-map", "3:a",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "128k", "-af", "afade=t=out:st=7:d=1,volume=0.9",
            "-t", str(DURATION), "-movflags", "+faststart", str(video_p),
        ]
        subprocess.run(cmd, check=True, timeout=180)
        if not video_p.exists() or video_p.stat().st_size < 10_000:
            return None
        return video_p, cover_p
    except Exception as exc:
        print(f"IG REEL: render failed ({type(exc).__name__}: {exc})")
        return None
    finally:
        for p in (base_p, fg_p, ov_p):
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass


def patch_instagrapi_analyzer(width=W, height=H, duration=DURATION):
    """instagrapi analyses clips with moviepy; we already know the numbers,
    so answer that step ourselves (no moviepy dependency)."""
    try:
        import instagrapi.mixins.clip as clipmod
        src = inspect.getsource(clipmod)
        m = re.search(r"\n\s*([\w ,()]+?)=\s*analyze_video\(", src)
        if not m or not hasattr(clipmod, "analyze_video"):
            return False
        names = [n.strip(" ()") for n in m.group(1).split(",") if n.strip(" ()")]
        if not names or set(names) - {"thumbnail", "width", "height", "duration"}:
            return False

        def analyze_video(path, thumbnail=None, *args, **kwargs):
            values = {"thumbnail": thumbnail, "width": width, "height": height, "duration": float(duration)}
            return tuple(values[n] for n in names)

        clipmod.analyze_video = analyze_video
        return True
    except Exception as exc:
        print(f"IG REEL: analyzer patch skipped ({type(exc).__name__})")
        return False
