"""Unit tests for the v13 editor gate: veto, bars, and the guaranteed-publication fallback.

These tests run fully offline: AI judging and cache persistence are monkeypatched.
"""
import json
import os

import pytest

os.environ.setdefault("BOT_TOKEN", "TEST_TOKEN")

import v13_editor_gate as gate


# Titles used below deliberately avoid HARD_HAPPENED / WAR_ZONE patterns when a
# "soft but real" story is needed, so the normal bar for them stays 7.
SOFT_WORLD = "توافق تجاری جدید بین ایران و روسیه امضا شد"
SOFT_WORLD_2 = "قیمت نفت در بازار جهانی افزایش چشمگیری یافت"
ANALYSIS = "تحلیل کارشناس درباره وضعیت بازار ارز"
HARD_TITLE = "سقوط بالگرد در استانبول ۴ کشته بر جای گذاشت"
VETOED_TITLE = "کارگاه آموزشی هلال احمر استان اصفهان برگزار می شود"


def _story(title, **extra):
    story = {
        "title": title,
        "summary": "متن خبر برای آزمون",
        "source": "test",
        "url": "https://example.com/" + title[:8],
        "publication_tier": 4,
        "intelligence_score": 20,
    }
    story.update(extra)
    return story


class FakeJudge:
    """judge_fn replacement: plan maps title -> (ok, reason, verdict|None)."""

    def __init__(self, plan):
        self.plan = plan
        self.calls = []

    def __call__(self, main, candidate):
        self.calls.append(candidate["title"])
        ok, reason, verdict = self.plan[candidate["title"]]
        if verdict is not None:
            candidate["editor_verdict"] = dict(verdict)
        return ok, reason


@pytest.fixture(autouse=True)
def _clean_gate_state(monkeypatch):
    gate.REJECTED_THIS_RUN.clear()
    gate.UNUSED_RESERVES.clear()
    gate.FALLBACK_THIS_RUN.clear()
    monkeypatch.setattr(gate, "_audit", lambda *args, **kwargs: None)
    monkeypatch.delenv("EDITOR_GATE_FALLBACK", raising=False)
    yield
    gate.REJECTED_THIS_RUN.clear()
    gate.UNUSED_RESERVES.clear()
    gate.FALLBACK_THIS_RUN.clear()


def _verdict(score, happened, scope="world"):
    return {"score": score, "happened": happened, "scope": scope, "provider": "fake"}


# ---------------------------------------------------------------------------
# Normal bar stays strict (policy: MIN_AI_SCORE is never lowered globally)
# ---------------------------------------------------------------------------

def test_normal_bar_is_unchanged():
    assert gate.MIN_AI_SCORE == 7
    assert gate.HARD_EVENT_MIN_AI_SCORE == 6
    assert gate.WAR_ZONE_MIN_SCORE == 5


def test_normal_approval_skips_fallback():
    plan = {
        SOFT_WORLD: (True, "ai fake score=7", _verdict(7, True)),
        ANALYSIS: (False, "ai fake score=2", _verdict(2, False)),
    }
    pool = [_story(SOFT_WORLD), _story(ANALYSIS)]
    kept = gate.gate_pool(None, pool, target=2, judge_fn=FakeJudge(plan))
    assert [c["title"] for c in kept] == [SOFT_WORLD]
    assert not kept[0].get("editor_fallback_publication")
    assert gate.FALLBACK_THIS_RUN == []


# ---------------------------------------------------------------------------
# Guaranteed-publication fallback
# ---------------------------------------------------------------------------

