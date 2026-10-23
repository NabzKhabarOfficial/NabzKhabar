"""Import every module loaded indirectly by the Telegram runtime."""
import importlib


def test_all_runtime_modules_import():
    modules = [
        "v13_relevance_gate", "v13_growth", "v13_quality_fix", "v13_review_log",
        "v13_chrome_scrub", "v13_sports_desk", "v13_editorial_final_patch",
    ]
    for name in modules:
        importlib.import_module(name)
