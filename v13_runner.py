import ast
import re

import v12_runner

SOURCE = "main.py"


def cleanup_duplicate_definitions(source):
    """Remove accidental duplicate top-level function definitions from prior patch runs."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise RuntimeError(f"main.py syntax error before cleanup: {exc}")

    lines = source.splitlines(keepends=True)
    seen = set()
    remove_ranges = []

    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name not in seen:
            seen.add(node.name)
            continue
        start = node.lineno - 1
        end = node.end_lineno
        remove_ranges.append((start, end))

    if not remove_ranges:
        return source

    for start, end in sorted(remove_ranges, reverse=True):
        del lines[start:end]

    return "".join(lines)


def collapse_repeated_canonical_history_blocks(source):
    """Collapse repeated identical canonical-history write blocks."""
    block = '''                if canonical_article_url:\n                    hash_history.add(\n                        make_history_key(\n                            original_title,\n                            canonical_article_url,\n                        )\n                    )\n'''
    while source.count(block) > 1:
        first = source.find(block)
        second = source.find(block, first + len(block))
        if second < 0:
            break
        source = source[:second] + source[second + len(block):]
    return source


def patch_event_level_dedup(source):
    """Strengthen semantic dedup so different headlines for the same real-world event are treated as one story."""
    helper_marker = "def same_story(a, b):"
    helper = r'''# ============================================================
# V13 EVENT-LEVEL DUPLICATE PROTECTION
# ============================================================

EVENT_TERMS = {
    "سیل", "زلزله", "سونامی", "بهمن", "طوفان", "گردباد", "رانش", "آتش سوزی", "آتش‌سوزی",
    "انفجار", "تصادف", "سقوط", "هواپیما", "قطار", "کشتی", "غرق", "حمله", "موشک", "جنگ",
    "درگیری", "آتش بس", "آتش‌بس", "ترور", "کشته", "قربانی", "تلفات", "مفقود", "بازداشت",
    "تحریم", "زلزله", "فوت", "مرگ", "مسمومیت", "قطعی", "خاموشی", "آتش",
}

LOCATION_TERMS = {
    "ایران", "تهران", "نپال", "چین", "هند", "پاکستان", "افغانستان", "ترکیه", "عراق", "سوریه",
    "لبنان", "اسرائیل", "فلسطین", "غزه", "آمریکا", "روسیه", "اوکراین", "فرانسه", "آلمان",
    "انگلیس", "بریتانیا", "ایتالیا", "اسپانیا", "ژاپن", "کره", "عربستان", "امارات", "قطر",
    "بحرین", "عمان", "مصر", "سودان", "یمن", "لیبی", "مکزیک", "برزیل", "کانادا",
}


def event_numbers(text):
    text = normalize_digits(text or "")
    values = re.findall(r"\d+(?:[.,٬]\d+)*", text)
    return {re.sub(r"[.,٬]", "", value) for value in values}


def event_terms(text):
    normalized = normalize_space(normalize_digits(text or "")).lower()
    normalized = normalized.replace("ي", "ی").replace("ك", "ک")
    normalized = normalized.replace("‌", " ")
    return {
        term for term in EVENT_TERMS
        if term in normalized
    }


def location_terms(text):
    normalized = normalize_space(normalize_digits(text or "")).lower()
    return {
        term for term in LOCATION_TERMS
        if term in normalized
    }


def same_real_world_event(title_a, title_b):
    """Detect the same incident when publishers use substantially different wording."""
    combined_a = clean_title(title_a)
    combined_b = clean_title(title_b)

    events_a = event_terms(combined_a)
    events_b = event_terms(combined_b)
    common_events = events_a & events_b

    locations_a = location_terms(combined_a)
    locations_b = location_terms(combined_b)
    common_locations = locations_a & locations_b

    numbers_a = event_numbers(combined_a)
    numbers_b = event_numbers(combined_b)
    common_numbers = numbers_a & numbers_b

    # Same incident type + same location + a shared key number.
    if common_events and common_locations and common_numbers:
        return True

    # Same incident + same location is enough when both headlines are clearly
    # describing a concrete casualty/disaster/attack event.
    if len(common_events) >= 1 and len(common_locations) >= 1:
        if common_numbers:
            return True

        sim = story_similarity(combined_a, combined_b)
        if sim >= 0.30:
            return True

    # Different number formatting such as 1400 vs 1,400 is normalized above.
    if len(common_events) >= 2 and common_numbers:
        return True

    return False


'''
    if helper_marker in source and "def same_real_world_event(title_a, title_b):" not in source:
        source = source.replace(helper_marker, helper + helper_marker, 1)

    target = '''    if not title_a or not title_b:\n        return False\n\n    # Exact normalized title.'''
    replacement = '''    if not title_a or not title_b:\n        return False\n\n    # Event-level identity catches different headlines describing the same\n    # real-world incident, before ordinary token similarity is evaluated.\n    if same_real_world_event(title_a, title_b):\n        return True\n\n    # Exact normalized title.'''
    if target in source and "if same_real_world_event(title_a, title_b):" not in source:
        source = source.replace(target, replacement, 1)

    return source


def patch_quality_gate(source):
    """Add V13 publication quality controls without bypassing the existing pipeline."""
    marker = "# ============================================================\n# PROCESS NEWS\n# ============================================================"

    helper = r'''# ============================================================
# V13 QUALITY GATE
# ============================================================

QUALITY_PR_PATTERNS = [
    r"\bروابط\s*عمومی\b",
    r"\bروابط‌عمومی\b",
    r"\bمراسم\b",
    r"\bگرامیداشت\b",
    r"\bتجلیل\b",
    r"\bتبریک\b",
    r"\bتسلیت\b",
    r"\bهمایش\b",
    r"\bنشست\b",
    r"\bدیدار\b",
    r"\bبالندگی\b",
    r"\bپویایی\b",
    r"\bافتخار\b",
    r"\bدستاوردهای\b",
    r"\bدرخشان\b",
    r"\bمردم‌سالاری\b",
    r"\bمردم سالاری\b",
]

QUALITY_CONCRETE_PATTERNS = [
    r"\bتصویب\b", r"\bتصمیم\b", r"\bاعلام کرد\b", r"\bگفت\b", r"\bآغاز\b",
    r"\bافتتاح\b", r"\bلغو\b", r"\bبازداشت\b", r"\bکشته\b", r"\bمصدوم\b",
    r"\bانفجار\b", r"\bآتش‌سوزی\b", r"\bتصادف\b", r"\bسقوط\b", r"\bقیمت\b",
    r"\bافزایش\b", r"\bکاهش\b", r"\bتغییر\b", r"\bاستخدام\b", r"\bتولید\b",
    r"\bعرضه\b", r"\bممنوع\b", r"\bتحریم\b", r"\bآتش‌بس\b", r"\bحمله\b",
    r"\bزلزله\b", r"\bسیل\b",
]

QUALITY_BAD_PATTERNS = [
    r"برای کسب اطلاعات بیشتر", r"جهت کسب اطلاعات بیشتر", r"کلیک کنید", r"همین حالا",
    r"ثبت\s*نام کنید", r"خرید کنید", r"فروش ویژه", r"تخفیف ویژه", r"اسپانسر",
    r"تبلیغات", r"https?://", r"www\.", r"t\.me/",
]

UNEXPECTED_SCRIPT_RE = re.compile(r"[\u0370-\u03ff\u0400-\u04ff\u0530-\u058f]")


def sanitize_public_text(text):
    if not text:
        return ""
    text = str(text)
    text = text.replace("\u200b", " ").replace("\u200c", " ").replace("\u200d", " ")
    text = text.replace("\u200e", " ").replace("\u200f", " ").replace("\ufeff", " ")
    text = text.replace("ي", "ی").replace("ى", "ی").replace("ك", "ک")
    text = UNEXPECTED_SCRIPT_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\s+([،,:؛.!؟])", r"\1", text)
    text = re.sub(r"([،,:؛])(?=[آ-یA-Za-z])", r"\1 ", text)
    text = re.sub(r"([.!؟])\1+", r"\1", text)
    return normalize_space(text)


def is_low_value_story(title, body):
    text = normalize_space(f"{title} {body}")
    low_hits = sum(bool(re.search(p, text, flags=re.I)) for p in QUALITY_PR_PATTERNS)
    if low_hits < 2:
        return False
    concrete = any(re.search(p, text, flags=re.I) for p in QUALITY_CONCRETE_PATTERNS)
    return not concrete


def quality_gate(candidate, final_title, final_summary):
    """Return (accepted, reason) for the final publishable text."""
    title = sanitize_public_text(final_title)
    summary = sanitize_public_text(final_summary)
    original = sanitize_public_text(candidate.get("title", ""))
    article_text = sanitize_public_text(candidate.get("article_text", ""))

    if not title or len(title) < 12:
        return False, "title_too_short"
    if len(title) > 180:
        return False, "title_too_long"
    if UNEXPECTED_SCRIPT_RE.search(title) or UNEXPECTED_SCRIPT_RE.search(summary):
        return False, "unexpected_script"
    for pattern in QUALITY_BAD_PATTERNS:
        if re.search(pattern, f"{title} {summary}", flags=re.I):
            return False, "advertising_or_link"
    if re.search(r"^(خبر|گزارش|آخرین اخبار|اخبار مهم|خبر مهم)$", title, flags=re.I):
        return False, "vague_title"
    title_words = [w for w in re.split(r"\s+", title) if len(w) > 1]
    if len(title_words) < 3 and len(original) >= 12:
        return False, "vague_title"
    if is_low_value_story(title, summary):
        return False, "low_value_pr"
    if article_text and not summary:
        return False, "empty_summary"
    if summary:
        if len(summary) < 25 and article_text:
            return False, "summary_too_short"
        if len(summary) > 650:
            return False, "summary_too_long"
        sentences = split_sentences(summary)
        if len(sentences) > 3:
            return False, "too_many_sentences"
    return True, "ok"


def quality_adjustment(candidate):
    """Deprioritize major single-source claims; do not hard-block them."""
    keyword_score = calculate_keyword_importance(candidate.get("title", ""), candidate.get("summary", ""))
    if candidate.get("cluster_size", 1) == 1 and keyword_score >= 16:
        return -3
    return 0


'''

    if marker in source and "def quality_gate(candidate, final_title, final_summary):" not in source:
        source = source.replace(marker, helper + marker, 1)

    importance_anchor = '''    if candidate.get(
        "is_hot"
    ):
        score += 18'''
    importance_replacement = importance_anchor + '''

    score += quality_adjustment(candidate)'''
    if importance_anchor in source and "score += quality_adjustment(candidate)" not in source:
        source = source.replace(importance_anchor, importance_replacement, 1)

    clean_anchor = '''    final_title = clean_title(
        final_title
    )

    final_summary = enforce_short_summary(
        final_summary
    )'''
    clean_replacement = '''    final_title = clean_title(
        sanitize_public_text(final_title)
    )

    final_summary = enforce_short_summary(
        sanitize_public_text(final_summary)
    )'''
    if clean_anchor in source and "sanitize_public_text(final_title)" not in source:
        source = source.replace(clean_anchor, clean_replacement, 1)

    gate_anchor = '''    # --------------------------------------------------------
    # Final semantic protection.
    # --------------------------------------------------------

    if history_contains_story('''
    gate_replacement = '''    # --------------------------------------------------------
    # V13 quality gate: never bypassed by hot-news mode.
    # --------------------------------------------------------

    quality_ok, quality_reason = quality_gate(
        candidate,
        final_title,
        final_summary,
    )

    if not quality_ok:
        print(
            f"QUALITY GATE BLOCKED: {quality_reason} | {final_title}"
        )
        return False

    # --------------------------------------------------------
    # Final semantic protection.
    # --------------------------------------------------------

    if history_contains_story('''
    if gate_anchor in source and "QUALITY GATE BLOCKED" not in source:
        source = source.replace(gate_anchor, gate_replacement, 1)

    header = "# NABZ KHABAR BOT v12"
    if header in source:
        source = source.replace(header, "# NABZ KHABAR BOT v13", 1)

    return source


def main():
    with open(SOURCE, "r", encoding="utf-8") as f:
        original = f.read()

    source = cleanup_duplicate_definitions(original)
    source = collapse_repeated_canonical_history_blocks(source)
    source = v12_runner.patch_canonical_duplicate_guard(source)
    source = v12_runner.patch_source_coverage(source)
    source = v12_runner.patch_hot_news(source)
    source = cleanup_duplicate_definitions(source)
    source = collapse_repeated_canonical_history_blocks(source)
    source = patch_event_level_dedup(source)
    source = patch_quality_gate(source)
    source = cleanup_duplicate_definitions(source)
    source = collapse_repeated_canonical_history_blocks(source)

    try:
        ast.parse(source)
    except SyntaxError as exc:
        raise RuntimeError(f"V13 produced invalid main.py: {exc}")

    if source != original:
        with open(SOURCE, "w", encoding="utf-8") as f:
            f.write(source)
        print("NABZ KHABAR: V13 event-level duplicate protection active")
    else:
        print("NABZ KHABAR: V13 already active")

    namespace = {"__name__": "__main__", "__file__": SOURCE}
    exec(compile(source, SOURCE, "exec"), namespace)


if __name__ == "__main__":
    main()
