"""Cold-boot simulation of the V13 patch chain (no network, no Telegram).

Imports every install() in the same order run_bot._install_v13_stack() uses,
then verifies the exact behaviours fixed in this change:

1. v13_text_polish must not downgrade the editor-gate cache version to v4
   (the gate bumped it to v5 so old wrong rejections are re-judged).
2. HARD_HAPPENED must match the real false-blocked stories from telemetry.
3. ai_judge must record provider attempts into health['ai_pool'].
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("BOT_TOKEN", "TEST_TOKEN")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import v13_editor_gate as gate

# --- 1) the exact order used by run_bot._install_v13_stack() -----------------
# (lightweight subset: the modules the fix touches, in their real order)
import v13_text_polish
v13_text_polish.install()
v13_text_polish._patch_editor_gate()

print("CACHE_VERSION after text_polish install:", gate.CACHE_VERSION)
assert gate.CACHE_VERSION == "v5", f"expected v5, got {gate.CACHE_VERSION}"
print("OK: text_polish no longer downgrades the cache to v4")

# --- 2) real false-blocked stories from v13_rejected_news.json ---------------
BLOCKED_STORIES = [
    "Gunmen hold two dozen people hostage at supermarket in Colombia's Cartagena",
]
for title in BLOCKED_STORIES:
    hard = bool(gate.HARD_HAPPENED.search(gate._norm(title)))
    assert hard, f"HARD_HAPPENED should match: {title}"
    accepted = gate.ai_accepts({"score": 6, "happened": True, "scope": "world"}, {"title": title})
    assert accepted, f"score=6 hard event should pass the bar now: {title}"
    print(f"OK: would now pass the 6-bar: {title[:70]}")

# Control: an analysis question must stay blocked.
assert not gate.ai_accepts(
    {"score": 4, "happened": False, "scope": "world"},
    {"title": "Is Libya a new front in the Ukraine war?"},
)
print("OK: analysis/opinion still blocked")

# --- 3) provider telemetry ----------------------------------------------------
class _Resp:
    ok = True
    status_code = 200

    def json(self):
        return {"choices": [{"message": {"content":
            '{"score": 8, "happened": true, "scope": "world", "reason": "ok"}'}}]}


class _Session:
    def post(self, url, **kwargs):
        return _Resp()


class _Main:
    SESSION = _Session()


os.environ["GROQ_API_KEY"] = "test-key"
os.environ.pop("AI_API_KEY", None)
os.environ.pop("OPENROUTER_API_KEY", None)

verdict, provider = gate.ai_judge(_Main(), {"title": "big event", "summary": "text"})
assert verdict and verdict["score"] == 8, verdict
print("ai_judge provider:", provider)

import v13_ai_router as router
health = router._load_health()
pool = health.get("ai_pool") or {}
assert provider in pool, f"ai_pool missing provider {provider}: {pool}"
assert "last_success" in pool[provider]
print("OK: ai_pool telemetry now records provider attempts/success")
print("\nALL COLD-BOOT CHECKS PASSED")
