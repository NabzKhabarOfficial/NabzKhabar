"""NABZ V13 anti-advertising quality gate.

This layer blocks clearly commercial/promotional articles before the expensive
AI/media/publication pipeline. It is intentionally conservative: ordinary
product/company news remains allowed unless there are strong purchase/sales
signals.
"""

import re


# High-confidence commercial terms. These are not enough alone in every case;
# combinations below make the decision conservative and reduce false positives.
DIRECT_AD_TERMS = (
    "رپورتاژ",
    "رپورتاژ آگهی",
    "تبلیغات",
    "محتوای تبلیغاتی",
    "آگهی تبلیغاتی",
    "اسپانسر",
    "اسپانسری",
    "کد تخفیف",
    "کد خرید",
    "لینک خرید",
    "ثبت سفارش",
    "سفارش دهید",
    "سفارش بدهید",
    "همین حالا بخرید",
    "خرید کنید",
    "خرید نمایید",
    "فروش ویژه",
    "فروش اقساطی",
    "تخفیف ویژه",
    "تخفیف استثنایی",
    "فرصت خرید",
    "پیشنهاد ویژه",
)

PURCHASE_TERMS = (
    "خرید",
    "فروش",
    "تهیه",
    "سفارش",
    "قیمت",
    "تخفیف",
    "اشتراک",
    "اکانت",
    "عضویت",
)

COMMERCIAL_OBJECTS = (
    "اکانت",
    "اشتراک",
    "سرویس",
    "خدمت",
    "محصول",
    "دوره",
    "نرم افزار",
    "نرم‌افزار",
    "پلن",
    "هاست",
    "دامنه",
    "وی پی ان",
    "vpn",
)

ACTION_TERMS = (
    "خرید",
    "فروش",
    "تهیه",
    "سفارش",
    "ثبت نام",
    "ثبت‌نام",
    "پرداخت",
    "قیمت",
    "تخفیف",
)

# Phrases that strongly indicate an intermediary/reseller or a route to buy.
RESELLER_PATTERNS = (
    r"خدمات?s+واسطه",
    r"واسطه(?:‌|s)+داخلی",
    r"ازs+(?:طریق|طریقِ)s+.*(?:تهیه|خرید)",
    r"(?:می‌توانید|میتوانید|میs+توانید).{0,80}(?:خرید|تهیه|سفارش)",
    r"(?:تهیه|خرید).{0,80}(?:اکانت|اشتراک|سرویس|پلن)",
)

# Commercial language close to the title is particularly strong. We inspect
# the whole article too, but do not let a single generic word block a story.
def _normalize(text):
    value = str(text or "").lower()
    value = value.replace("ي", "ی").replace("ك", "ک")
    value = value.replace("‌", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _has_any(text, terms):
    return any(term in text for term in terms)


def is_promotional_content(title, body=""):
    """Return (blocked, reason) for clearly commercial/promotional content."""
    title = _normalize(title)
    body = _normalize(body)
    combined = f"{title} {body}"

    if not title:
        return False, ""

    # Explicit ad/radvertorial markers are sufficient on their own.
    for term in DIRECT_AD_TERMS:
        if term in title or term in body[:5000]:
            return True, f"explicit commercial marker: {term}"

    # A title that explicitly asks/teaches how to buy/sell a commercial
    # service is promotional even if the body is written like an article.
    if _has_any(title, PURCHASE_TERMS) and _has_any(title, COMMERCIAL_OBJECTS):
        return True, "purchase/sales language in headline"

    # Strong reseller/intermediary wording anywhere in the article.
    for pattern in RESELLER_PATTERNS:
        if re.search(pattern, combined, flags=re.I):
            return True, "reseller/purchase instruction"

    # Two or more commercial action signals plus a commercial object.
    action_hits = sum(term in combined for term in ACTION_TERMS)
    object_hits = sum(term in combined for term in COMMERCIAL_OBJECTS)
    if action_hits >= 2 and object_hits >= 1:
        return True, "multiple commercial purchase signals"

    # Price + discount/order language is a classic sales article.
    if (
        ("قیمت" in combined or "تخفیف" in combined)
        and _has_any(combined, ("سفارش", "خرید", "فروش", "کد تخفیف", "ثبت سفارش"))
    ):
        return True, "price/discount plus purchase signal"

    # English commercial headlines commonly found in syndicated material.
    english_commercial = (
        r"\b(?:buy|purchase|shop|sale|discount|coupon|promo|sponsored|"
        r"advertorial|advertisement|subscribe)\b"
    )
    if re.search(english_commercial, title, flags=re.I):
        return True, "commercial English headline"

    return False, ""


def install(main_module):
    """Wrap V13 candidate collection without changing the core engine."""
    original = main_module.collect_candidates

    def filtered_collect_candidates(hash_history, title_history):
        candidates = original(hash_history, title_history)
        kept = []
        blocked = 0

        for candidate in candidates:
            title = candidate.get("title", "")
            body = (
                candidate.get("summary", "")
                or candidate.get("description", "")
                or candidate.get("content", "")
                or candidate.get("article_text", "")
            )
            blocked_flag, reason = is_promotional_content(title, body)
            if blocked_flag:
                blocked += 1
                print(
                    f"V13 AD FILTER: blocked commercial/promotional story: "
                    f"{title[:160]} | {reason}",
                    flush=True,
                )
                continue
            kept.append(candidate)

        if blocked:
            print(
                f"V13 AD FILTER: blocked {blocked} promotional candidate(s).",
                flush=True,
            )

        return kept

    main_module.collect_candidates = filtered_collect_candidates
    print("V13 anti-advertising filter: ON", flush=True)
