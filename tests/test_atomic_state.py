import tempfile
import unittest
from pathlib import Path

import atomic_state


class AtomicStateTests(unittest.TestCase):
    def test_round_trip_and_no_temp_leftover(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"

            atomic_state.save_json(
                path,
                {
                    "number": 1,
                    "persian": "نبض",
                },
            )

            self.assertEqual(
                atomic_state.load_json(path),
                {
                    "number": 1,
                    "persian": "نبض",
                },
            )

            self.assertFalse(
                list(Path(directory).glob("*.tmp"))
            )

    def test_corrupt_state_is_quarantined(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text("{broken", encoding="utf-8")

            result = atomic_state.load_json(
                path,
                {"safe": True},
            )

            self.assertEqual(result, {"safe": True})
            self.assertTrue(
                list(
                    Path(directory).glob(
                        "state.json.corrupt-*"
                    )
                )
            )


if __name__ == "__main__":
    unittest.main()
