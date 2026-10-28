"""Runtime diagnostics for scheduler, feed collection, and stale health state."""
from __future__ import annotations

import os
import threading
import time
import uuid
from datetime import datetime, timezone

from atomic_state import load_json, save_json

HEALTH_FILE = "v13_health.json"
_LOCK = threading.Lock()
_FEEDS = {}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _merge_health(patch):
    try:
        with _LOCK:
            state = load_json(HEALTH_FILE, {})
            if not isinstance(state, dict):
                state = {}
            state.update(patch)
            state["updated_at"] = _now()
            save_json(HEALTH_FILE, state)
    except Exception as exc:
        print(f"V13 OBSERVABILITY: health write warning: {type(exc).__name__}", flush=True)


def startup_heartbeat():
    """Write a durable marker before imports and network work can fail."""
    run_id = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
    os.environ["NABZ_RUN_ID"] = run_id
    _merge_health({
        "status": "starting",
        "run_id": run_id,
        "started_at": _now(),
        "heartbeat_at": _now(),
        "heartbeat_phase": "process-start",
        "last_errors": [],
    })
    print(f"V13 OBSERVABILITY: heartbeat {run_id}", flush=True)


def install_collection_observer(main):
    """Observe every feed without changing selection or publication decisions."""
    if getattr(main, "_v13_feed_observer", False):
        return
    original_feed = main.collect_feed
    original_collect = main.collect_candidates

    def collect_feed(category, url, is_google=False):
        started = time.monotonic()
        key = f"{category}|{url}"
        try:
            result = original_feed(category, url, is_google=is_google)
            with _LOCK:
                _FEEDS[key] = {
                    "category": category,
                    "url": url,
                    "kind": "google" if is_google else "direct",
                    "status": "ok" if result else "empty",
                    "candidates": len(result or []),
                    "duration_seconds": round(time.monotonic() - started, 2),
                    "checked_at": _now(),
                }
            return result
        except Exception as exc:
            with _LOCK:
                _FEEDS[key] = {
                    "category": category,
                    "url": url,
                    "kind": "google" if is_google else "direct",
                    "status": "exception",
                    "error": str(exc)[:240],
                    "candidates": 0,
                    "duration_seconds": round(time.monotonic() - started, 2),
                    "checked_at": _now(),
                }
            raise

    def collect_candidates(hash_history, title_history):
        with _LOCK:
            _FEEDS.clear()
        _merge_health({
            "status": "collecting",
            "heartbeat_at": _now(),
            "heartbeat_phase": "collection-start",
        })
        try:
            result = original_collect(hash_history, title_history)
        finally:
            with _LOCK:
                feeds = dict(_FEEDS)
            counts = {}
            for row in feeds.values():
                counts[row["status"]] = counts.get(row["status"], 0) + 1
            _merge_health({
                "feed_status": feeds,
                "feed_summary": {
                    "total": len(feeds),
                    "statuses": counts,
                    "feeds_with_candidates": sum(1 for x in feeds.values() if x.get("candidates", 0) > 0),
                    "feeds_empty_or_failed": sum(1 for x in feeds.values() if x.get("candidates", 0) == 0),
                },
                "heartbeat_at": _now(),
                "heartbeat_phase": "collection-finish",
            })
        return result

    main.collect_feed = collect_feed
    main.collect_candidates = collect_candidates
    main._v13_feed_observer = True
    print("V13 OBSERVABILITY: per-feed collection diagnostics active", flush=True)


def install_patch_hook(run_bot):
    """Install collection observation after the source patch has rebuilt collect_candidates."""
    if getattr(run_bot, "_v13_observability_hooked", False):
        return
    original = getattr(run_bot, "_patch_history_rescue_pipeline", None)
    if not callable(original):
        return

    def patched():
        result = original()
        install_collection_observer(run_bot.main)
        return result

    run_bot._patch_history_rescue_pipeline = patched
    run_bot._v13_observability_hooked = True
