"""Canonical publication outcome schema shared by V13 runtime and monitoring."""
from enum import Enum


class PublicationStatus(str, Enum):
    PUBLISHED = "published"
    FAILED = "failed"
    AMBIGUOUS = "ambiguous"
    EDITORIAL_BLOCKED = "editorial_blocked"
    QUALITY_BLOCKED = "quality_blocked"
    SKIPPED_DUPLICATE = "skipped_duplicate"
    AI_UNAVAILABLE = "ai_unavailable"


VALID_PUBLICATION_STATUSES = frozenset(item.value for item in PublicationStatus)
_ALIASES = {
    "success": PublicationStatus.PUBLISHED.value,
    "explicit_failure": PublicationStatus.FAILED.value,
    "publication_ambiguous": PublicationStatus.AMBIGUOUS.value,
    "failure": PublicationStatus.FAILED.value,
    "exception": PublicationStatus.FAILED.value,
    "duplicate": PublicationStatus.SKIPPED_DUPLICATE.value,
}


def normalize_status(value) -> str:
    """Normalize legacy labels to the canonical schema; unknown labels fail closed."""
    normalized = str(value or "").strip().lower()
    normalized = _ALIASES.get(normalized, normalized)
    return normalized if normalized in VALID_PUBLICATION_STATUSES else "unknown"


def is_non_failure(value) -> bool:
    return normalize_status(value) in {
        PublicationStatus.EDITORIAL_BLOCKED.value,
        PublicationStatus.QUALITY_BLOCKED.value,
        PublicationStatus.SKIPPED_DUPLICATE.value,
    }
