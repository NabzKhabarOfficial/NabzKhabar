"""Explicit Telegram transport outcomes.

AMBIGUOUS means the request may have reached Telegram but the response
was lost. It must never be retried automatically.
"""

from enum import Enum


class PublicationOutcome(str, Enum):
    SUCCESS = "success"
    EXPLICIT_FAILURE = "explicit_failure"
    AMBIGUOUS = "ambiguous"


def classify(result):
    if result is True:
        return PublicationOutcome.SUCCESS

    if isinstance(result, dict) and result.get("ok") is True:
        return PublicationOutcome.SUCCESS

    if result is None:
        return PublicationOutcome.AMBIGUOUS

    return PublicationOutcome.EXPLICIT_FAILURE


def should_retry(outcome) -> bool:
    return classify(outcome) is PublicationOutcome.EXPLICIT_FAILURE
