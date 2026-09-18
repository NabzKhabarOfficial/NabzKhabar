import os
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

CHANNEL_URL = "https://t.me/NabzKhabarOfficial"
BRAND = "نبض خبر | NABZ"
HANDLE = "@NabzKhabarOfficial"
FONT_PATH = "Vazirmatn-Bold.ttf"


def _font(size):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()


def _watermark_image(width, height):
    # Glass-style bottom-right brand: translucent dark panel, soft white type,
    # channel URL clearly visible. Scale with media dimensions.
    scale = max(1.0, min(width, height) / 1080.0)
    brand_size = max(24, int(30 * scale))
    url_size = max(20, int(24 * scale))
    pad_x = max(18, int(22 * scale))
    pad_y = max(12, int(14 * scale))
    gap = max(5, int(7 * scale))

    brand_font = _font(brand_size)
    url_font = _font(url_size)

    probe = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    d = ImageDraw.Draw(probe)
    b1 = d.textbbox((0, 0), BRAND, font=brand_font)
    b2 = d.textbbox((0, 0), HANDLE, font=url_font)
    content_w = max(b1[2] - b1[0], b2[2] - b2[0])
    content_h = (b1[3] - b1[1]) + gap + (b2[3] - b2[1])

    box_w = content_w + 2 * pad_x
    box_h = content_h + 2 * pad_y
    canvas = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas, "RGBA")

    radius = max(14, int(18 * scale))
    draw.rounded_rectangle(
        (0, 0, box_w - 1, box_h - 1),
        radius=radius,
        fill=(8, 12, 18, 112),
        outline=(255, 255, 255, 82),
        width=max(1, int(1.5 * scale)),
    )

    # Tiny highlight line for a premium glass effect.
    draw.rounded_rectangle(
        (pad_x, 3, box_w - pad_x, max(4, int(5 * scale))),
        radius=3,
        fill=(255, 255, 255, 55),
    )

    x1 = (box_w - (b1[2] - b1[0])) // 2 - b1[0]
    y1 = pad_y - b1[1]
    x2 = (box_w - (b2[2] - b2[0])) // 2 - b2[0]
    y2 = pad_y + (b1[3] - b1[1]) + gap - b2[1]

    # Subtle shadow + crisp white text.
    draw.text((x1 + 2, y1 + 2), BRAND, font=brand_font, fill=(0, 0, 0, 170))
    draw.text((x1, y1), BRAND, font=brand_font, fill=(255, 255, 255, 238))
    draw.text((x2 + 2, y2 + 2), HANDLE, font=url_font, fill=(0, 0, 0, 160))
    draw.text((x2, y2), HANDLE, font=url_font, fill=(235, 248, 255, 235))

    return canvas


def add_watermark(input_path, output_path):
    try:
        # Preserve orientation and never resize/crop the source image.
        source = Image.open(input_path)
        source = ImageOps.exif_transpose(source)
        width, height = source.size

        # Very small images do not have enough safe area for branding.
        if width < 420 or height < 300:
            print("V13 WATERMARK: image too small; original preserved.")
            return input_path

        image = source.convert("RGBA")
        wm = _watermark_image(width, height)
        margin = max(16, int(min(width, height) * 0.018))

        # Hard safety limits: watermark stays a small unobtrusive part of the image.
        max_w = int(width * 0.34)
        max_h = int(height * 0.22)
        if wm.width > max_w or wm.height > max_h:
            print("V13 WATERMARK: unsafe size for image; original preserved.")
            return input_path

        x = width - wm.width - margin
        y = height - wm.height - margin
        if x < 0 or y < 0:
            print("V13 WATERMARK: insufficient safe area; original preserved.")
            return input_path

        image.alpha_composite(wm, (x, y))

        # High-quality output with no resizing or cropping.
        image.convert("RGB").save(
            output_path,
            "JPEG",
            quality=95,
            optimize=True,
            subsampling=0,
        )
        return output_path
    except Exception as exc:
        print(f"V13 branding image error: {exc}")
        return input_path

