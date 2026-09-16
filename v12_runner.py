import re

SOURCE = "main.py"


def patch_v12(source):
    original = source

    source = source.replace(
        "# NABZ KHABAR BOT v11",
        "# NABZ KHABAR BOT v12",
        1,
    )
    source = source.replace(
        'print("NABZ KHABAR BOT v11")',
        'print("NABZ KHABAR BOT v12")',
        1,
    )

    old_phrases = '''    "براساس اعلام",\n]'''
    new_phrases = '''    "براساس اعلام",\n    "روابط عمومی",\n    "روابط‌عمومی",\n    "در اطلاعیه ای",\n    "در اطلاعیه‌ای",\n    "در بیانیه ای",\n    "در بیانیه‌ای",\n]'''
    if old_phrases not in source:
        raise RuntimeError("v12 anchor SOURCE_PHRASES not found")
    source = source.replace(old_phrases, new_phrases, 1)

    old_clean_end = '''    text = re.sub(\n        r"\\+\\s*(فیلم|ویدئو|ویدیو|عکس|تصاویر)\\s*$",\n        "",\n        text,\n        flags=re.I\n    )\n\n    text = normalize_space(\n        text\n    )\n\n    return text[:6000]'''
    new_clean_end = '''    text = re.sub(\n        r"\\+\\s*(فیلم|ویدئو|ویدیو|عکس|تصاویر)\\s*$",\n        "",\n        text,\n        flags=re.I\n    )\n\n    # Remove common PR / promotional boilerplate.\n    promotional_patterns = [\n        r"برای کسب اطلاعات بیشتر",\n        r"جهت کسب اطلاعات بیشتر",\n        r"برای خرید",\n        r"جهت خرید",\n        r"ثبت ?نام کنید",\n        r"همین حالا",\n        r"کلیک کنید",\n        r"لینک زیر",\n        r"با ما همراه باشید",\n        r"ما را دنبال کنید",\n        r"اسپانسر",\n        r"تبلیغات",\n    ]\n\n    for pattern in promotional_patterns:\n        text = re.sub(pattern, "", text, flags=re.I)\n\n    # Remove dateline / attribution fragments left after source cleanup.\n    text = re.sub(\n        r"^(?:[آ-یA-Za-z]+\\s*){1,4}[,:-]\\s*",\n        "",\n        text,\n        count=1\n    )\n\n    # Repair repeated punctuation and spacing.\n    text = re.sub(r"[ ]{2,}", " ", text)\n    text = re.sub(r"([،,:؛])\\1+", r"\\1", text)\n    text = re.sub(r"([.!؟])\\1+", r"\\1", text)\n    text = re.sub(r"\\s+([،,:؛.!؟])", r"\\1", text)\n    text = re.sub(r"([،,:؛])(?=[آ-یA-Za-z])", r"\\1 ", text)\n\n    text = normalize_space(\n        text\n    )\n\n    return text[:6000]'''
    if old_clean_end not in source:
        raise RuntimeError("v12 anchor clean_content not found")
    source = source.replace(old_clean_end, new_clean_end, 1)

    old_title_end = '''    title = re.sub(\n        r"\\s*\\+\\s*(فیلم|ویدئو|ویدیو|عکس|تصاویر)\\s*$",\n        "",\n        title,\n        flags=re.I\n    )\n\n    return normalize_space(\n        title\n    )[:180]'''
    new_title_end = '''    title = re.sub(\n        r"\\s*\\+\\s*(فیلم|ویدئو|ویدیو|عکس|تصاویر)\\s*$",\n        "",\n        title,\n        flags=re.I\n    )\n\n    # Remove repeated urgency / source punctuation artifacts.\n    title = re.sub(r"(?:^|\\s)(فوری)(?:\\s+فوری)+", r" \\1", title)\n    title = re.sub(r"\\s*[|｜]+\\s*", " - ", title)\n    title = re.sub(r"\\s*[-–—:]\\s*$", "", title)\n    title = re.sub(r"[.!؟]+$", "", title)\n    title = re.sub(r"\\s{2,}", " ", title)\n\n    return normalize_space(\n        title\n    )[:180]'''
    if old_title_end not in source:
        raise RuntimeError("v12 anchor clean_title not found")
    source = source.replace(old_title_end, new_title_end, 1)

    old_caption = '''def build_caption(\n    title,\n    body\n):\n\n    title = clean_title(\n        title\n    )\n\n    body = enforce_short_summary(\n        body\n    )\n\n    if body:\n\n        return (\n            f"📰 {title}\\n\\n"\n            f"{body}\\n\\n"\n            f"#نبض_خبر"\n        )\n\n    return (\n        f"📰 {title}\\n\\n"\n        f"#نبض_خبر"\n    )'''
    new_caption = '''def build_caption(\n    title,\n    body\n):\n\n    title = clean_title(\n        title\n    )\n\n    body = enforce_short_summary(\n        body\n    )\n\n    if body:\n\n        return (\n            f"📰 {title}\\n\\n"\n            f"{body}\\n\\n"\n            f"📡 @NabzKhabarOfficial\\n"\n            f"#نبض_خبر"\n        )\n\n    return (\n        f"📰 {title}\\n\\n"\n        f"📡 @NabzKhabarOfficial\\n"\n        f"#نبض_خبر"\n    )'''
    if old_caption not in source:
        raise RuntimeError("v12 anchor build_caption not found")
    source = source.replace(old_caption, new_caption, 1)

    old_prompt = '''3. نام رسانه، نام خبرگزاری، لینک، عبارت «به گزارش»، عبارت‌های تبلیغاتی و منبع را حذف کن.\n4. اگر متن ناقص است، چیزی را حدس نزن.\n5. لحن کاملاً خبری، خنثی و حرفه‌ای باشد.\n6. از اغراق، کلیک‌بیت و نظر شخصی خودداری کن.\n7. اگر عنوان اصلی مناسب است، آن را بی‌دلیل تغییر نده.\n8. فقط اطلاعات موجود در متن را استفاده کن.'''
    new_prompt = '''3. نام رسانه، نام خبرگزاری، لینک، عبارت «به گزارش»، تاریخ‌گذاری ابتدای خبر، عبارت‌های روابط عمومی، بیانیه و اطلاعیه، متن تبلیغاتی و فراخوان‌های تبلیغاتی را حذف کن.\n4. اگر متن ناقص است، چیزی را حدس نزن.\n5. لحن کاملاً خبری، خنثی و حرفه‌ای باشد.\n6. از اغراق، کلیک‌بیت و نظر شخصی خودداری کن.\n7. اگر عنوان اصلی مناسب است، آن را بی‌دلیل تغییر نده.\n8. فقط اطلاعات موجود در متن را استفاده کن.\n9. هیچ نام، عدد، علت، نقل‌قول یا جزئیات جدیدی اختراع نکن.\n10. متن را از عبارت‌های تبلیغاتی، روابط عمومی و معرفی خدمات پاک نگه دار.'''
    if old_prompt not in source:
        raise RuntimeError("v12 anchor Gemini prompt not found")
    source = source.replace(old_prompt, new_prompt, 1)

    if source == original:
        raise RuntimeError("v12 made no changes")

    return source


def main():
    with open(SOURCE, "r", encoding="utf-8") as f:
        source = f.read()

    patched = patch_v12(source)

    # Persist v12 so the repository itself becomes v12 after this run.
    with open(SOURCE, "w", encoding="utf-8") as f:
        f.write(patched)

    print("NABZ KHABAR v12 patch applied successfully")

    namespace = {"__name__": "__main__", "__file__": SOURCE}
    exec(compile(patched, SOURCE, "exec"), namespace)


if __name__ == "__main__":
    main()
