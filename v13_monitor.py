"""NABZ-V13 runtime monitoring report."""
import json
from datetime import datetime, timezone

from atomic_state import save_json
from v13_status import PublicationStatus, normalize_status

HEALTH_FILE = "v13_health.json"
REPORT_FILE = "v13_monitor.json"
STALE_AFTER_SECONDS = 20 * 60
NON_FAILURE_RESULTS = (
    PublicationStatus.SKIPPED_DUPLICATE.value,
    PublicationStatus.EDITORIAL_BLOCKED.value,
    PublicationStatus.QUALITY_BLOCKED.value,
)


def _load(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _age_seconds(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds())
    except Exception:
        return None


def build_report():
    health = _load(HEALTH_FILE, None)
    if not isinstance(health, dict):
        report = {"checked_at": datetime.now(timezone.utc).isoformat(), "status": "runtime_failure", "run_status": "unknown", "diagnostics": ["Runtime health file is missing or invalid."], "selected_for_publication": 0, "published": 0, "failed_publications": 0, "ambiguous_publications": 0}
        save_json(REPORT_FILE, report)
        print("V13 MONITOR STATUS: runtime_failure", flush=True)
        return report

    attempts = health.get("publication_attempts") or []
    selected = health.get("selected_news_this_run") or []
    published = {str(x.get("title", "")).strip() for x in attempts if normalize_status(x.get("result")) == PublicationStatus.PUBLISHED.value}
    handled = published | {str(x.get("title", "")).strip() for x in attempts if normalize_status(x.get("result")) in NON_FAILURE_RESULTS}
    missed = [{**x, "monitor_reason": "selected-but-not-published"} for x in selected if str(x.get("title", "")).strip() and str(x.get("title", "")).strip() not in handled]
    failed = [x for x in attempts if normalize_status(x.get("result")) in (PublicationStatus.FAILED.value, PublicationStatus.AMBIGUOUS.value)]
    run_status = str(health.get("status", "unknown")).strip().lower()
    status = "healthy"
    diagnostics = []
    if run_status in ("failed", "error", "unknown", "", "starting", "running", "collecting"):
        status = "runtime_failure"
        diagnostics.append(f"Runtime status is {run_status or 'unknown'}.")
    heartbeat = health.get("heartbeat_at") or health.get("updated_at") or health.get("started_at")
    age = _age_seconds(heartbeat)
    if age is None:
        # Older fixtures and manually-created health files may not carry a
        # timestamp. New production runs always have a startup heartbeat and
        # are therefore still fail-closed when that marker is malformed.
        if health.get("run_id") or health.get("heartbeat_phase"):
            status = "runtime_failure"
            diagnostics.append("Runtime heartbeat timestamp is missing or invalid.")
    elif age > STALE_AFTER_SECONDS:
        status = "runtime_failure"
        diagnostics.append(f"Runtime heartbeat is stale ({int(age // 60)} minutes old).")
    if missed or health.get("failed_publications") or health.get("ambiguous_publications"):
        status = "publication_failure"
        if missed: diagnostics.append("Selected stories did not reach confirmed publication.")
        if failed: diagnostics.append("Publication attempts failed or raised exceptions.")
    important_missed = health.get("important_missed") or []
    editorial_blocked = [x for x in attempts if normalize_status(x.get("result")) == PublicationStatus.EDITORIAL_BLOCKED.value]
    skipped_duplicate = [x for x in attempts if normalize_status(x.get("result")) == PublicationStatus.SKIPPED_DUPLICATE.value]
    ai_pool = health.get("ai_pool") or health.get("ai_providers") or {}
    no_publication_candidate = bool(health.get("no_publication_candidate")) or (not selected and not attempts)
    if important_missed:
        diagnostics.append("Important-news rescue reports missed candidates.")
    if editorial_blocked:
        diagnostics.append("Editorial gate blocked one or more candidates.")
    if no_publication_candidate:
        diagnostics.append("No publication candidate was available this run.")
    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "run_status": run_status,
        "heartbeat_age_seconds": age,
        "selected_for_publication": len(selected),
        "published": health.get("published", len(published)),
        "failed_publications": health.get("failed_publications", len(failed)),
        "ambiguous_publications": health.get("ambiguous_publications", sum(1 for x in attempts if normalize_status(x.get("result")) == PublicationStatus.AMBIGUOUS.value)),
        "important_missed": important_missed,
        "editorial_blocked": editorial_blocked,
        "skipped_duplicate": skipped_duplicate,
        "ai_pool": ai_pool,
        "feed_summary": health.get("feed_summary", {}),
        "no_publication_candidate": no_publication_candidate,
        "missed_selected_stories": missed,
        "failed_publication_attempts": failed,
        "diagnostics": diagnostics,
    }
    save_json(REPORT_FILE, report)
    print("V13 MONITOR STATUS:", status, flush=True)
    return report

if __name__ == "__main__":
    build_report()