def test_fallback_publishes_best_sub_bar_story_when_nothing_approved():
    plan = {
        ANALYSIS: (False, "ai fake score=2", _verdict(2, False)),
        SOFT_WORLD: (False, "ai fake score=6", _verdict(6, True)),
        SOFT_WORLD_2: (False, "ai fake score=5", _verdict(5, True)),
    }
    pool = [_story(ANALYSIS), _story(SOFT_WORLD), _story(SOFT_WORLD_2)]
    kept = gate.gate_pool(None, pool, target=4, judge_fn=FakeJudge(plan))
    assert len(kept) == 1
    assert kept[0]["title"] == SOFT_WORLD  # highest eligible score wins
    assert kept[0]["editor_fallback_publication"] is True
    assert gate.FALLBACK_THIS_RUN == [SOFT_WORLD]
    # the fallback story is not counted as an editorial block anymore
    assert SOFT_WORLD not in gate.REJECTED_THIS_RUN
    assert ANALYSIS in gate.REJECTED_THIS_RUN
    assert SOFT_WORLD_2 in gate.REJECTED_THIS_RUN


def test_fallback_finds_nothing_when_no_story_meets_the_lower_bar():
    plan = {
        ANALYSIS: (False, "ai fake score=4", _verdict(4, True)),       # score too low
        SOFT_WORLD: (False, "ai fake score=5", _verdict(5, False)),    # not happened
        SOFT_WORLD_2: (False, "ai local", _verdict(5, True, "local")),  # local scope
        HARD_TITLE: (False, "no-ai-fallback-fail-closed", None),       # no AI verdict
    }
    pool = [_story(x) for x in (ANALYSIS, SOFT_WORLD, SOFT_WORLD_2, HARD_TITLE)]
    kept = gate.gate_pool(None, pool, target=4, judge_fn=FakeJudge(plan))
    assert kept == []
    assert gate.FALLBACK_THIS_RUN == []


def test_fallback_can_be_disabled_with_env(monkeypatch):
    plan = {SOFT_WORLD: (False, "ai fake score=6", _verdict(6, True))}
    pool = [_story(SOFT_WORLD)]
    monkeypatch.setenv("EDITOR_GATE_FALLBACK", "0")
    assert not gate.fallback_enabled()
    kept = gate.gate_pool(None, pool, target=4, judge_fn=FakeJudge(plan))
    assert kept == []
    assert gate.FALLBACK_THIS_RUN == []
    monkeypatch.setenv("EDITOR_GATE_FALLBACK", "1")
    assert gate.fallback_enabled()  # default and explicit "1" keep it on


def test_fallback_ranking_prefers_hard_events_then_score():
    soft = _story(SOFT_WORLD, editor_verdict=_verdict(6, True))
    hard = _story(HARD_TITLE, editor_verdict=_verdict(6, True))
    assert gate.fallback_publication_pick([soft, hard]) is hard
    assert gate.fallback_publication_pick([hard, soft]) is hard


def test_fallback_pick_exclusions():
    assert gate.fallback_publication_pick([_story(ANALYSIS)]) is None  # no verdict
    assert gate.fallback_publication_pick([_story(SOFT_WORLD, editor_verdict=_verdict(4, True))]) is None
    assert gate.fallback_publication_pick([_story(SOFT_WORLD, editor_verdict=_verdict(5, False))]) is None
    assert gate.fallback_publication_pick([_story(SOFT_WORLD, editor_verdict=_verdict(5, True, "local"))]) is None
    vetoed = _story(VETOED_TITLE, editor_verdict=_verdict(6, True))
    assert gate.fallback_publication_pick([vetoed]) is None  # veto always wins


def test_fallback_only_when_nothing_approved_even_if_target_unmet():
    plan = {
        SOFT_WORLD: (True, "ai fake score=7", _verdict(7, True)),
        ANALYSIS: (False, "ai fake score=5", _verdict(5, True)),
    }
    pool = [_story(SOFT_WORLD), _story(ANALYSIS)]
    kept = gate.gate_pool(None, pool, target=3, judge_fn=FakeJudge(plan))
    # target 3 was not reached, but something was approved -> no fallback
    assert [c["title"] for c in kept] == [SOFT_WORLD]
    assert gate.FALLBACK_THIS_RUN == []


