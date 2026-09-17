from PIL import Image, ImageDraw

import main


# Local-only branding: original photo + the established Nabz Khabar watermark.
def enhance_image(input_path, output_path):
    try:
        image = Image.open(input_path).convert("RGBA")
        image = main.resize_for_telegram(image)
        width, height = image.size

        brand = "نبض خبر | NABZ"
        handle = "@NabzKhabarOfficial"
        brand_size = max(16, min(28, int(width * 0.020)))
        handle_size = max(12, min(20, int(width * 0.014)))
        brand_font = main.find_font(brand_size, bold=True)
        handle_font = main.find_font(handle_size, bold=True)
        draw = ImageDraw.Draw(image, "RGBA")

        brand_box = draw.textbbox((0, 0), brand, font=brand_font)
        handle_box = draw.textbbox((0, 0), handle, font=handle_font)
        brand_w = brand_box[2] - brand_box[0]
        brand_h = brand_box[3] - brand_box[1]
        handle_w = handle_box[2] - handle_box[0]
        handle_h = handle_box[3] - handle_box[1]

        margin = max(14, int(width * 0.018))
        gap = max(2, int(width * 0.004))
        content_w = max(brand_w, handle_w)
        content_h = brand_h + gap + handle_h
        x = width - content_w - margin
        y = height - content_h - margin
        pad_x = max(8, int(width * 0.007))
        pad_y = max(5, int(width * 0.004))

        # Same clean bottom-right treatment, now including the channel address.
        draw.rounded_rectangle(
            [x - pad_x, y - pad_y, x + content_w + pad_x, y + content_h + pad_y],
            radius=8,
            fill=(0, 0, 0, 82),
        )
        draw.text((x + 1, y + 1), brand, font=brand_font, fill=(0, 0, 0, 125))
        draw.text((x, y), brand, font=brand_font, fill=(255, 255, 255, 205))

        handle_x = x + (content_w - handle_w)
        handle_y = y + brand_h + gap
        draw.text((handle_x + 1, handle_y + 1), handle, font=handle_font, fill=(0, 0, 0, 125))
        draw.text((handle_x, handle_y), handle, font=handle_font, fill=(255, 255, 255, 190))

        image.convert("RGB").save(output_path, "JPEG", quality=90, optimize=True)
        return output_path

    except Exception as exc:
        print(f"Graphics enhancement error: {exc}")
        return input_path


main.add_watermark = enhance_image
