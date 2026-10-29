import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ReconciliationGuardTests(unittest.TestCase):
    def test_owner_reconciled_source_is_blocked_without_sender_call(self):
        spec = importlib.util.spec_from_file_location("reconciliation_guard", ROOT / "reconciliation_guard.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        old = mod.REGISTRY
        try:
            with tempfile.TemporaryDirectory() as tmp:
                mod.REGISTRY = Path(tmp) / "reconciled.json"
                mod.REGISTRY.write_text(json.dumps({"entries": [{"source_url": "https://irna.ir/news/86306491", "titles": []}]}), encoding="utf-8")
                calls = []
                class Main: pass
                main = Main()
                main.process_news = lambda candidate, *a, **k: calls.append(candidate) or True
                mod.install(main)
                candidate = {"title": "new title", "link": "https://irna.ir/news/86306491?x=1"}
                self.assertFalse(main.process_news(candidate, {}, {}))
                self.assertEqual(calls, [])
                self.assertEqual(candidate["publication_status"], "skipped_duplicate")
        finally:
            mod.REGISTRY = old


if __name__ == "__main__":
    unittest.main()
