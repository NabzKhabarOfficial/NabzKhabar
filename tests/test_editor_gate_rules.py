"""Editor-gate hard-event rules and provider telemetry (Nov 2026 fix).

Regression tests for the false-block root causes found in the telemetry:
1. English hard events (hostage/kidnapped/...) were not in HARD_HAPPENED, so
   real events with score=6/happened=True missed the 6-bar and were blocked.
2. health['ai_pool'] was never written anywhere, so v13_monitor always
   reported an empty pool during publication outages.
3. v13_text_polish re-pinned CACHE_VERSION to "v4" at import time,
   undoing newer gate cache versions (v5).
Pure logic only - no network, no Telegram, no AI provider.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("BOT_TOKEN", "TEST_TOKEN")

import v13_editor_gate as gate


# --------------------------------------------------------------------------
# 1) English hard events are hard events now
# --------------------------------------------------------------------------
@pytest.mark.parametrize("title", [
    "Gunmen hold two dozen people hostage at supermarket in Colombia's Cartagena",
    "At least 14 killed in stadium stampede",
    "Dozens dead after earthquake strikes Turkey",
    "Passenger plane crashes near Sao Paulo",
    "Armed men kidnap 30 workers at mining site",
    "Ship sinks after collision in Manila Bay",
    "Train derails in Ohio, fire breaks out",
])
def test_english_hard_events_are_hard(title):
    assert gate.HARD_HAPPENED_EN.search(gate._norm(title)), title


@pytest.mark.parametrize("title", [
    "Hostage negotiation training course to be held in Qom",
    "Plane crash drill scheduled for next month",
])
def test_english_drills_are_hard_events_but_not_publishable(title):
    """A drill is a non-event: HARD match alone must not auto-publish.

    The deterministic veto intentionally lets English hard-event keywords
    pass through (they carry past-tense news most of the time), so the
    publish decision must still be gated by the AI verdict. A drill title
    with happened=False must therefore stay blocked - which is exactly the
    fail-closed behaviour the editorial policy requires.
    """
    assert gate.HARD_HAPPENED_EN.search(gate._norm(title)), title
    assert not gate.ai_accepts(
        {"score": 6, "happened": False, "scope": "world"},
        {"title": title},
    ), title


def test_english_course_without_hard_keyword_is_vetoed():
    reason = gate.deterministic_veto({"title": "Fire safety training course to be held in Qom"})
    assert reason == "editor-non-event"


def test_hard_event_keyword_alone_is_not_enough():
    """A keyword match without a happened verdict must still be blocked."""
    assert not gate.ai_accepts(
        {"score": 6, "happened": False, "scope": "world"},
        {"title": "Gunmen hold two dozen people hostage at supermarket in Colombia's Cartagena"},
    )


def test_cartagena_hostage_taking_passes_the_hard_bar():
    """The exact false block from v13_rejected_news.json (score=6, happened=True)."""
    candidate = {"title": "Gunmen hold two dozen people hostage at supermarket in Colombia's Cartagena"}
    verdict = {"score": 6, "happened": True, "scope": "world"}
    assert gate.ai_accepts(verdict, candidate)


def test_analysis_stays_blocked_even_with_hard_words():
    """A question/analysis headline must not become a hard event (fail-closed kept)."""
    assert not gate.ai_accepts(
        {"score": 4, "happened": False, "scope": "world"},
        {"title": "Is Libya a new front in the Ukraine war?"},
    )


def test_persian_hard_events_still_match():
    assert gate.HARD_HAPPENED_FA.search(gate._norm("در پی انفجار در تهران ۳ نفر کشته شدند"))
    assert gate.HARD_HAPPENED.search(gate._norm("۱۳ نفر در سقوط اتوبوس کشته شدند"))


def test_deterministic_veto_still_blocks_local_non_events():
    reason = gate.deterministic_veto({"title": "فرماندار شهرستان XYZ در جلسه شورای شهر"})
    assert reason in ("editor-local-level", "editor-non-event")


# --------------------------------------------------------------------------
# 2) Provider telemetry: ai_pool must be recorded
# --------------------------------------------------------------------------
class _FakeHealth:
    def __init__(self, tmp_path, monkeypatch, initial=None):
        self.file = tmp_path / "ai_model_health.json"
        self.file.write_text("{}", encoding="utf-8")
        import json as json_mod

        state = {"data": dict(initial or {})}

        def load():
            return state["data"]

        def save(health):
            state["data"] = health

        import v13_ai_router as router

        monkeypatch.setattr(router, "_load_health", load)
        monkeypatch.setattr(router, "_save_health", save)
        monkeypatch.setattr(gate, "_health_io", lambda: (load, save))
        self.state = state

    def pool(self):
        return self.state["data"].get("ai_pool") or {}


def test_record_pool_marks_attempt_and_success(tmp_path, monkeypatch):
    fake = _FakeHealth(tmp_path, monkeypatch)
    gate._record_pool(["groq/openai/gpt-oss-120b"])
    pool = fake.pool()
    entry = pool["groq/openai/gpt-oss-120b"]
    assert "last_tried" in entry and "last_attempt" in entry
    assert "last_success" not in entry

    gate._record_pool(["groq/openai/gpt-oss-120b"], ok=True)
    entry = fake.pool()["groq/openai/gpt-oss-120b"]
    assert "last_success" in entry


def test_record_pool_never_raises_on_broken_health(tmp_path, monkeypatch):
    import v13_ai_router as router

    def boom():
        raise RuntimeError("health unreadable")

    monkeypatch.setattr(router, "_load_health", boom)
    monkeypatch.setattr(gate, "_health_io", lambda: (boom, boom))
    gate._record_pool(["gemini/gemini-3.5-flash-lite"])  # must not raise


def test_ai_judge_records_tried_and_success(tmp_path, monkeypatch):
    fake = _FakeHealth(tmp_path, monkeypatch)

    class _Session:
        def post(self, url, **kwargs):
            class _Resp:
                ok = True
                status_code = 200

                def json(self):
                    return {"choices": [{"message": {"content":
                        '{"score": 8, "happened": true, "scope": "world", "reason": "ok"}'}}]}

            return _Resp()

    class _Main:
        SESSION = _Session()

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(gate, "AI_TIMEOUT", 1)

    verdict, provider = gate.ai_judge(_Main(), {"title": "big event", "summary": "text"})
    assert verdict and verdict["score"] == 8
    assert provider.startswith("groq/")
    pool = fake.pool()
    assert provider in pool
    assert "last_success" in pool[provider]


# --------------------------------------------------------------------------
# 3) Cache version floor in v13_text_polish
# --------------------------------------------------------------------------
def test_text_polish_keeps_newer_cache_version():
    import v13_text_polish as polish

    gate._text_polish = False  # allow the patch to run again
    gate.CACHE_VERSION = "v5"
    polish._patch_editor_gate()
    assert gate.CACHE_VERSION == "v5"
    gate._text_polish = False
    gate.CACHE_VERSION = "v3"
    polish._patch_editor_gate()
    assert gate.CACHE_VERSION == "v4"
    gate.CACHE_VERSION = "v5"  # restore for other tests


def test_editor_gate_cache_version_is_v5():
    assert gate.CACHE_VERSION == "v5"
