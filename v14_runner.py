import ast
import v12_runner
import v13_runner

SOURCE = "main.py"


def patch_event_dedup(source):
    """Apply V13's event-level guard and add a final history guard."""
    # V13 contains the stronger event matcher (event + location + number).
    # Make sure it is actually applied before the final V14 guard.
    source = v13_runner.patch_event_level_dedup(source)

    marker = "# ============================================================\n# PROCESS NEWS\n# ============================================================"
    helper = r'''# ============================================================
# V14 EVENT-LEVEL DUPLICATE PROTECTION
# ============================================================

EVENT_WORDS = {
    "سیل", "زلزله", "انفجار", "آتش سوزی", "آتش‌سوزی", "سقوط", "تصادف",
    "حمله", "جنگ", "موشک", "ترور", "کشته", "قربانی", "تلفات", "مفقود",
    "بازداشت", "آتش بس", "آتش‌بس", "فوت", "درگذشت", "طوفان", "بارندگی",
    "رانش", "بهمن", "حادثه", "واژگونی", "حریق",
}

GENERIC_EVENT_WORDS = {
    "خبر", "گزارش", "اعلام", "آخرین", "جدید", "مهم", "بیشتر", "شد", "شدند",
    "کرد", "کردند", "گفت", "گفتند", "رسید", "گذشت", "نفر", "افراد", "مقام",
    "مقامات", "کشور", "منطقه", "استان", "شهر", "در", "از", "به", "با", "و",
    "را", "که", "این", "آن", "یک", "هم", "نیز", "برای", "تا", "بر", "های", "ها",
}


def event_normalize(text):
    text = normalize_digits(str(text or ""))
    text = text.replace("ي", "ی").replace("ى", "ی").replace("ك", "ک")
    text = re.sub(r"[\u200b-\u200f\ufeff]", " ", text)
    text = re.sub(r"[،؛,:.!؟()\[\]{}\"'«»/\\|]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def event_tokens(text):
    tokens = set(re.findall(r"[a-z0-9آ-ی]+", event_normalize(text)))
    return {x for x in tokens if len(x) >= 2 and x not in GENERIC_EVENT_WORDS}


def event_numbers(text):
    return {x.replace(",", "") for x in re.findall(r"\d+(?:[.,]\d+)?", event_normalize(text))}


def event_terms(text):
    normalized = event_normalize(text)
    return {x for x in EVENT_WORDS if event_normalize(x) in normalized}


def same_event(a_title, a_body, b_title, b_body):
    a = event_tokens(f"{a_title} {a_body}")
    b = event_tokens(f"{b_title} {b_body}")
    common = a & b
    numbers = event_numbers(f"{a_title} {a_body}") & event_numbers(f"{b_title} {b_body}")
    terms = event_terms(f"{a_title} {a_body}") & event_terms(f"{b_title} {b_body}")
    if not terms or len(common) < 2:
        return False
    if numbers and len(common) >= 2:
        return True
    return bool(terms and len(common) >= 4)


def event_history_contains(candidate, title_history):
    title = clean_title(candidate.get("title", ""))
    body = normalize_space(candidate.get("summary", ""))
    if not title:
        return False
    cutoff = int(datetime.now(timezone.utc).timestamp()) - int(SEMANTIC_HISTORY_DAYS * 86400)
    for timestamp, old_title in title_history:
        if timestamp < cutoff:
            continue
        if same_event(title, body, old_title, ""):
            return True
    return False

'''
    if marker in source and "def event_history_contains(candidate, title_history):" not in source:
        source = source.replace(marker, helper + marker, 1)

    # V13's quality gate already locates the final semantic block. If that
    # exact comment is absent, use the first history check as a fallback.
    if "EVENT DUPLICATE BLOCKED" not in source:
        insertion = (
            "    # V14 event-level protection: same real-world incident, different wording.\n"
            "    if event_history_contains(candidate, title_history):\n"
            "        print(f\"EVENT DUPLICATE BLOCKED: {final_title}\")\n"
            "        return False\n\n"
        )
        anchors = [
            "    # Final semantic protection.\n",
            "    if history_contains_story(\n",
        ]
        for anchor in anchors:
            if anchor in source:
                source = source.replace(anchor, insertion + anchor, 1)
                break
    return source


def main():
    with open(SOURCE, "r", encoding="utf-8") as f:
        original = f.read()

    source = v13_runner.cleanup_duplicate_definitions(original)
    source = v13_runner.collapse_repeated_canonical_history_blocks(source)
    source = v12_runner.patch_canonical_duplicate_guard(source)
    source = v12_runner.patch_source_coverage(source)
    source = v12_runner.patch_hot_news(source)
    source = v13_runner.cleanup_duplicate_definitions(source)
    source = v13_runner.collapse_repeated_canonical_history_blocks(source)
    source = v13_runner.patch_quality_gate(source)
    source = v13_runner.patch_event_level_dedup(source)
    source = v13_runner.cleanup_duplicate_definitions(source)
    source = v13_runner.collapse_repeated_canonical_history_blocks(source)
    source = patch_event_dedup(source)
    source = v13_runner.cleanup_duplicate_definitions(source)
    source = v13_runner.collapse_repeated_canonical_history_blocks(source)
    ast.parse(source)

    if source != original:
        with open(SOURCE, "w", encoding="utf-8") as f:
            f.write(source)
        print("NABZ KHABAR: V14 event-level duplicate protection active")
    else:
        print("NABZ KHABAR: V14 already active")

    namespace = {"__name__": "__main__", "__file__": SOURCE}
    exec(compile(source, SOURCE, "exec"), namespace)


if __name__ == "__main__":
    main()
