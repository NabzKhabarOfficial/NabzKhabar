"""NABZ-V13 runtime monitoring report.

Reads the health state produced by the running bot and turns silent publication
losses into explicit, machine-readable diagnostics. It never sends Telegram
messages and never changes editorial decisions.
"""

import json
from datetime import datetime, timezone

HEALTH_FILE = "v13_health.json"
REPORT_FILE = "v13_monitor.json"


def _load(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def build_report():
    health = _load(HEALTH_FILE, {})
    selected = health.get("selected_news_this_run") or []
    attempts = health.get("publication_attempts") or []

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

    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": "healthy",
        "run_status": health.get("status", "unknown"),
        "raw_candidates": health.get("raw_candidates", 0),
        "strict_rejected": health.get("strict_rejected", 0),
        "selected_for_publication": len(selected),
        "published": health.get("published", 0),
        "failed_publications": health.get("failed_publications", 0),
        "missed_selected_stories": missed,
        "failed_publication_attempts": failed_attempts,
        "skipped_duplicate_attempts": skipped_duplicates,
        "last_errors": health.get("last_errors", []),
        "diagnostics": [],
    }

    if missed or report["failed_publications"]:
        report["status"] = "publication_failure"
        if missed:
            report["diagnostics"].append("Selected stories did not reach confirmed publication.")
        if report["failed_publications"]:
            report["diagnostics"].append("One or more publication attempts returned failure/exception.")

    if not selected and health.get("raw_candidates", 0) and not health.get("published", 0):
        report["status"] = "no_publication_candidate"
        report["diagnostics"].append("Candidates were collected but none reached the publication queue.")
    elif report["published"] > 0 and not report["failed_publications"] and not missed:
        report["status"] = "healthy"

    if health.get("status") == "failed":
        report["status"] = "runtime_failure"
        report["diagnostics"].append("The V13 runtime failed.")

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("V13 MONITOR STATUS:", report["status"], flush=True)
    print(
        "V13 MONITOR: selected=%s published=%s failed=%s missed=%s duplicates=%s"
        % (report["selected_for_publication"], report["published"],
           report["failed_publications"], len(missed), len(skipped_duplicates)),
        flush=True,
    )
    for story in missed:
        print("V13 MONITOR MISSED: %s | %s | %s" % (
            story.get("source", "unknown"), story.get("title", ""), story.get("url", "")
        ), flush=True)

    return report


if __name__ == "__main__":
    build_report()