# ---------------------------------------------------------------------------
# judge(): verdict is stored on the candidate and in the cache entry
# ---------------------------------------------------------------------------

def test_judge_stores_verdict_and_cache_fields(monkeypatch):
    captured = {}

    def fake_ai_judge(main, candidate):
        return {"score": 6, "happened": True, "scope": "world", "topic": "سیاست",
                "reason": "test verdict"}, "fake/provider"

    monkeypatch.setattr(gate, "ai_judge", fake_ai_judge)
    monkeypatch.setattr(gate, "_cache_get", lambda key: None)
    monkeypatch.setattr(gate, "_cache_put", lambda key, entry: captured.update(entry))

    story = _story(SOFT_WORLD)
    ok, reason = gate.judge(None, story)
    assert ok is False  # 6 < 7 for a soft story, but the verdict is kept
    assert "score=6" in reason
    assert story["editor_verdict"]["score"] == 6
    assert story["editor_verdict"]["happened"] is True
    assert story["editor_verdict"]["scope"] == "world"
    # cache entry now carries the verdict fields so cached rejections can be
    # fallback-eligible without re-judging
    assert captured["score"] == 6
    assert captured["happened"] is True
    assert captured["scope"] == "world"
    assert captured["ok"] is False


def test_judge_restores_verdict_from_cache(monkeypatch):
    cached_entry = {
        "ok": False,
        "reason": "ai fake score=5 happened=True scope=world: cached reason",
        "score": 5,
        "happened": True,
        "scope": "world",
    }
    monkeypatch.setattr(gate, "_cache_get", lambda key: cached_entry)
    story = _story(SOFT_WORLD)
    ok, reason = gate.judge(None, story)
    assert ok is False
    assert reason.startswith("cached:")
    assert story["editor_verdict"]["score"] == 5
    assert story["editor_verdict"]["happened"] is True


def test_judge_veto_shortcircuits_before_ai(monkeypatch):
    calls = []

    def fake_ai_judge(main, candidate):
        calls.append(candidate["title"])
        return {"score": 9, "happened": True, "scope": "world"}, "fake/provider"

    monkeypatch.setattr(gate, "ai_judge", fake_ai_judge)
    monkeypatch.setattr(gate, "_cache_get", lambda key: None)
    monkeypatch.setattr(gate, "_cache_put", lambda key, entry: None)

    story = _story(VETOED_TITLE)
    ok, reason = gate.judge(None, story)
    assert ok is False
    assert reason == "editor-non-event"
    assert calls == []  # vetoed stories never cost AI


def test_cache_version_bumped_for_the_fallback_rule():
    # policy: version the editorial cache whenever rescue rules change
    assert gate.CACHE_VERSION == "v5"
    assert gate.FALLBACK_MIN_AI_SCORE == 5


# ---------------------------------------------------------------------------
# Telemetry: fallback publications are counted, not marked as blocks
# ---------------------------------------------------------------------------

def test_record_blocks_counts_fallback_publications(tmp_path):
    health_file = tmp_path / "v13_health.json"
    rejected = _story(ANALYSIS)
    fallback_story = _story(SOFT_WORLD)
    health_file.write_text(json.dumps({
        "publication_attempts": [],
        "selected_news_this_run": [rejected, fallback_story],
        "selected_for_publication": 2,
    }, ensure_ascii=False), encoding="utf-8")

    gate.REJECTED_THIS_RUN[ANALYSIS] = (rejected, "ai fake score=2")
    gate.FALLBACK_THIS_RUN.append(SOFT_WORLD)

    added = gate.record_blocks(str(health_file))
    assert added == 1
    health = json.loads(health_file.read_text(encoding="utf-8"))
    assert health["editorial_blocked_publications"] == 1
    assert health["fallback_publications"] == 1
    results = [x["result"] for x in health["publication_attempts"]]
    assert results == ["editorial_blocked"]
    assert health["publication_attempts"][0]["title"] == ANALYSIS
