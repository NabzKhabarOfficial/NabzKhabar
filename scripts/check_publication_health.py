"""Fail loudly when the news engine stops producing fresh runtime evidence."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HEALTH = Path("v13_health.json")
MONITOR = Path("v13_monitor.json")
MAX_AGE_SECONDS = 20 * 60


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
