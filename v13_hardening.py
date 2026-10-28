"""Small, deterministic runtime hardening patches for the active V13 stack."""
from __future__ import annotations
import json
import os
import re
from pathlib import Path


def _halfspace_text(value):
    text = str(value or "").replace("ي", "ی").replace("ك", "ک")
    text = text.replace("\u200f", "").replace("\u200e", "").replace("\xa0", " ")
    text = re.sub(r"\s*\u200c\s*", "\u200c", text)
    # Use callable replacements: Python's re replacement parser treats
    # backslash-u sequences specially and can raise "bad escape \\u".
    text = re.sub(
        r"\b(می|نمی)\s+([\u0600-\u06ff])",
        lambda match: f"{match.group(1)}\u200c{match.group(2)}",
        text,
    )
    text = re.sub(
        r"([\u0600-\u06ff])\s+(ها|های|هایی|تر|ترین)(?=\b|\s|[،؛؟,.!])",
        lambda match: f"{match.group(1)}\u200c{match.group(2)}",
        text,
    )
    return re.sub(r"[ \t]+", " ", text).strip()


def install_text_normalizer(core):
    if getattr(core, "_nabz_halfspace_hardened", False):
        return
    core.normalize_space = _halfspace_text
    core._nabz_halfspace_hardened = True
    print("V13 HARDENING: Persian half-spaces preserved", flush=True)


def _gone_page(growth, item_id):
    try:
        return growth._gone_page()
    except Exception:
        return ("<!doctype html><html lang=\"fa\" dir=\"rtl\"><head>"
                "<meta name=\"robots\" content=\"noindex,nofollow\"><meta http-equiv=\"refresh\" content=\"0;url=../index.html\"></head>"
                "<body><h1>این خبر برداشته شد</h1><p>این مطلب از سایت حذف شده است.</p></body></html>")


def _quarantine_ids():
    try:
        import quarantine_guard
        return quarantine_guard.quarantined_ids()
    except Exception:
        return set()


def install_growth(growth):
    if getattr(growth, "_nabz_growth_hardened", False):
        return
    original_build = growth.build_site

    def safe_build(items):
        blocked = _quarantine_ids()
        kept = []
        for item in list(items or []):
            if isinstance(item, dict) and str(item.get("id") or "") in blocked:
                item_id = str(item.get("id"))
                try:
                    growth._write(os.path.join(growth.DOCS, "news", item_id + ".html"), _gone_page(growth, item_id))
                except Exception:
                    pass
                continue
            kept.append(item)
        return original_build(kept)

    growth.build_site = safe_build
    growth._nabz_growth_hardened = True
    print("V13 HARDENING: quarantined site pages excluded from indexes", flush=True)


def install_digest(growth):
    if getattr(growth, "_nabz_digest_hardened", False):
        return
    from datetime import datetime, timezone
    from publication_outcome import classify, PublicationOutcome
    original = growth.maybe_post_digest

    def safe_digest(core):
        now = datetime.now(timezone.utc).astimezone(growth.TEHRAN)
        if now.hour < growth.DIGEST_HOUR_TEHRAN:
            return
        router, health = growth._health()
        today = now.date().isoformat()
        if health.get(growth.DIGEST_KEY) == today:
            return
        start = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        items = [x for x in (health.get(growth.DAILY_KEY) or []) if isinstance(x, dict) and float(x.get("t", 0) or 0) >= start]
        if len(items) < growth.DIGEST_MIN_ITEMS:
            return
        text, _entities, count = growth.build_digest(items, now)
        try:
            result = core.send_message(text)
        except Exception as exc:
            print(f"V13 GROWTH: digest ambiguous ({type(exc).__name__})", flush=True)
            return
        outcome = classify(result)
        if outcome is PublicationOutcome.SUCCESS:
            health = router._load_health(); health[growth.DIGEST_KEY] = today; router._save_health(health)
            print(f"V13 GROWTH: daily digest published ({count} stories).", flush=True)
        elif outcome is PublicationOutcome.AMBIGUOUS:
            print("V13 GROWTH: digest ambiguous; left pending for reconciliation.", flush=True)
        else:
            print("V13 GROWTH: digest explicitly rejected; left pending for retry.", flush=True)

    growth.maybe_post_digest = safe_digest
    growth._nabz_digest_hardened = True
    print("V13 HARDENING: digest uses canonical publication outcomes", flush=True)
