"""Regression: names used by the extracted v13_text_core helpers must resolve.

The module split (improvement 5) moved helpers into v13_text_core; a helper
that references a tunable left behind in v13_standalone only fails at CALL
time with NameError (it crashed a production run before these tests existed).
"""
import os
import time
from datetime import datetime, timedelta, timezone

os.environ.setdefault("BOT_TOKEN", "OFFLINE_TEST_TOKEN")

import v13_standalone as bot  # noqa: E402
import v13_text_core as core  # noqa: E402

NOW = datetime.now(timezone.utc)


def test_history_contains_story_runs_without_nameerror():
    now = int(time.time())
    assert core.history_contains_story("هر خبری", []) is False
    assert core.history_contains_story("یک خبر تکراری", [(now - 100, "یک خبر تکراری")]) is True
    assert core.history_contains_story(
        "خبر تازه درباره بازار ارز", [(now - 100, "قیمت سکه در بازار امروز")]
    ) is False


def test_is_fresh_runs_without_nameerror():
    assert core.is_fresh(None) is True
    assert core.is_fresh(NOW - timedelta(minutes=10)) is True   # inside the 0.5h window
    assert core.is_fresh(NOW - timedelta(hours=3)) is False     # outside
    assert core.is_fresh(NOW + timedelta(minutes=10)) is True   # negative age -> fresh


def test_constants_have_single_source():
    assert bot.SEMANTIC_HISTORY_DAYS == core.SEMANTIC_HISTORY_DAYS == 7
    assert bot.MAX_NEWS_AGE_HOURS == core.MAX_NEWS_AGE_HOURS == 0.5
