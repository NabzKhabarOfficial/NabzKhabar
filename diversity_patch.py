"""NabzKhabar diversity + clustering performance patch.

Free only: no paid API/service is used.

Goals:
1) Make topic coverage more balanced (sports/football, AI/tech, society/family,
   science, culture/entertainment) while keeping breaking news able to win.
2) Add a proven sports RSS source without changing the existing source system.
3) Cache repeated same-story comparisons. The original clustering algorithm is
   preserved; only repeated identical title-pair comparisons are avoided.
"""

from functools import lru_cache
import main


# ------------------------------------------------------------
# Extra free RSS source: Varzesh3
# The feed URL is publicly documented as the site's web feed.
# ------------------------------------------------------------
EXTRA_DIRECT_FEEDS = [
    ("ورزش", "https://www.varzesh3.com/rss/list"),
]

for feed in EXTRA_DIRECT_FEEDS:
    if feed not in main.DIRECT_RSS_FEEDS:
        main.DIRECT_RSS_FEEDS.append(feed)


# ------------------------------------------------------------
# Focused Google News discovery for categories that were being
# underrepresented in the final four posts.
# ------------------------------------------------------------
EXTRA_GOOGLE_QUERIES = [
    ("فوتبال", main.google_news_search_url(
        "فوتبال ایران لیگ برتر استقلال پرسپولیس تراکتور"
    )),
    ("ورزش جهان", main.google_news_search_url(
        "ورزش فوتبال بسکتبال تنیس جهان"
    )),
    ("هوش مصنوعی", main.google_news_search_url(
        "هوش مصنوعی AI مدل جدید ابزار هوش مصنوعی"
    )),
    ("جامعه", main.google_news_search_url(
        "جامعه خانواده والدین فرزندان آموزش اجتماعی"
    )),
    ("علم", main.google_news_search_url(
        "علم فضا دانش پژوهش فناوری علمی"
    )),
    ("فرهنگ و سرگرمی", main.google_news_search_url(
        "سینما موسیقی بازیگر فیلم سریال فرهنگ سرگرمی"
    )),
]

for feed in EXTRA_GOOGLE_QUERIES:
    if feed not in main.GOOGLE_NEWS_FEEDS:
        main.GOOGLE_NEWS_FEEDS.append(feed)


# ------------------------------------------------------------
# Cache same-story comparisons.
# ------------------------------------------------------------
_ORIGINAL_SAME_STORY = main.same_story


def _same_story_cached(title_a, title_b):
    # The comparison is symmetric, so canonicalize the pair.
    if title_a > title_b:
        title_a, title_b = title_b, title_a
    return _ORIGINAL_SAME_STORY(
        {"title": title_a},
        {"title": title_b},
    )


@lru_cache(maxsize=30000)
def _cached_pair(title_a, title_b):
    return _same_story_cached(title_a, title_b)


def same_story(a, b):
    title_a = main.clean_title(a.get("title", ""))
    title_b = main.clean_title(b.get("title", ""))
    if not title_a or not title_b:
        return False
    return _cached_pair(title_a, title_b)


main.same_story = same_story


# ------------------------------------------------------------
# Diversity-aware selection.
# main.py already has a soft penalty. This adds a bonus for a
# family that has not appeared yet, while preserving important
# breaking stories because this is still only a modest adjustment.
# ------------------------------------------------------------
_ORIGINAL_DIVERSITY_PENALTY = main.diversity_penalty

DIVERSITY_BONUS_FAMILIES = {
    "ورزش",
    "فناوری",
    "جامعه",
    "علم",
    "فرهنگ",
    "سلامت",
    "خودرو",
    "انرژی",
    "بازار",
    "جهان",
}


def diversity_penalty(candidate, selected):
    original = _ORIGINAL_DIVERSITY_PENALTY(candidate, selected)
    family = main.category_family(candidate.get("category", ""))

    # Give an unseen family a modest boost. Once it has appeared,
    # the existing repetition penalty takes over.
    if selected and family in DIVERSITY_BONUS_FAMILIES:
        seen_families = {
            main.category_family(x.get("category", ""))
            for x in selected
        }
        if family not in seen_families:
            return original - 8

    return original


main.diversity_penalty = diversity_penalty

print(
    "DIVERSITY PATCH: focused sports/AI/society/science/culture discovery; "
    "Varzesh3 RSS enabled; cached story matching enabled; balanced selection enabled"
)
