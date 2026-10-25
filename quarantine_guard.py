"""Fail-closed production guard for quarantined news records and AI verdicts."""
from __future__ import annotations

import json
import math
from functools import wraps
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "content" / "quarantine_manifest.json"
ALLOWED_SCOPES = {"world", "iran_national", "local"}


def quarantined_ids() -> set[str]:
    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        ids = data.get("ids")
        if not isinstance(ids, list):
            raise ValueError("quarantine manifest ids is not a list")
        return {str(x).strip() for x in ids if str(x).strip()}
    except Exception as exc:
        # A missing/corrupt safety manifest must not silently publish.
        raise RuntimeError(f"quarantine manifest unavailable: {type(exc).__name__}: {exc}") from None


def candidate_id(candidate: dict) -> str:
    for key in ("id", "story_id", "record_id", "slug"):
        value = str(candidate.get(key) or "").strip()
        if value:
            return value
    for key in ("canonical", "canonical_url", "url", "link"):
        value = str(candidate.get(key) or "").strip().rstrip("/")
        if value:
            tail = value.rsplit("/", 1)[-1]
            if tail:
                return tail.removesuffix(".html")
    return ""


def is_quarantined(candidate: dict) -> bool:
    return candidate_id(candidate) in quarantined_ids()


def install_main(main) -> None:
    if getattr(main, "_quarantine_guard_installed", False):
        return
    previous_process = main.process_news
    previous_collect = getattr(main, "collect_candidates", None)

    @wraps(previous_process)
    def guarded_process(candidate, *args, **kwargs):
        if is_quarantined(candidate):
            candidate["publication_status"] = "quarantine_blocked"
            print(f"QUARANTINE BLOCK: {candidate_id(candidate)}", flush=True)
            return False
        return previous_process(candidate, *args, **kwargs)

    main.process_news = guarded_process
    if previous_collect is not None:
        @wraps(previous_collect)
        def guarded_collect(*args, **kwargs):
            rows = list(previous_collect(*args, **kwargs) or [])
            kept = []
            for row in rows:
                if is_quarantined(row):
                    row["publication_status"] = "quarantine_blocked"
                    print(f"QUARANTINE BLOCK: {candidate_id(row)}", flush=True)
                else:
                    kept.append(row)
            return kept
        main.collect_candidates = guarded_collect
    main._quarantine_guard_installed = True


def install_editor_gate(gate) -> None:
    if getattr(gate, "_quarantine_verdict_guard_installed", False):
        return
    previous = gate.ai_accepts

    @wraps(previous)
    def strict_ai_accepts(verdict, candidate=None):
        if not isinstance(verdict, dict):
            return False
        try:
            score = float(verdict.get("score"))
        except (TypeError, ValueError):
            return False
        scope = str(verdict.get("scope") or "").strip().lower()
        happened = verdict.get("happened") is True
        if not math.isfinite(score) or score < 0 or score > 10 or scope not in ALLOWED_SCOPES:
            return False
        if candidate is not None and gate.war_zone(candidate.get("title", "")):
            return score >= gate.WAR_ZONE_MIN_SCORE and happened and scope != "local"
        return bool(previous(verdict, candidate))

    gate.ai_accepts = strict_ai_accepts
    gate._quarantine_verdict_guard_installed = True
