from PIL import Image, ImageDraw

import main


# Simple local-only branding: original photo + the previously used watermark.

def enhance_image(input_path, output_path):
    try:
        image = Image.open(input_path).convert("RGBA")
        image = main.resize_for_telegram(image)
        width, height = image.size

        watermark = main.WATERMARK_TEXT
        font_size = max(14, min(24, int(width * 0.017)))
        font = main.find_font(font_size, bold=True)
        draw = ImageDraw.Draw(image, "RGBA")

        bbox = draw.textbbox((0, 0), watermark, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        margin = max(12, int(width * 0.015))
        x = width - tw - margin
        y = height - th - margin

        # Previously used watermark style: small, unobtrusive, bottom-right.
        draw.rounded_rectangle(
            [x - 6, y - 3, x + tw + 6, y + th + 3],
            radius=5,
            fill=(0, 0, 0, 75),
        )
        draw.text((x + 1, y + 1), watermark, font=font, fill=(0, 0, 0, 120))
        draw.text((x, y), watermark, font=font, fill=(255, 255, 255, 190))

        image.convert("RGB").save(
            output_path,
            "JPEG",
            quality=90,
            optimize=True,
        )
        return output_path

    except Exception as exc:
        print(f"Graphics enhancement error: {exc}")
        return input_path


main.add_watermark = enhance_image
