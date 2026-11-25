"""Tests for state-file growth control (improvement 4).

Covers:
- _trim_rejected_record keeps the diagnostic core fields
- _save_rejected_history trims old records and caps length
- REJ_MAX in v13_review_log is within the analyzed budget
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("BOT_TOKEN", "OFFLINE_TEST_TOKEN")

import v13_intelligence as intel


FULL_RECORD = {
    "checked_at": "2026-11-25T00:00:00+00:00",
    "title": "یک خبر",
    "source": "irna.ir",
    "category": "ایران",
    "published_at": "2026-11-25T00:00:00+00:00",
    "url": "https://www.irna.ir/news/1",
    "age_seconds": 120,
    "intelligence_score": 3,
    "reason": "below-event-threshold",
    "stage": "intelligence_filter",
    "high_impact_security_candidate": False,
    "major_business_legal_candidate": False,
    "global_consequential_candidate": False,
    "unga_breaking_candidate": False,
}


class TrimRejectedRecordTests(unittest.TestCase):

    def test_keeps_diagnostic_core_fields(self):
        trimmed = intel._trim_rejected_record(FULL_RECORD)
        self.assertEqual(set(trimmed), set(intel.REJECTED_NEWS_KEEP_FIELDS))
        self.assertEqual(trimmed["title"], FULL_RECORD["title"])
        self.assertEqual(trimmed["reason"], FULL_RECORD["reason"])
        self.assertEqual(trimmed["intelligence_score"], FULL_RECORD["intelligence_score"])

    def test_drops_bulky_fields(self):
        trimmed = intel._trim_rejected_record(FULL_RECORD)
        for dropped in ("url", "published_at", "age_seconds",
                        "high_impact_security_candidate",
                        "major_business_legal_candidate",
                        "global_consequential_candidate",
                        "unga_breaking_candidate"):
            self.assertNotIn(dropped, trimmed)

    def test_trim_is_smaller_than_full_record(self):
        trimmed = intel._trim_rejected_record(FULL_RECORD)
        self.assertLess(
            len(json.dumps(trimmed, ensure_ascii=False)),
            len(json.dumps(FULL_RECORD, ensure_ascii=False)),
        )


class SaveRejectedHistoryTests(unittest.TestCase):

    def test_save_trims_records_and_caps_length(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "v13_rejected_news.json"
            old = intel.REJECTED_NEWS_FILE
            intel.REJECTED_NEWS_FILE = str(path)
            try:
                history = [dict(FULL_RECORD, title=f"خبر {i}") for i in range(600)]
                intel._save_rejected_history(history)
                saved = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(len(saved), intel.MAX_REJECTED_NEWS_HISTORY)
                # newest kept
                self.assertEqual(saved[-1]["title"], "خبر 599")
                # all rows trimmed
                for row in saved:
                    self.assertEqual(set(row), set(intel.REJECTED_NEWS_KEEP_FIELDS))
            finally:
                intel.REJECTED_NEWS_FILE = old

    def test_save_keeps_non_dict_entries_untouched(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "v13_rejected_news.json"
            old = intel.REJECTED_NEWS_FILE
            intel.REJECTED_NEWS_FILE = str(path)
            try:
                intel._save_rejected_history(["legacy-string-row"])
                saved = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(saved, ["legacy-string-row"])
            finally:
                intel.REJECTED_NEWS_FILE = old


class ReviewLogBudgetTests(unittest.TestCase):

    def test_rej_max_is_within_analyzed_budget(self):
        import v13_review_log as rl
        # cap must keep the full 48h window (~700/day measured) but stay
        # far below the old 4000 (which produced a 2.4 MB file per run)
        self.assertLessEqual(rl.REJ_MAX, 1500)
        self.assertGreaterEqual(rl.REJ_MAX, 1500)
        self.assertEqual(rl.REJ_KEEP_SECONDS, 48 * 3600)


if __name__ == "__main__":
    unittest.main()
