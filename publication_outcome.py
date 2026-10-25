"""Explicit Telegram transport outcomes.

Callers must not retry or send a text fallback for AMBIGUOUS. A timeout can
mean Telegram accepted the request while the response was lost.
"""
from enum import Enum

class PublicationOutcome(str, Enum):
    SUCCESS = "success"
    EXPLICIT_FAILURE = "explicit_failure"
    AMBIGUOUS = "ambiguous"


def classify(result):
    if result is True or (isinstance(result, dict) and result.get("ok") is True):
        return PublicationOutcome.SUCCESS
    if result is None:
        return PublicationOutcome.AMBIGUOUS
    return PublicationOutcome.EXPLICIT_FAILURE


def should_retry(outcome) -> bool:
    return classify(outcome) is PublicationOutcome.EXPLICIT_FAILURE
