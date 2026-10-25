import tempfile
import unittest
from pathlib import Path
import atomic_state

class AtomicStateTests(unittest.TestCase):
    def test_round_trip_and_no_temp_leftover(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "state.json"
            atomic_state.save_json(p, {"n": 1, "fa": "نبض"})
            self.assertEqual(atomic_state.load_json(p), {"n": 1, "fa": "نبض"})
            self.assertFalse(list(Path(td).glob("*.tmp")))

    def test_corrupt_state_is_quarantined(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "state.json"
            p.write_text("{broken", encoding="utf-8")
            self.assertEqual(atomic_state.load_json(p, {"safe": True}), {"safe": True})
            self.assertTrue(list(Path(td).glob("state.json.corrupt-*")))

if __name__ == "__main__": unittest.main()
