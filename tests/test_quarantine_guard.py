import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import quarantine_guard


class QuarantineGuardTests(unittest.TestCase):
    def test_manifest_is_loaded_and_known_id_is_blocked(self):
        ids = quarantine_guard.quarantined_ids()
        self.assertEqual(len(ids), 15)
        self.assertTrue(quarantine_guard.is_quarantined({"id": next(iter(ids))}))
        self.assertFalse(quarantine_guard.is_quarantined({"id": "not-quarantined"}))

    def test_editor_verdict_schema_rejects_bad_scope_and_score(self):
        gate = SimpleNamespace(
            WAR_ZONE_MIN_SCORE=5,
            war_zone=lambda title: False,
            ai_accepts=lambda verdict, candidate=None: True,
        )
        quarantine_guard.install_editor_gate(gate)
        self.assertFalse(gate.ai_accepts({"score": 11, "happened": True, "scope": "world"}))
        self.assertFalse(gate.ai_accepts({"score": 8, "happened": True, "scope": "unknown"}))


if __name__ == "__main__":
    unittest.main()