def _probe_duration(path):
    # Prefer container duration, then video-stream duration.
    for args in (
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=duration", "-of",
         "default=noprint_wrappers=1:nokey=1", path],
    ):
        try:
            r = subprocess.run(args, capture_output=True, text=True, timeout=15)
            value = float((r.stdout or "").strip())
            if value > 0:
                return max(1, int(round(value)))
        except Exception:
            pass
    return 0


def _probe_dimensions(path):
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", path],
            capture_output=True, text=True, timeout=15,
        )
        w, h = (r.stdout or "").strip().split("x")
        return int(w), int(h)
    except Exception:
        return 0, 0


def _brand_video(input_path):
    # Use a real transparent PNG overlay so Persian text stays correctly shaped
    # by Pillow, while ffmpeg handles the video compositing.
    try:
        width, height = _probe_dimensions(input_path)
        if not width or not height:
            return input_path

        wm = _watermark_image(width, height)
        margin = max(16, int(min(width, height) * 0.018))
        x = max(0, width - wm.width - margin)
        y = max(0, height - wm.height - margin)

        with tempfile.TemporaryDirectory() as td:
            overlay = os.path.join(td, "nabz_watermark.png")
            output = os.path.join(td, "nabz_branded.mp4")
            wm.save(overlay, "PNG")

            cmd = [
                "ffmpeg", "-y",
                "-i", input_path,
                "-i", overlay,
                "-filter_complex", f"[0:v][1:v]overlay={x}:{y}:format=auto[v]",
                "-map", "[v]",
                "-map", "0:a?",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "23",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "128k",
                "-movflags", "+faststart",
                output,
            ]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=150)
            if r.returncode != 0 or not os.path.exists(output):
                print(f"V13 video watermark failed: {(r.stderr or '')[-1000:]}")
                return input_path

            # Copy out of TemporaryDirectory before it is removed.
            final_path = input_path + ".nabz.mp4"
            with open(output, "rb") as src, open(final_path, "wb") as dst:
                dst.write(src.read())
            return final_path
    except Exception as exc:
        print(f"V13 video branding error: {exc}")
        return input_path


def send_video(path, caption):
    # Telegram's sendVideo duration is an integer number of seconds. We
    # explicitly calculate it from the final (watermarked) file and send it.
    branded = _brand_video(path)
    # Never let branding push a valid video over Telegram's configured limit.
    if branded != path and os.path.getsize(branded) > 49 * 1024 * 1024:
        print("V13 VIDEO: branded file exceeded 49 MB; using original media.")
        try:
            os.remove(branded)
        except Exception:
            pass
        branded = path

    duration = _probe_duration(branded)
    width, height = _probe_dimensions(branded)

    try:
        import v13_standalone as core

        with open(branded, "rb") as video:
            data = {
                "chat_id": core.CHANNEL_ID,
                "caption": caption,
                "supports_streaming": "true",
            }
            if duration > 0:
                data["duration"] = str(duration)
            if width and height:
                data["width"] = str(width)
                data["height"] = str(height)

            response = core.SESSION.post(
                core.telegram_api("sendVideo"),
                data=data,
                files={"video": video},
                timeout=120,
            )

        if response.ok:
            print(f"V13 VIDEO PUBLISHED | duration={duration}s | {width}x{height}")
            return True

        print(f"V13 sendVideo failed: {response.status_code} {response.text[:500]}")
        return False
    except Exception as exc:
        print(f"V13 sendVideo error: {exc}")
        return False
    finally:
        if branded != path:
            try:
                os.remove(branded)
            except Exception:
                pass


def build_caption(title, body):
    title = str(title or "").strip()
    body = str(body or "").strip()
    parts = [f"📰 {title}"]
    if body:
        parts.append(body)
    parts.append("#نبض_خبر")
    parts.append(f"🔗 کانال نبض خبر: {CHANNEL_URL}")
    return "\n\n".join(parts)


def install(core):
    core.add_watermark = add_watermark
    core.send_video = send_video
    core.build_caption = build_caption
