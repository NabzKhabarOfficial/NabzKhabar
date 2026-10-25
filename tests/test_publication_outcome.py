import unittest
from publication_outcome import PublicationOutcome, classify, should_retry

class PublicationOutcomeTests(unittest.TestCase):
    def test_timeout_is_ambiguous_and_never_retried(self):
        self.assertEqual(classify(None), PublicationOutcome.AMBIGUOUS)
        self.assertFalse(should_retry(None))

    def test_explicit_failure_is_retryable(self):
        self.assertEqual(classify(False), PublicationOutcome.EXPLICIT_FAILURE)
        self.assertTrue(should_retry(False))

    def test_success_is_not_retryable(self):
        self.assertEqual(classify({"ok": True}), PublicationOutcome.SUCCESS)
        self.assertFalse(should_retry({"ok": True}))

if __name__ == "__main__": unittest.main()
