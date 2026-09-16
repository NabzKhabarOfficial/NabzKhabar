import re

SOURCE = "main.py"


def patch_v12(source):
    original = source

    # --------------------------------------------------------
    # Existing v12 patching logic (kept for compatibility).
    # --------------------------------------------------------
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
    if old_phrases in source:
        source = source.replace(old_phrases, new_phrases, 1)

    old_clean_end = '''    text = re.sub(\n        r"\\+\\s*(فیلم|ویدئو|ویدیو|عکس|تصاویر)\\s*$",\n        "",\n        text,\n        flags=re.I\n    )\n\n    text = normalize_space(\n        text\n    )\n\n    return text[:6000]'''
    new_clean_end = '''    text = re.sub(\n        r"\\+\\s*(فیلم|ویدئو|ویدیو|عکس|تصاویر)\\s*$",\n        "",\n        text,\n        flags=re.I\n    )\n\n    # Remove common PR / promotional boilerplate.\n    promotional_patterns = [\n        r"برای کسب اطلاعات بیشتر",\n        r"جهت کسب اطلاعات بیشتر",\n        r"برای خرید",\n        r"جهت خرید",\n        r"ثبت ?نام کنید",\n        r"همین حالا",\n        r"کلیک کنید",\n        r"لینک زیر",\n        r"با ما همراه باشید",\n        r"ما را دنبال کنید",\n        r"اسپانسر",\n        r"تبلیغات",\n    ]\n\n    for pattern in promotional_patterns:\n        text = re.sub(pattern, "", text, flags=re.I)\n\n    # Remove dateline / attribution fragments left after source cleanup.\n    text = re.sub(\n        r"^(?:[آ-یA-Za-z]+\\s*){1,4}[,:-]\\s*",\n        "",\n        text,\n        count=1\n    )\n\n    # Repair repeated punctuation and spacing.\n    text = re.sub(r"[ ]{2,}", " ", text)\n    text = re.sub(r"([،,:؛])\\1+", r"\\1", text)\n    text = re.sub(r"([.!؟])\\1+", r"\\1", text)\n    text = re.sub(r"\\s+([،,:؛.!؟])", r"\\1", text)\n    text = re.sub(r"([،,:؛])(?=[آ-یA-Za-z])", r"\\1 ", text)\n\n    text = normalize_space(\n        text\n    )\n\n    return text[:6000]'''
    if old_clean_end in source:
        source = source.replace(old_clean_end, new_clean_end, 1)

    old_title_end = '''    title = re.sub(\n        r"\\s*\\+\\s*(فیلم|ویدئو|ویدیو|عکس|تصاویر)\\s*$",\n        "",\n        title,\n        flags=re.I\n    )\n\n    return normalize_space(\n        title\n    )[:180]'''
    new_title_end = '''    title = re.sub(\n        r"\\s*\\+\\s*(فیلم|ویدئو|ویدیو|عکس|تصاویر)\\s*$",\n        "",\n        title,\n        flags=re.I\n    )\n\n    # Remove repeated urgency / source punctuation artifacts.\n    title = re.sub(r"(?:^|\\s)(فوری)(?:\\s+فوری)+", r" \\1", title)\n    title = re.sub(r"\\s*[|｜]+\\s*", " - ", title)\n    title = re.sub(r"\\s*[-–—:]\\s*$", "", title)\n    title = re.sub(r"[.!؟]+$", "", title)\n    title = re.sub(r"\\s{2,}", " ", title)\n\n    return normalize_space(\n        title\n    )[:180]'''
    if old_title_end in source:
        source = source.replace(old_title_end, new_title_end, 1)

    old_prompt = '''3. نام رسانه، نام خبرگزاری، لینک، عبارت «به گزارش»، عبارت‌های تبلیغاتی و منبع را حذف کن.\n4. اگر متن ناقص است، چیزی را حدس نزن.\n5. لحن کاملاً خبری، خنثی و حرفه‌ای باشد.\n6. از اغراق، کلیک‌بیت و نظر شخصی خودداری کن.\n7. اگر عنوان اصلی مناسب است، آن را بی‌دلیل تغییر نده.\n8. فقط اطلاعات موجود در متن را استفاده کن.'''
    new_prompt = '''3. نام رسانه، نام خبرگزاری، لینک، عبارت «به گزارش»، تاریخ‌گذاری ابتدای خبر، عبارت‌های روابط عمومی، بیانیه و اطلاعیه، متن تبلیغاتی و فراخوان‌های تبلیغاتی را حذف کن.\n4. اگر متن ناقص است، چیزی را حدس نزن.\n5. لحن کاملاً خبری، خنثی و حرفه‌ای باشد.\n6. از اغراق، کلیک‌بیت و نظر شخصی خودداری کن.\n7. اگر عنوان اصلی مناسب است، آن را بی‌دلیل تغییر نده.\n8. فقط اطلاعات موجود در متن را استفاده کن.\n9. هیچ نام، عدد، علت، نقل‌قول یا جزئیات جدیدی اختراع نکن.\n10. متن را از عبارت‌های تبلیغاتی، روابط عمومی و معرفی خدمات پاک نگه دار.'''
    if old_prompt in source:
        source = source.replace(old_prompt, new_prompt, 1)

    return source if source != original else source


