import unittest
from types import SimpleNamespace

import quarantine_guard


class FailClosedBootstrapTests(unittest.TestCase):
    def test_final_guard_installer_is_present(self):
        module = SimpleNamespace(install=lambda: None)
        quarantine_guard.install_final_guard(module)
        self.assertTrue(module._quarantine_final_guard_installed)

    def test_quarantine_manifest_has_expected_entries(self):
        self.assertEqual(len(quarantine_guard.quarantined_ids()), 15)


if __name__ == "__main__":
    unittest.main()
