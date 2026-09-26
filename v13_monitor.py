"""NABZ-V13 runtime monitoring report.

Reads the health state produced by the running bot and turns silent publication
losses into explicit, machine-readable diagnostics. It never sends Telegram
messages and never changes editorial decisions.
"""

import json
import re
from datetime import datetime, timezone

HEALTH_FILE = "v13_health.json"
REPORT_FILE = "v13_monitor.json"

# Neutral monitoring threshold: this is a review signal, not an editorial
# override. A story is "important missed" when intelligence scored it strongly
# or an independent consequential/security/business/UNGA override recognized it.
IMPORTANT_MISSED_SCORE = 12


def _load(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


GLOBAL_MONITOR_SIGNALS = (
    "توافق", "توافقنامه", "موافقت", "قرارداد", "پیشنهاد", "پیشنهاد داد",
    "ممنوعیت", "محدودیت", "تحریم", "تعلیق", "لغو", "ازسرگیری", "از سرگیری",
    "توقف", "اختلال گسترده", "بحران", "نفت", "انرژی", "فرودگاه",
    "venezuela", "caracas", "germany", "european", "oil", "agreement",
    "deal", "sanction", "restricted", "suspended", "halted", "proposal",
)
GLOBAL_MONITOR_ACTORS = (
    "ایران", "آمریکا", "چین", "روسیه", "اوکراین", "اسرائیل", "عراق", "عربستان",
    "ونزوئلا", "آلمان", "اتحادیه اروپا", "سازمان ملل",
    "iran", "united states", "u.s.", "china", "russia", "ukraine", "israel",
    "iraq", "saudi", "venezuela", "germany", "european union", "united nations",
)


def _monitor_global_consequential(story):
    title = str(story.get("title", "") or "").lower()
    if not title:
        return False
    signal_hits = sum(x in title for x in GLOBAL_MONITOR_SIGNALS)
    actor_hits = sum(x in title for x in GLOBAL_MONITOR_ACTORS)
    # Two independent action/topic signals plus a major actor are enough for
    # monitoring review. This is intentionally broader than publication gates.
    return signal_hits >= 2 and actor_hits >= 1


def _is_important_missed(story):
    score = int(story.get("intelligence_score", 0) or 0)
    return bool(
        score >= IMPORTANT_MISSED_SCORE
        or story.get("high_impact_security_candidate")
        or story.get("major_business_legal_candidate")
        or story.get("global_consequential_candidate")
        or story.get("unga_breaking_candidate")
        or _monitor_global_consequential(story)
    )


def build_report():
    health = _load(HEALTH_FILE, {})
    selected = health.get("selected_news_this_run") or []
    attempts = health.get("publication_attempts") or []
    rejected = health.get("rejected_news_this_run") or []

    if not selected and attempts:
        selected = [
            {"title": x.get("title", ""), "source": x.get("source", ""), "url": x.get("url", "")}
            for x in attempts
            if x.get("title") and x.get("result") != "skipped_duplicate"
        ]

    published = {
        str(x.get("title", "")).strip()
        for x in attempts if x.get("result") == "published"
    }

    missed = []
    for story in selected:
        title = str(story.get("title", "")).strip()
        if title and title not in published:
            missed.append({**story, "monitor_reason": "selected-but-not-published"})

    failed_attempts = [
        x for x in attempts if x.get("result") in ("failed", "exception")
    ]
    skipped_duplicates = [
        x for x in attempts if x.get("result") == "skipped_duplicate"
    ]

    important_missed = []
    seen = set()
    for story in rejected:
        title = str(story.get("title", "")).strip()
        if not title or not _is_important_missed(story):
            continue
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        important_missed.append({
            **story,
            "monitor_reason": "important-candidate-rejected",
        })

    # Do not turn a review signal into a runtime failure. It is specifically
    # there so the next audit can identify potentially important losses without
    # forcing the editorial engine to publish them blindly.
    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": "healthy",
        "run_status": health.get("status", "unknown"),
        "raw_candidates": health.get("raw_candidates", 0),
        "strict_rejected": health.get("strict_rejected", 0),
        "selected_for_publication": len(selected),
        "published": health.get("published", 0),
        "failed_publications": health.get("failed_publications", 0),
        "ambiguous_publications": health.get("ambiguous_publications", 0),
        "missed_selected_stories": missed,
        "important_missed_news": important_missed,
        "failed_publication_attempts": failed_attempts,
        "skipped_duplicate_attempts": skipped_duplicates,
        "last_errors": health.get("last_errors", []),
        "diagnostics": [],
    }

    if missed or report["failed_publications"] or report["ambiguous_publications"]:
        report["status"] = "publication_failure"
        if missed:
            report["diagnostics"].append("Selected stories did not reach confirmed publication.")
        if report["failed_publications"]:
            report["diagnostics"].append("One or more publication attempts returned failure/exception.")
        if report["ambiguous_publications"]:
            report["diagnostics"].append(
                "One or more Telegram sends had ambiguous transport results; fallback was intentionally blocked to prevent duplicates."
            )

    if important_missed:
        report["diagnostics"].append(
            f"{len(important_missed)} potentially important candidate(s) were rejected; review reasons before changing gates."
        )

    if not selected and health.get("raw_candidates", 0) and not health.get("published", 0):
        report["status"] = "no_publication_candidate"
        report["diagnostics"].append("Candidates were collected but none reached the publication queue.")
    elif report["published"] > 0 and not report["failed_publications"] and not missed:
        # Keep the run technically healthy even when important-missed review
        # signals exist.
        report["status"] = "healthy"

    if health.get("status") == "failed":
        report["status"] = "runtime_failure"
        report["diagnostics"].append("The V13 runtime failed.")

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("V13 MONITOR STATUS:", report["status"], flush=True)
    print(
        "V13 MONITOR: selected=%s published=%s failed=%s ambiguous=%s missed=%s duplicates=%s important_missed=%s"
        % (
            report["selected_for_publication"],
            report["published"],
            report["failed_publications"],
            report["ambiguous_publications"],
            len(missed),
            len(skipped_duplicates),
            len(important_missed),
        ),
        flush=True,
    )

    for story in missed:
        print("V13 MONITOR MISSED: %s | %s | %s" % (
            story.get("source", "unknown"), story.get("title", ""), story.get("url", "")
        ), flush=True)

    for story in important_missed[:10]:
        print(
            "V13 MONITOR IMPORTANT MISSED: "
            f"[score={story.get('intelligence_score', 0)}] "
            f"[reason={story.get('reason', 'unknown')}] "
            f"{story.get('title', '')} | {story.get('url', '')}",
            flush=True,
        )

    return report


if __name__ == "__main__":
    build_report()
