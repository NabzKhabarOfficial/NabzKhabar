from PIL import Image, ImageDraw, ImageFilter

import main


# Free, local-only visual upgrade. The v11 news engine, duplicate logic,
# captions, sources and scheduling remain untouched.
BRAND = "نبض خبر | NABZ"
ACCENT = (38, 198, 218, 255)
DARK = (8, 16, 28, 235)
WHITE = (255, 255, 255, 245)
SOFT_WHITE = (235, 245, 248, 220)


def _fit_brand_font(size):
    return main.find_font(size, bold=True)


def enhance_image(input_path, output_path):
    try:
        image = Image.open(input_path).convert("RGBA")
        image = main.resize_for_telegram(image)
        width, height = image.size

        # Preserve the original photograph; only add a restrained branded overlay.
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay, "RGBA")

        band_h = max(78, int(height * 0.105))
        draw.rectangle([0, 0, width, band_h], fill=DARK)
        draw.rectangle([0, band_h - 5, width, band_h], fill=ACCENT)

        # Soft dark fade at the bottom for the watermark area.
        fade_h = max(90, int(height * 0.16))
        for i in range(fade_h):
            alpha = int(150 * (i / fade_h))
            y = height - fade_h + i
            draw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))

        brand_size = max(24, min(54, int(width * 0.036)))
        small_size = max(16, min(30, int(width * 0.020)))
        brand_font = _fit_brand_font(brand_size)
        small_font = _fit_brand_font(small_size)

        # Left brand block.
        x = max(22, int(width * 0.028))
        y = max(16, int(band_h * 0.20))
        draw.rounded_rectangle(
            [x - 12, y - 7, x + int(width * 0.30), y + brand_size + 12],
            radius=16,
            fill=(255, 255, 255, 22),
            outline=(255, 255, 255, 35),
            width=1,
        )
        draw.text((x, y), BRAND, font=brand_font, fill=WHITE)

        # Small editorial label on the right.
        label = "NEWS • 24/7"
        bbox = draw.textbbox((0, 0), label, font=small_font)
        tw = bbox[2] - bbox[0]
        draw.text((width - tw - x, y + 5), label, font=small_font, fill=SOFT_WHITE)

        # Thin brand mark at the bottom-left.
        mark_w = max(110, int(width * 0.13))
        mark_h = max(5, int(height * 0.006))
        draw.rounded_rectangle(
            [x, height - int(height * 0.055), x + mark_w, height - int(height * 0.055) + mark_h],
            radius=mark_h,
            fill=ACCENT,
        )

        image = Image.alpha_composite(image, overlay)

        # Keep the existing watermark identity, but make it cleaner and slightly stronger.
        watermark = "نبض خبر | NABZ"
        wm_size = max(18, min(32, int(width * 0.022)))
        wm_font = _fit_brand_font(wm_size)
        draw = ImageDraw.Draw(image, "RGBA")
        bbox = draw.textbbox((0, 0), watermark, font=wm_font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        margin = max(18, int(width * 0.022))
        wx = width - tw - margin
        wy = height - th - margin

        draw.rounded_rectangle(
            [wx - 12, wy - 7, wx + tw + 12, wy + th + 7],
            radius=14,
            fill=(8, 16, 28, 185),
            outline=(38, 198, 218, 135),
            width=2,
        )
        draw.text((wx + 1, wy + 1), watermark, font=wm_font, fill=(0, 0, 0, 130))
        draw.text((wx, wy), watermark, font=wm_font, fill=WHITE)

        image = image.convert("RGB")
        image.save(output_path, "JPEG", quality=92, optimize=True)
        return output_path

    except Exception as exc:
        print(f"Graphics enhancement error: {exc}")
        return input_path


# Replace only the image decoration function. Everything else stays v11.
main.add_watermark = enhance_image
