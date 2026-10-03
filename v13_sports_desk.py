"""NABZ V13 — sports desk.

The V13 rewrite stopped installing v13_relevance_gate, so its major-sports
path vanished and every sports story died in the intelligence filter as
"no-concrete-event". This module re-installs only that sports path (the
rest of the relevance gate stays as it is today) and widens it a little:

* Iran's national teams and Iranian athletes with a result or medal;
* decisive stages (final, semi-final, medal, title) of big tournaments,
  including the Asian Games (Nagoya 2026);
* the Tehran derby, world records, the Ballon d'Or.

Routine league games, rumours, transfers talk and interviews stay out, and
the final AI editor (v13_editor_gate) still has the last word; its rubric is
extended so Iranian medals and decisive results score as first-tier news.
"""
import re

import v13_relevance_gate as rg

EXTRA_SPORT = ("ناگویا", "جودو", "کاراته", "ووشو", "دوومیدانی", "کبدی", "بوکس",
               "تیراندازی با کمان", "قایقرانی", "مدال طلا", "مدال نقره", "مدال برنز",
               "استقلال تهران", "تراکتور تبریز")
EXTRA_BIG_STAGE = ("ناگویا", "بازی های آسیایی ناگویا", "جام حذفی", "لیگ نخبگان آسیا")
EXTRA_DECISIVE = ("به فینال رسید", "طلایی شد", "نایب قهرمان", "سکوی", "قهرمان شد")
SPORTS_QUERIES = (
    ("ورزش", "تیم ملی فوتبال ایران"),
    ("ورزش", "تیم ملی والیبال ایران"),
    ("ورزش", "بازی های آسیایی ناگویا ایران مدال"),
    ("ورزش", "کشتی ایران قهرمانی جهان"),
    ("ورزش", "پرسپولیس استقلال دربی"),
    ("ورزش", "لیگ قهرمانان اروپا"),
)
PROMPT_ANCHOR = "finals and decisive results of top sports competitions (World Cup, Olympics, Iran national team, Champions League final)."
PROMPT_SPORTS = ("finals and decisive results of top sports competitions (World Cup, Olympics, Champions League final); "
                 "results of Iran's national teams; medals, finals or titles won by Iranian athletes at the Asian Games, "
                 "world championships or Olympics (score these 7-8); the Tehran derby result.")


SCORE_LINE = r"[0-9۰-۹]{1,2}\s*[-–]\s*[0-9۰-۹]{1,2}"


def _words(words):
    # \w covers Persian letters but not Persian punctuation such as «؛», so
    # "ناگویا؛" still matches (the relevance gate's own boundary rejects it).
    alt = "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))
    return rf"(?<!\w)(?:{alt})(?!\w)"


def _merge(regex, words, extra_pattern=""):
    parts = [f"(?:{regex.pattern})", f"(?:{_words(words)})"]
    if extra_pattern:
        parts.append(f"(?:{extra_pattern})")
    return re.compile("|".join(parts), regex.flags)


def _widen():
    if getattr(rg, "_sports_desk_widened", False):
        return
    rg.SPORT = _merge(rg.SPORT, EXTRA_SPORT)
    rg.BIG_STAGE = _merge(rg.BIG_STAGE, EXTRA_BIG_STAGE)
    rg.DECISIVE = _merge(rg.DECISIVE, EXTRA_DECISIVE)
    rg.RESULT = _merge(rg.RESULT, ("شکست داد", "پیروز شد", "برتری"), SCORE_LINE)
    rg._sports_desk_widened = True


def _add_feeds(core):
    feeds = getattr(core, "GOOGLE_NEWS_FEEDS", None)
    builder = getattr(core, "google_news_search_url", None)
    if not isinstance(feeds, list) or not callable(builder):
        return 0
    existing = {(str(a), str(b)) for a, b in feeds}
    added = 0
    for category, query in SPORTS_QUERIES:
        try:
            feed = (category, builder(query))
        except Exception:
            continue
        if feed[1] and feed not in existing:
            feeds.append(feed)
            existing.add(feed)
            added += 1
    return added


def _extend_editor_prompt():
    try:
        import v13_editor_gate as eg
        if PROMPT_ANCHOR in eg.PROMPT:
            eg.PROMPT = eg.PROMPT.replace(PROMPT_ANCHOR, PROMPT_SPORTS)
            return True
    except Exception:
        pass
    return False


def install(core):
    import v13_intelligence
    import v13_policy_guard

    if getattr(core, "_sports_desk_installed", False):
        return
    _widen()
    min_score = int(getattr(v13_intelligence, "MIN_EVENT_SCORE", 7))
    previous = v13_intelligence.is_publishable

    def sports_gate(main_obj, candidate):
        ok, score, reason = previous(main_obj, candidate)
        level = rg.major_sports(candidate)
        if not level or reason == "recent-editorial-block":
            return ok, score, reason
        candidate["_major_sports"] = level
        if not candidate.get("category"):
            candidate["category"] = "ورزش"
        return True, max(int(score or 0), min_score + 3), "major-sports"

    v13_intelligence.is_publishable = sports_gate

    previous_tier = v13_intelligence._publication_tier

    def sports_tier(candidate):
        tier = previous_tier(candidate)
        level = candidate.get("_major_sports") or rg.major_sports(candidate)
        return max(int(tier or 1), level) if level else tier

    v13_intelligence._publication_tier = sports_tier

    previous_scope = v13_policy_guard._foreign_local_only

    def sports_scope(candidate):
        if rg.major_sports(candidate):
            return False
        return previous_scope(candidate)

    v13_policy_guard._foreign_local_only = sports_scope

    strict = getattr(core, "is_strictly_useful_news", None)
    if callable(strict):
        def sports_strict(candidate):
            return True if rg.major_sports(candidate) else strict(candidate)
        core.is_strictly_useful_news = sports_strict

    added = _add_feeds(core)
    prompt = _extend_editor_prompt()
    core._sports_desk_installed = True
    print(f"V13 SPORTS DESK ACTIVE: major sports allowed (+{added} feeds, editor rubric "
          f"{'extended' if prompt else 'unchanged'})", flush=True)
