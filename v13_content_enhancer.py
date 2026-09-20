"""
NABZ V13 — Automatic content enrichment layer.

Keeps the existing V13 runtime and AI fallback router intact, but makes
guide/list/market stories more useful automatically. No paid service is used.
"""

import re


GUIDE_MARKERS = (
    "راهنمای", "خرید", "قیمت", "لیست", "فهرست", "مقایسه", "معرفی",
    "مدل", "بازه قیمتی", "شهریور", "مرداد", "تومان", "هزینه",
    "بهترین", "نکات", "چطور", "چگونه", "شرایط فروش",
)


def _is_guide(text):
    value = str(text or "").lower()
    return sum(1 for marker in GUIDE_MARKERS if marker in value) >= 2


def _rich_prompt(prompt):
    value = str(prompt or "")
    if not _is_guide(value):
        return value

    # Preserve the original source/title and safety requirements, but change
    # the output contract for practical guide/market content.
    value = re.sub(
        r"خلاصه حداکثر ۳ جمله و ۷۵۰ نویسه باشد\.",
        "خلاصه حداکثر ۵ جمله و ۹۰۰ نویسه باشد.",
        value,
    )
    value = re.sub(
        r"خلاصه حداکثر ۳ جمله و ۷۵۰ نویسه باشد",
        "خلاصه حداکثر ۵ جمله و ۹۰۰ نویسه باشد",
        value,
    )

    extra = """
این محتوا از نوع راهنما/فهرست/قیمت/بازار است. آن را صرفاً کوتاه نکن؛
اطلاعات کاربردی موجود در متن را فشرده و منظم ارائه کن:
- مهم‌ترین بازه‌ها، مدل‌ها، قیمت‌ها، ویژگی‌ها یا شرایطی که واقعاً در منبع آمده را حفظ کن.
- اگر منبع چند گزینه یا چند بازه دارد، آن‌ها را در خلاصه به شکل مرتب و قابل خواندن بیاور.
- برای راهنمای خرید، در صورت وجود اطلاعات در منبع، کاربرد، قیمت و نکات مهم خرید را حفظ کن.
- هیچ مدل، قیمت، عدد، ویژگی، تاریخ یا ادعایی را حدس نزن و از خودت اضافه نکن.
- اگر اطلاعات یک بخش در منبع وجود ندارد، آن بخش را حذف کن.
- خروجی همچنان خبری و بی‌طرف باشد و تبلیغاتی نشود.
"""
    return value + "\n" + extra


def install(main, router):
    original_request_json = router._request_json
    original_validate = router._validate
    original_enforce = main.enforce_short_summary

    def request_json(main_obj, model, prompt, max_output_tokens=500):
        return original_request_json(
            main_obj, model, _rich_prompt(prompt), max_output_tokens
        )

    def validate(main_obj, original_title, source, data, foreign):
        result = original_validate(
            main_obj, original_title, source, data, foreign
        )
        if result:
            return result

        # The stock validator is intentionally strict at 3 sentences/750 chars.
        # For guide/market stories, allow the richer contract while retaining
        # every other safety check from the original validator.
        if not _is_guide(str(original_title) + " " + str(source)):
            return None
        if not isinstance(data, dict):
            return None

        title = main_obj.clean_title(data.get("title", ""))
        summary = main_obj.clean_content(data.get("summary", ""))
        if not title or not summary or len(summary) > 900:
            return None

        if any(x in (title + " " + summary).lower() for x in (
            "http://", "https://", "www.", "منبع:", "به گزارش",
            "طبق گزارش ما", "به گفته منابع ما", "منابع ما",
        )):
            return None

        if len(re.findall(r"(?<=[.!؟؛])\s+", summary.strip())) + 1 > 5:
            return None

        # Every number in the AI output must exist in the source.
        src_nums = set(re.findall(r"\b\d+(?:[.,]\d+)?\b", main_obj.normalize_digits(str(source))))
        out_nums = set(re.findall(r"\b\d+(?:[.,]\d+)?\b", main_obj.normalize_digits(title + " " + summary)))
        if not out_nums.issubset(src_nums):
            return None

        latin = re.findall(r"(?<![A-Za-z])[A-Za-z]{2,}(?![A-Za-z])", title + " " + summary)
        if any(x.upper() != "NABZ" for x in latin):
            return None

        return {"title": title, "summary": summary}

    def rich_enforce(text):
        text = main.clean_content(text)
        if not text:
            return ""
        sentences = main.split_sentences(text)
        if not sentences:
            return text[:900].strip()
        selected = [sentences[0]]
        for sentence in sentences[1:]:
            if len(selected) >= 5:
                break
            candidate = " ".join(selected + [sentence])
            if len(candidate) <= 900:
                selected.append(sentence)
        return " ".join(selected).strip()[:900]

    router._request_json = request_json
    router._validate = validate
    main.enforce_short_summary = rich_enforce

    print("V13 CONTENT ENHANCER ACTIVE: guide/market content is enriched automatically.")


if __name__ == "__main__":
    print("NABZ V13 content enhancer module")
