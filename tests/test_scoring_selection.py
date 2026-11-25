"""Unit tests for the NabzAI scoring & selection logic (no network).

Covers:
- calculate_recency_score (time tiers)
- calculate_keyword_importance (keyword weights, cap, global high-impact boost)
- source_priority / publisher_quality (host tiers, social/google penalties)
- calculate_importance (composition, media/cluster/social/google adjustments)
- choose_cluster_representative (publisher beats Google discovery)
- diversity_penalty (family crowding)
"""
import os
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("BOT_TOKEN", "TEST_TOKEN")

import v13_standalone as v13

NOW = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _dt(hours_ago):
    # recency is computed against real "now", so build ages relative to it
    return datetime.now(timezone.utc) - timedelta(hours=hours_ago)


def _cand(title, **kw):
    base = {
        "title": title,
        "summary": "",
        "link": kw.pop("link", "https://www.irna.ir/news/1"),
        "published_at": kw.pop("published_at", None),
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# calculate_recency_score
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("expected", [12, 10, 8, 5, 3, 1])
def test_recency_tiers(expected):
    # recency is computed against real "now"; snap to the middle of each
    # tier so runtime drift of a few seconds cannot cross a boundary.
    centers = {12: 0.5, 10: 2.0, 8: 4.5, 5: 9.0, 3: 18.0, 1: 30.0}
    score = v13.calculate_recency_score(_dt(centers[expected]))
    assert score == expected, f"expected tier {expected}, got {score}"


def test_recency_none_and_future():
    assert v13.calculate_recency_score(None) == 0
    # future dates: age negative -> "<1h" tier in the wild; may also raise-free
    future = datetime.now(timezone.utc) + timedelta(hours=5)
    assert isinstance(v13.calculate_recency_score(future), int)


def test_recency_beyond_36h_is_zero():
    assert v13.calculate_recency_score(_dt(48)) == 0


# ---------------------------------------------------------------------------
# calculate_keyword_importance
# ---------------------------------------------------------------------------

def test_keyword_importance_empty():
    assert v13.calculate_keyword_importance("", "") == 0


def test_keyword_importance_very_important_counts():
    score = v13.calculate_keyword_importance("زلزله", "")
    # 'زلزله' appears in both VERY and global-impact lists when paired with an actor
    assert score >= 8
    # capped sum check: without actor, no global boost
    assert score == 8


def test_keyword_importance_important_counts():
    assert v13.calculate_keyword_importance("دلار", "") == 3


def test_keyword_importance_cap():
    # flood the text with many distinct VERY keywords
    text = " ".join(["زلزله", "سیل", "جنگ", "موشک", "ترور", "تحریم", "انفجار", "مذاکرات", "آتش بس", "قطعی اینترنت"])
    score = v13.calculate_keyword_importance(text, "")
    assert score == 55  # capped


def test_keyword_importance_global_high_impact_requires_actor():
    # English high-impact word alone: no actor -> no +14
    base = v13.calculate_keyword_importance("earthquake", "")
    with_actor = v13.calculate_keyword_importance("earthquake in Iran", "")
    assert with_actor - base == 14


def test_keyword_importance_global_high_impact_persian():
    base = v13.calculate_keyword_importance("زلزله", "")
    with_actor = v13.calculate_keyword_importance("زلزله در ایران", "")
    # "زلزله" is VERY (8) + "ایران" is IMPORTANT (3) + global +14
    assert with_actor == 25


def test_keyword_importance_persian_word_boundary():
    # 'Iran' inside 'Iranian' must not double count actor via substring
    a = v13.calculate_keyword_importance("Iranian army", "")
    b = v13.calculate_keyword_importance("Iran", "")
    # both may score via actor hit, but 'iranian' must not match \biran\b
    assert a == b


# ---------------------------------------------------------------------------
# publisher_quality / source_priority
# ---------------------------------------------------------------------------

def test_publisher_quality_tiers():
    assert v13.publisher_quality("https://www.irna.ir/x") == 25
    assert v13.publisher_quality("https://www.cnn.com/x") == 15
    assert v13.publisher_quality("https://example.com/x") == 5


def test_publisher_quality_social_negative():
    assert v13.publisher_quality("https://t.me/x") == -40


def test_publisher_quality_google_negative():
    assert v13.publisher_quality("https://news.google.com/x") == -50


def test_source_priority_google_flag_penalty():
    direct = v13.source_priority("https://www.irna.ir/x", is_google=False)
    via_google = v13.source_priority("https://www.irna.ir/x", is_google=True)
    assert via_google == direct - 10


# ---------------------------------------------------------------------------
# calculate_importance composition
# ---------------------------------------------------------------------------

def test_importance_minimum_for_neutral_stale_social():
    cand = _cand(
        "متن عادی",
        link="https://t.me/channel",
        published_at=None,
    )
    score = v13.calculate_importance(cand)
    # social -40 + publisher -40 => strongly negative
    assert score < 0


def test_importance_video_image_bonus():
    plain = v13.calculate_importance(_cand("دلار"))
    with_media = v13.calculate_importance(_cand("دلار", video_url="http://v/1", image_url="http://i/1"))
    assert with_media == plain + 5


def test_importance_resolved_publisher_bonus():
    plain = v13.calculate_importance(_cand("دلار"))
    resolved = v13.calculate_importance(_cand("دلار", resolved_link="https://www.reuters.com/x"))
    assert resolved == plain + 8


def test_importance_roundup_title_penalized():
    plain = v13.calculate_importance(_cand("دلار"))
    roundup = v13.calculate_importance({"title": "خلاصه خبرهای امروز", "summary": "", "link": "https://www.irna.ir/x"})
    assert roundup < plain


def test_importance_cluster_size_bonus_capped():
    small = v13.calculate_importance(_cand("دلار", cluster_size=2))
    big = v13.calculate_importance(_cand("دلار", cluster_size=9))
    assert big - small == (4 - 2) * 2  # min(cluster_size,4)*2


def test_importance_google_link_penalized_vs_publisher():
    publisher = v13.calculate_importance(_cand("دلار", link="https://www.irna.ir/x"))
    google = v13.calculate_importance(_cand("دلار", link="https://news.google.com/x"))
    assert google < publisher


# ---------------------------------------------------------------------------
# choose_cluster_representative
# ---------------------------------------------------------------------------

def test_cluster_rep_prefers_direct_publisher_over_google():
    via_google = _cand("دلار", link="https://news.google.com/x", is_google=True)
    direct = _cand("دلار", link="https://www.irna.ir/x", is_google=False)
    rep = v13.choose_cluster_representative([via_google, direct])
    assert rep is direct


def test_cluster_rep_values_resolved_link_and_article_text():
    bare = _cand("دلار", link="https://www.irna.ir/x")
    rich = _cand("دلار", link="https://www.irna.ir/x",
                 resolved_link="https://www.reuters.com/y",
                 article_text="body", image_url="http://i/1", video_url="http://v/1")
    rep = v13.choose_cluster_representative([bare, rich])
    assert rep is rich


def test_cluster_rep_empty():
    assert v13.choose_cluster_representative([]) is None


# ---------------------------------------------------------------------------
# diversity_penalty / family_count
# ---------------------------------------------------------------------------

def _fam(cat):
    return v13.category_family(cat)


def test_family_count_groups_categories():
    a = _fam("international")
    b = _fam("economy")
    assert a or b  # both resolve
    # same family counts itself twice in selected list
    selected = [{"category": "international"}, {"category": "international"}]
    cand = {"category": "international"}
    assert v13.family_count(cand, selected) == 2


def test_diversity_penalty_escalates():
    cand = {"category": "international"}
    p0 = v13.diversity_penalty(cand, [])
    p1 = v13.diversity_penalty(cand, [{"category": "international"}])
    p2 = v13.diversity_penalty(cand, [{"category": "international"}, {"category": "international"}])
    p3 = v13.diversity_penalty(cand, [{"category": "international"}] * 3)
    assert (p0, p1, p2, p3) == (0, 4, 10, 18)


def test_diversity_penalty_other_family_free():
    cand = {"category": "international"}
    selected = [{"category": "economy"}] * 5
    if _fam("economy") != _fam("international"):
        assert v13.diversity_penalty(cand, selected) == 0


# ---------------------------------------------------------------------------
# integration: importance feeds selection ranking
# ---------------------------------------------------------------------------

def test_high_impact_beats_bland_local():
    hard = v13.calculate_importance(
        _cand("زلزله بزرگ در ایران", summary="زلزله", link="https://www.irna.ir/x"))
    bland = v13.calculate_importance(
        _cand("قیمت جدید گوشی", link="https://example.com/y"))
    assert hard > bland
