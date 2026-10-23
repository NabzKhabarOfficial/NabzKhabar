"""Stable, Persian-aware identity keys for Instagram stories."""
from __future__ import annotations
import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from .content import normalize_fa

_TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid", "ref", "source"}


def canonical_url(url: str = "") -> str:
    value = normalize_fa(url).lower().strip()
    if not value:
        return ""
    try:
        p = urlsplit(value)
        query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if k not in _TRACKING and not k.startswith("utm_")]
        return urlunsplit((p.scheme or "https", p.netloc.removeprefix("www."), p.path.rstrip("/") or "/", urlencode(sorted(query)), ""))
    except ValueError:
        return value


def normalized_title(title: str) -> str:
    text = normalize_fa(title).lower()
    text = re.sub(r"[^\w\u0600-\u06ff]+", " ", text)
    return " ".join(text.split())


def content_key(title: str, source_url: str = "", event_key: str = "") -> str:
    raw = "|".join((normalized_title(title), canonical_url(source_url), normalize_fa(event_key).lower()))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def media_key(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
