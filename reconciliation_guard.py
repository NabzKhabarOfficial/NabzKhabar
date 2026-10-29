"""Prevent duplicate Telegram sends for owner-reconciled publications.

This registry is intentionally narrow and evidence-backed. It is not a general
truth database: entries are added only after the owner confirms the story is
already visible in the channel.
"""
from __future__ import annotations
import json
import re
from functools import wraps
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REGISTRY = ROOT / "reconciled_publications.json"


def _norm(value):
    return re.sub(r"\s+", " ", str(value or "").replace("ي", "ی").replace("ك", "ک")).strip().lower()


def _load():
    try:
        data = json.loads(REGISTRY.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"entries": []}
    except (OSError, ValueError):
        return {"entries": []}


def _matches(candidate, entries):
    title = _norm(candidate.get("title") or candidate.get("headline"))
    urls = {str(candidate.get(k) or "").split("?", 1)[0].rstrip("/") for k in ("link", "url", "resolved_link", "source_url")}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("source_url") and str(entry["source_url"]).split("?", 1)[0].rstrip("/") in urls:
            return entry
        titles = {_norm(x) for x in entry.get("titles", []) if x}
        if title and title in titles:
            return entry
    return None


def install(main):
    if getattr(main, "_reconciliation_guard_installed", False):
        return
    previous = main.process_news
    @wraps(previous)
    def reconciled_process(candidate, *args, **kwargs):
        entry = _matches(candidate, _load().get("entries", []))
        if entry:
            candidate["publication_status"] = "skipped_duplicate"
            candidate["reconciliation"] = {
                "status": "already_published",
                "evidence": entry.get("evidence", "owner-confirmed channel post"),
                "recorded_at": entry.get("recorded_at", ""),
            }
            print("V13 RECONCILIATION: already published; no Telegram send: " + str(candidate.get("title", "")), flush=True)
            return False
        return previous(candidate, *args, **kwargs)
    main.process_news = reconciled_process
    main._reconciliation_guard_installed = True
