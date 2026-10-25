import unittest
from types import SimpleNamespace
import quarantine_guard

class QuarantineGuardTests(unittest.TestCase):
    def test_manifest_and_existing_page_title_are_blocked(self):
        ids = quarantine_guard.quarantined_ids(); self.assertEqual(len(ids), 15)
        rid = next(iter(ids)); self.assertTrue(quarantine_guard.is_quarantined({"id": rid}))
        self.assertFalse(quarantine_guard.is_quarantined({"id": "not-quarantined"}))

    def test_bad_editor_verdict_is_rejected(self):
        gate = SimpleNamespace(WAR_ZONE_MIN_SCORE=5, war_zone=lambda title: False, ai_accepts=lambda verdict, candidate=None: True)
        quarantine_guard.install_editor_gate(gate)
        self.assertFalse(gate.ai_accepts({"score": 11, "happened": True, "scope": "world"}))
        self.assertFalse(gate.ai_accepts({"score": 8, "happened": True, "scope": "unknown"}))

    def test_rss_shaped_candidate_can_match_quarantined_page_title(self):
        ids = quarantine_guard.quarantined_ids(); rid = next(iter(ids)); page = quarantine_guard.NEWS / f"{rid}.html"
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(page.read_text(encoding="utf-8"), "html.parser")
        title = soup.find("h1").get_text(" ", strip=True)
        self.assertTrue(quarantine_guard.is_quarantined({"title": title, "link": "https://publisher.example/article"}))

if __name__ == "__main__": unittest.main()
