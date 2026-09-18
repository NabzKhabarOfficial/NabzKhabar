import unittest

from v13_event_dedup import event_score


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
        # The subject is related, but the second headline describes a new
        # development and should not be treated as an identical event solely
        # because it shares the same event vocabulary.
        self.assertLess(event_score(first, other), 0.90)


if __name__ == "__main__":
    unittest.main()
