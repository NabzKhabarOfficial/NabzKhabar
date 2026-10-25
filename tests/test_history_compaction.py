import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from atomic_state import save_text


os.environ.setdefault("BOT_TOKEN", "OFFLINE_TEST_TOKEN")
import v13_standalone as bot


class HistoryCompactionTests(unittest.TestCase):
    def test_compaction_preserves_recent_hashes_and_duplicate_lookup(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "sent_news.txt"
            old_path = bot.HISTORY_FILE
            bot.HISTORY_FILE = str(path)
            try:
                hashes = {f"{i:064x}" for i in range(6000)}
                now = int(datetime.now(timezone.utc).timestamp())
                bot.save_history(hashes, [(now, "یک خبر مهم")])
                loaded_hashes, titles = bot.load_history()
                self.assertEqual(len(loaded_hashes), bot.MAX_HASH_HISTORY)
                self.assertIn(max(hashes), loaded_hashes)
                self.assertEqual(titles[0][1], "یک خبر مهم")
                self.assertLessEqual(len(path.read_text(encoding="utf-8").splitlines()), bot.MAX_HASH_HISTORY + 1)
                self.assertFalse(any(p.suffix == ".tmp" for p in path.parent.iterdir()))
            finally:
                bot.HISTORY_FILE = old_path

    def test_malformed_hash_entries_are_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "sent_news.txt"
            old_path = bot.HISTORY_FILE
            bot.HISTORY_FILE = str(path)
            try:
                valid = "a" * 64
                path.write_text("not-a-hash\n" + valid + "\n", encoding="utf-8")
                hashes, titles = bot.load_history()
                self.assertEqual(hashes, {valid})
                self.assertEqual(titles, [])
            finally:
                bot.HISTORY_FILE = old_path

    def test_atomic_text_writes_never_leave_partial_content(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.txt"
            payloads = [str(i) + ":" + ("x" * 10000) for i in range(8)]
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(lambda value: save_text(path, value), payloads))
            self.assertIn(path.read_text(encoding="utf-8"), payloads)
            self.assertFalse(any(p.suffix == ".tmp" for p in path.parent.iterdir()))


if __name__ == "__main__":
    unittest.main()