def patch_topic_emoji(source):
    """Replace the caption builder with a topic-aware emoji version."""

    marker = "def build_caption("
    start = source.find(marker)

    if start < 0:
        raise RuntimeError("build_caption function not found")

    section_end = source.find(
        "\n# ============================================================\n",
        start + len(marker)
    )

    if section_end < 0:
        raise RuntimeError("build_caption section boundary not found")

    new_block = '''def choose_news_emoji(title, body):
    """Choose one clean emoji based on the main topic of the news."""

    text = normalize_space(
        f"{title} {body}"
    ).lower()

    # Urgent incidents take priority over ordinary categories.
    urgent_keywords = [
        "خبر فوری", "فوری", "انفجار", "حمله", "موشک", "جنگ",
        "زلزله", "سیل", "آتش سوزی", "آتش‌سوزی", "سقوط",
        "تصادف", "کشته", "مفقود", "ترور", "حادثه مهم"
    ]
    if any(k in text for k in urgent_keywords):
        return "🚨"

    categories = [
        ("⚽", ["فوتبال", "ورزش", "لیگ", "جام جهانی", "المپیک", "تیم ملی", "بازیکن", "مربی", "آرسنال", "استقلال", "پرسپولیس"]),
        ("💵", ["دلار", "ارز", "یورو", "پوند", "نرخ ارز"]),
        ("🪙", ["طلا", "سکه", "اونس طلا", "طلای ۱۸", "طلای 24", "طلای ۲۴"]),
        ("📈", ["بورس", "شاخص کل", "فرابورس", "سهام", "معاملات بورس"]),
        ("🤖", ["هوش مصنوعی", "هوش مصنوعی", "ai", "gemini", "chatgpt", "مدل زبانی"]),
        ("📱", ["موبایل", "گوشی", "اینترنت", "اپلیکیشن", "اندروید", "آیفون", "ios", "شبکه اجتماعی"]),
        ("🚗", ["خودرو", "ماشین", "خودروساز", "خودروهای وارداتی", "خودرو برقی"]),
        ("🏥", ["سلامت", "پزشکی", "بیمارستان", "دارو", "درمان", "پزشک"]),
        ("🌦️", ["هواشناسی", "آب و هوا", "بارندگی", "بارش", "دما", "هوا"]),
        ("₿", ["بیت کوین", "اتریوم", "ارز دیجیتال", "کریپتو", "رمزارز", "crypto"]),
        ("🛢️", ["نفت", "گاز", "انرژی", "بنزین", "برق", "سوخت", "پالایشگاه"]),
        ("🔬", ["علم", "دانش", "پژوهش", "فضا", "ناسا", "نجوم", "آزمایش"]),
        ("🎬", ["سینما", "فیلم", "سریال", "بازیگر", "هنر", "موسیقی", "فرهنگ"]),
        ("🎓", ["دانشگاه", "مدرسه", "آموزش", "دانشجو", "کنکور", "معلم"]),
        ("🌍", ["جهان", "آمریکا", "اروپا", "روسیه", "اوکراین", "چین", "خاورمیانه", "بین‌الملل", "بین الملل"]),
        ("🇮🇷", ["ایران", "تهران", "مجلس", "دولت", "وزارتخانه", "استاندار", "استان"]),
    ]

    for emoji, keywords in categories:
        if any(k in text for k in keywords):
            return emoji

    return "⚡"


def build_caption(
    title,
    body
):

    title = clean_title(
        title
    )

    body = enforce_short_summary(
        body
    )

    emoji = choose_news_emoji(
        title,
        body
    )

    if body:

        return (
            f"{emoji} {title}\\n\\n"
            f"{body}\\n\\n"
            f"#نبض_خبر"
        )

    return (
        f"{emoji} {title}\\n\\n"
        f"#نبض_خبر"
    )
'''

    return source[:start] + new_block + source[section_end:]


def main():
    with open(SOURCE, "r", encoding="utf-8") as f:
        source = f.read()

    # Keep v12 intact, then always apply the caption/emoji upgrade.
    patched = patch_v12(source)
    patched = patch_topic_emoji(patched)

    if patched != source:
        with open(SOURCE, "w", encoding="utf-8") as f:
            f.write(patched)
        print("NABZ KHABAR: topic-based emoji caption applied")
    else:
        print("NABZ KHABAR: topic-based emoji already active")

    namespace = {"__name__": "__main__", "__file__": SOURCE}
    exec(compile(patched, SOURCE, "exec"), namespace)


if __name__ == "__main__":
    main()
