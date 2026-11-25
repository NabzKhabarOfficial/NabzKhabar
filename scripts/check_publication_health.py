"""Fail loudly when the news engine stops producing fresh runtime evidence.

A run that selects stories and publishes none is an outage for a news channel,
not a green run. Since the editor gate ships a guaranteed-publication fallback
(Nov 2026), a zero-publication run means even the fallback bar found nothing
publishable - that state deserves a visible alert issue, and the watchdog
workflow closes the issue again once publication recovers.

One exception, per CHANGE_CONTROL_POLICY.md: a run the gate failed closed
because NO AI provider answered (no-ai-fallback-fail-closed) is not the same
failure as an editorial shutdown. It stays visible as a warning, but it must
not page the outage alert.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HEALTH = Path("v13_health.json")
MONITOR = Path("v13_monitor.json")
MAX_AGE_SECONDS = 20 * 60
# Reasons the engine records when it failed closed because no AI provider
# answered. Per CHANGE_CONTROL_POLICY.md these are not editorial outages.
FAIL_CLOSED_MARKERS = ("ai_unavailable", "no-ai-fallback-fail-closed")


def _read(path):
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except Exception as exc:
        return None, f"{path}: {type(exc).__name__}"


def _age(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - parsed).total_seconds()
    except Exception:
        return None


def main():
    health, health_error = _read(HEALTH)
    monitor, monitor_error = _read(MONITOR)
    errors = [x for x in (health_error, monitor_error) if x]
    if not isinstance(health, dict):
        errors.append("health telemetry is missing or invalid")
    if not isinstance(monitor, dict):
        errors.append("monitor telemetry is missing or invalid")
    if errors:
        for error in errors:
            print(f"PUBLICATION WATCHDOG: {error}")
        return 1

    status = str(monitor.get("status", "unknown")).lower()
    age = _age(health.get("heartbeat_at") or health.get("updated_at"))
    if status in {"runtime_failure", "publication_failure", "unknown", "error"}:
        errors.append(f"monitor status={status}")
    if age is None:
        errors.append("heartbeat is missing or invalid")
    elif age > MAX_AGE_SECONDS:
        errors.append(f"heartbeat is stale: {int(age // 60)} minutes")
    if str(health.get("status", "")).lower() in {"starting", "running", "collecting"}:
        errors.append(f"engine status={health.get('status')}")

    feed_summary = health.get("feed_summary") or {}
    if feed_summary and feed_summary.get("total", 0) and feed_summary.get("feeds_with_candidates", 0) == 0:
        errors.append("all observed feeds returned zero candidates")

    # A silent zero-publication run is an outage, not a warning: with the
    # guaranteed-publication fallback in place, reaching this state means the
    # fallback bar also found nothing (no AI verdict >= 5 with happened=true
    # and non-local scope), so the channel is silent and someone should look.
    # Exception (policy): when every blocked attempt failed closed because no
    # AI provider answered, the run is a provider outage, not an editorial
    # one - it stays visible as a warning instead of paging the alert.
    selected = int(health.get("selected_for_publication", 0) or 0)
    published = int(health.get("published", 0) or 0)
    if status == "editorial_blocked" and selected and published == 0:
        attempts = [a for a in (health.get("publication_attempts") or []) if isinstance(a, dict)]
        fail_closed_no_ai = bool(attempts) and all(
            any(marker in str(a.get("reason", "")) for marker in FAIL_CLOSED_MARKERS)
            for a in attempts
        )
        if fail_closed_no_ai:
            print("::warning title=NabzKhabar no publication this run::"
                  f"{selected} selected, 0 published "
                  "(no AI provider available - engine failed closed per policy)")
            print("PUBLICATION WATCHDOG: WARNING - fail-closed run (AI providers unavailable)")
        else:
            errors.append(
                f"run published nothing: {selected} selected, 0 published "
                "(editorial gate blocked everything and the fallback found nothing)"
            )

    if errors:
        print("PUBLICATION WATCHDOG: ALERT")
        for error in errors:
            print(f" - {error}")
        print("::error title=NabzKhabar publication stopped::" + "; ".join(errors))
        return 1

    print("PUBLICATION WATCHDOG: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
