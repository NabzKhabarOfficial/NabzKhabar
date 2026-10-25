import unittest

from v13_status import (
    PublicationStatus,
    VALID_PUBLICATION_STATUSES,
    is_non_failure,
    normalize_status,
)


class PublicationStatusSchemaTests(unittest.TestCase):
    def test_required_statuses_are_canonical(self):
        self.assertEqual(
            VALID_PUBLICATION_STATUSES,
            {
                "published", "failed", "ambiguous", "editorial_blocked",
                "quality_blocked", "skipped_duplicate", "ai_unavailable",
            },
        )

    def test_legacy_labels_normalize(self):
        self.assertEqual(normalize_status("success"), PublicationStatus.PUBLISHED.value)
        self.assertEqual(normalize_status("exception"), PublicationStatus.FAILED.value)
        self.assertEqual(normalize_status("duplicate"), PublicationStatus.SKIPPED_DUPLICATE.value)

    def test_unknown_status_fails_closed(self):
        self.assertEqual(normalize_status("mystery-status"), "unknown")
        self.assertFalse(is_non_failure("mystery-status"))

    def test_editorial_blocks_are_non_failure(self):
        self.assertTrue(is_non_failure("editorial_blocked"))
        self.assertTrue(is_non_failure("quality_blocked"))
        self.assertTrue(is_non_failure("skipped_duplicate"))
        self.assertFalse(is_non_failure("ambiguous"))


if __name__ == "__main__":
    unittest.main()
