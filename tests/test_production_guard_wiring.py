"""Regression checks for production guard installation.

These are source-level checks by design: importing the launcher starts network and
provider state work, so the test must prove the wiring without executing the bot.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SITE = (ROOT / "sitecustomize.py").read_text(encoding="utf-8")
GUARD = (ROOT / "quarantine_guard.py").read_text(encoding="utf-8")


class ProductionGuardWiringTests(unittest.TestCase):
    def test_startup_hook_installs_launcher_guard(self):
        self.assertIn("quarantine_guard.install_launcher(module)", SITE)
        self.assertIn('root == "run_bot"', SITE)

    def test_startup_hook_installs_candidate_guard(self):
        self.assertIn("quarantine_guard.install_main(target, force=True)", SITE)
        self.assertIn('root in {"v13_standalone", "run_bot", "v13_ai_extra"}', SITE)

    def test_startup_hook_installs_editor_and_final_guards(self):
        self.assertIn("quarantine_guard.install_editor_gate", SITE)
        self.assertIn("quarantine_guard.install_final_guard(module)", SITE)

    def test_quarantine_guard_is_fail_closed_for_manifest_errors(self):
        self.assertIn("raise RuntimeError", GUARD)
        self.assertIn('publication_status"] = "quarantine_blocked"', GUARD)


if __name__ == "__main__":
    unittest.main()
