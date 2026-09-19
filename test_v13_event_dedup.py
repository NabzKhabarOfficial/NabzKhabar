import unittest

from v13_event_dedup import event_score, fingerprint_debug


class EventDedupRegressionTests(unittest.TestCase):
    def test_testosterone_headlines_are_same_event(self):
        first = "ازسرگیری آزمایش اجباری تستوسترون برای نظامیان بالای ۳۰ سال آمریکا در پنتاگون"
        second = "پنتاگون سیاست جنجالی آزمایش تستوسترون برای نظامیان را از سر گرفت"
        self.assertGreaterEqual(event_score(first, second), 0.90)

    def test_unrelated_pentagon_story_is_not_same_event(self):
        first = "ازسرگیری آزمایش اجباری تستوسترون برای نظامیان بالای ۳۰ سال آمریکا در پنتاگون"
        other = "پنتاگون درباره هزینه عملیات نظامی آمریکا در خاورمیانه گزارش تازه‌ای منتشر کرد"
        self.assertLess(event_score(first, other), 0.90)

    def test_different_development_is_not_automatically_blocked(self):
        first = "پنتاگون آزمایش اجباری تستوسترون برای نظامیان بالای ۳۰ سال را از سر گرفت"
        other = "پنتاگون آزمایش تستوسترون برای نظامیان را پس از بررسی پزشکی متوقف کرد"
        self.assertLess(event_score(first, other), 0.90)

    def test_greenland_security_headlines_are_same_event(self):
        first = "توافق آمریکا و دانمارک درباره امنیت گرینلند"
        second = "ترامپ: توافق با دانمارک کنترل امنیتی گرینلند را به آمریکا می‌دهد"
        self.assertGreaterEqual(event_score(first, second), 0.90)

    def test_greenland_variants_match_with_summary_context(self):
        first_title = "توافق آمریکا و دانمارک درباره امنیت گرینلند"
        first_summary = "قرار است توافق هفته آینده امضا شود و امنیت گرینلند را پوشش می‌دهد."
        second_title = "ترامپ از توافق امنیتی با دانمارک درباره گرینلند خبر داد"
        second_summary = "این توافق حضور نظامی آمریکا را گسترش می‌دهد و روسیه و چین را از ایجاد پایگاه منع می‌کند."
        self.assertGreaterEqual(event_score(first_title, second_title, first_summary, second_summary), 0.90)

    def test_greenland_different_future_development_can_survive(self):
        first = "آمریکا و دانمارک درباره امنیت گرینلند به توافق رسیدند"
        other = "دانمارک توافق امنیتی گرینلند را پس از بررسی پارلمان متوقف کرد"
        self.assertLess(event_score(first, other), 0.90)

    def test_fingerprint_contains_event_dimensions(self):
        fp = fingerprint_debug("ترامپ توافق امنیتی با دانمارک درباره گرینلند را اعلام کرد؛ امضای توافق هفته آینده")
        self.assertIn("trump", fp["entities"])
        self.assertIn("denmark", fp["entities"])
        self.assertIn("greenland", fp["locations"])
        self.assertIn("greenland_security", fp["families"])
        self.assertTrue(fp["agreements"])
        self.assertIn("agreement", fp["actions"])


if __name__ == "__main__":
    unittest.main()
