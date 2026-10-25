import os
import unittest
from unittest.mock import patch

import v13_ai_router


class AIRouterSafetyTests(unittest.TestCase):
    def test_json_must_be_object(self):
        self.assertEqual(v13_ai_router._clean_json('{"ok": true}'), {"ok": True})
        with self.assertRaises((ValueError, TypeError)):
            v13_ai_router._clean_json('["not", "an", "object"]')
        with self.assertRaises((ValueError, TypeError)):
            v13_ai_router._clean_json('"scalar"')

    def test_configured_secret_is_redacted(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "offline-secret-key-123456"}):
            self.assertNotIn("offline-secret-key-123456", v13_ai_router._redact(
                "provider error offline-secret-key-123456"
            ))
            self.assertIn("[REDACTED]", v13_ai_router._redact(
                "provider error offline-secret-key-123456"
            ))

    def test_common_provider_token_patterns_are_redacted(self):
        value = "bad token gsk_abcdefghijklmnopqrstuvwxyz123456789"
        self.assertNotIn("gsk_abcdefghijklmnopqrstuvwxyz123456789", v13_ai_router._redact(value))


if __name__ == "__main__":
    unittest.main()
