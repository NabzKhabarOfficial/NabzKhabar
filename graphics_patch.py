from PIL import Image, ImageDraw

import main

BRAND = "نبض خبر | NABZ"
BASE_ACCENT = (38, 198, 218, 255)
DARK = (8, 16, 28, 238)
WHITE = (255, 255, 255, 248)
SOFT_WHITE = (235, 245, 248, 225)

CATEGORY_STYLES = [
    (("دلار", "طلا", "سکه", "بورس", "ارز", "اقتصاد", "قیمت", "بازار", "کریپتو", "بیت کوین"), "MARKET", (255, 193, 7, 255)),
    (("فوتبال", "ورزش", "لیگ", "جام جهانی", "استقلال", "پرسپولیس", "آرسنال", "رئال", "بارسلونا"), "SPORT", (76, 175, 80, 255)),
    (("هوش مصنوعی", "فناوری", "تکنولوژی", "موبایل", "گوشی", "سامسونگ", "اپل", "آیفون", "اندروید", "لپ تاپ", "پردازنده"), "TECH", (156, 39, 176, 255)),
    (("خودرو", "ماشین", "خودروساز", "خودروسازی", "خودروی", "اتومبیل", "موتورسیکلت"), "AUTO", (255, 87, 34, 255)),
    (("زلزله", "انفجار", "حمله", "موشک", "جنگ", "آتش سوزی", "آتش‌سوزی", "سقوط", "فوری", "خبر فوری"), "BREAKING", (244, 67, 54, 255)),
]


def _fit_brand_font(size):
    return main.find_font(size, bold=True)


def _safe_size(width, height):
    return width >= 320 and height >= 240


def _category_style(title):
    value = str(title or "").lower()
    for keywords, label, accent in CATEGORY_STYLES:
        if any(keyword.lower() in value for keyword in keywords):
            return label, accent
    return "NEWS", BASE_ACCENT


def enhance_image(input_path, output_path):
    """Free local category-aware newsroom treatment; failures never block publishing."""
    try:
        image = Image.open(input_path).convert("RGBA")
        image = main.resize_for_telegram(image)
        width, height = image.size

        if not _safe_size(width, height):
            image.convert("RGB").save(output_path, "JPEG", quality=92, optimize=True)
            return output_path

        title = getattr(main, "CURRENT_GRAPHICS_TITLE", "")
        category_label, accent = _category_style(title)

        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay, "RGBA")

        band_h = max(72, min(150, int(height * 0.105)))
        draw.rectangle([0, 0, width, band_h], fill=DARK)
        draw.rectangle([0, band_h - 4, width, band_h], fill=accent)

        fade_h = max(80, min(260, int(height * 0.18)))
        for i in range(fade_h):
            progress = i / max(1, fade_h - 1)
            alpha = int(125 * progress)
            y = height - fade_h + i
            draw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))

        x = max(18, int(width * 0.028))
        brand_size = max(22, min(52, int(width * 0.034)))
        small_size = max(15, min(28, int(width * 0.019)))
        brand_font = _fit_brand_font(brand_size)
        small_font = _fit_brand_font(small_size)
        y = max(13, int(band_h * 0.19))

        brand_box_right = min(width - x, x + int(width * 0.34))
        draw.rounded_rectangle([x - 10, y - 6, brand_box_right, y + brand_size + 10], radius=14, fill=(255, 255, 255, 20), outline=(255, 255, 255, 38), width=1)
        draw.text((x, y), BRAND, font=brand_font, fill=WHITE)

        label = category_label if category_label != "NEWS" else "NEWS  •  24/7"
        bbox = draw.textbbox((0, 0), label, font=small_font)
        tw = bbox[2] - bbox[0]
        draw.text((width - tw - x, y + 4), label, font=small_font, fill=SOFT_WHITE)

        mark_w = max(90, min(220, int(width * 0.13)))
        mark_h = max(4, min(9, int(height * 0.006)))
        mark_y = height - max(26, int(height * 0.055))
        draw.rounded_rectangle([x, mark_y, x + mark_w, mark_y + mark_h], radius=mark_h, fill=accent)

        image = Image.alpha_composite(image, overlay)

        watermark = BRAND
        wm_size = max(17, min(31, int(width * 0.021)))
        wm_font = _fit_brand_font(wm_size)
        draw = ImageDraw.Draw(image, "RGBA")
        bbox = draw.textbbox((0, 0), watermark, font=wm_font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        margin = max(16, int(width * 0.021))
        wx = max(8, width - tw - margin)
        wy = max(8, height - th - margin)

        draw.rounded_rectangle([wx - 11, wy - 6, wx + tw + 11, wy + th + 6], radius=12, fill=(8, 16, 28, 190), outline=accent, width=2)
        draw.text((wx + 1, wy + 1), watermark, font=wm_font, fill=(0, 0, 0, 120))
        draw.text((wx, wy), watermark, font=wm_font, fill=WHITE)

        image.convert("RGB").save(output_path, "JPEG", quality=92, optimize=True)
        return output_path

    except Exception as exc:
        print(f"Graphics enhancement error: {exc}")
        return input_path


main.add_watermark = enhance_image
