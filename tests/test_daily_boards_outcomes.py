import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import daily_boards


class DailyBoardPhotoOutcomeTests(unittest.TestCase):
    def test_confirmed_photo_success(self):
        response = type("Response", (), {"ok": True, "status_code": 200, "text": ""})()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "photo.jpg"
            path.write_bytes(b"test")
            with patch.dict(os.environ, {"BOT_TOKEN": "offline-test-token"}), patch(
                "daily_boards.requests.post", return_value=response
            ) as post:
                self.assertIs(daily_boards.send_photo(path, "caption"), True)
                post.assert_called_once()

    def test_explicit_rejection_allows_fallback(self):
        response = type("Response", (), {"ok": False, "status_code": 400, "text": "bad request"})()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "photo.jpg"
            path.write_bytes(b"test")
            with patch.dict(os.environ, {"BOT_TOKEN": "offline-test-token"}), patch(
                "daily_boards.requests.post", return_value=response
            ):
                self.assertIs(daily_boards.send_photo(path, "caption"), False)

    def test_timeout_is_ambiguous_and_must_not_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "photo.jpg"
            path.write_bytes(b"test")
            with patch.dict(os.environ, {"BOT_TOKEN": "offline-test-token"}), patch(
                "daily_boards.requests.post", side_effect=__import__("requests").Timeout("offline timeout")
            ):
                outcome = daily_boards.send_photo(path, "caption")
                self.assertIsNone(outcome)
                self.assertIsNot(outcome, False)


if __name__ == "__main__":
    unittest.main()
