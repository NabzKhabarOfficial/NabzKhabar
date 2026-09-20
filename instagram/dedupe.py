"""Persistent-friendly duplicate key generation for Instagram posts."""

from __future__ import annotations

import hashlib


def content_key(title: str, source_url: str = "") -> str:
    raw = f"{title.strip().lower()}|{source_url.strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
