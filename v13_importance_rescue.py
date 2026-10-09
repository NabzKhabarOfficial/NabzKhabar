"""NABZ V13 — AI importance rescue (Oct 2026).

Owner's rule: no important news may be lost. Most early filters are keyword
rules («iran-local-routine», «low-value», «strict-source-below-importance»,
«routine-metaphorical-topic» ...). They are cheap, but a real first-tier story
that happens to use the "wrong" words is dropped before any AI ever sees it.

This layer gives every such rejected story with a plausible importance signal
a second opinion from the same free AI editor-in-chief that makes the final
call (v13_editor_gate.ai_judge, same rubric). If the AI says it is first-tier
news (score >= 7, happened, not local; war-zone reports >= 5) the story is put
back into the pool, and the final editor gate reuses this verdict from its
cache, so it costs no second call. Duplicates, recently blocked, old or
already-published stories are never touched here: the dedup chain still runs.

* Cost cap: MAX_CALLS new AI verdicts per run (time budget BUDGET_SECONDS);
  every verdict is cached 24h, so a headline is judged at most once a day.
* Free providers only (Groq, Gemini flash-lite, OpenRouter free), as the gate.
* Fail-safe: any error keeps the original decision.
* Log: ai_model_health.json -> _importance_rescue_log.
"""

import re
import time

MAX_CALLS = 5
BUDGET_SECONDS = 60
LOG_KEY = "_importance_rescue_log"
LOG_ITEMS = 80

# Rejections that are judgements about importance made by keyword rules.
RULE_REASONS = (
    "iran-local-routine", "local-routine-low-value", "routine-metaphorical-topic", "low-value",
    "no-concrete-event", "below-event-threshold", "strict-source-below-importance",
    "strict-source-local-routine", "foreign-local-preselection", "final-scope-preselection",
    "analysis-or-opinion", "foreign-soft-local", "routine-statement", "editor-local-level",
    "editor-non-event",
)

SIGNAL = re.compile(
    r"(?:کشته|جان باخت|جان سپرد|زخمی|مجروح|مصدوم|مفقود|زلزله|سیل|طوفان|آتش ?سوزی|انفجار|سقوط|غرق|ریزش|"
    r"تصادف|واژگون|گروگان|ترور|تیراندازی|حمله|درگیری|"
    r"دلار|ارز|بنزین|گازوئیل|قیمت|تورم|بورس|طلا|سکه|یارانه|کالابرگ|حقوق|مالیات|بانک مرکزی|"
    r"اینترنت|فیلتر|قطعی (?:برق|آب|گاز)|خاموشی|تعطیل|کنکور|اعدام|بازداشت|حکم|دادگاه|"
    r"مجلس|دولت|وزیر|رهبر|رئیس ?جمهور|پزشکیان|عراقچی|سپاه|ارتش|ترامپ|پوتین|نتانیاهو|هسته|تحریم|"
    r"مذاکره|توافق|آتش ?بس|تنگه هرمز|"
    r"killed|dead|died|deaths|injured|earthquake|flood|storm|hurricane|typhoon|wildfire|crash|explosion|"
    r"shooting|hostage|president|prime minister|minister|election|court|ruling|sanction|oil|"
    r"market|stocks|nuclear|ceasefire|talks|deal|record|emergency)",
    re.I,
)
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
STATE = {"calls": 0, "started": None}


def _eg():
    import v13_editor_gate as eg
    return eg


def eligible(candidate, reason):
    reason = str(reason or "")
    # Only keyword importance rules; duplicates, history, freshness, ads and
    # recent editorial blocks are never in this list.
    if not any(reason.startswith(r) for r in RULE_REASONS):
        return False
    title = str(candidate.get("title", "") or "")
    if len(title.strip()) < 15:
        return False
    text = title + " " + str(candidate.get("summary", "") or candidate.get("description", "") or "")[:400]
    return bool(SIGNAL.search(text) or re.search(r"\d{2,}", text.translate(_DIGITS)))


def _log(entry):
    try:
        import v13_ai_router as r
        health = r._load_health()
        log = health.get(LOG_KEY)
        if not isinstance(log, list):
            log = []
        log.append(entry)
        health[LOG_KEY] = log[-LOG_ITEMS:]
        r._save_health(health)
    except Exception:
        pass


def second_opinion(main, candidate, reason):
    """(rescue?, tier, note). Uses the editor gate cache first, then the AI."""
    eg = _eg()
    key = eg._cache_key(candidate)
    cached = eg._cache_get(key)
    if cached is not None:
        return bool(cached.get("ok")), 3, "cached"
    if STATE["started"] is None:
        STATE["started"] = time.monotonic()
    if STATE["calls"] >= MAX_CALLS or time.monotonic() - STATE["started"] > BUDGET_SECONDS:
        return False, 0, "budget"
    STATE["calls"] += 1
    verdict, provider = eg.ai_judge(main, candidate)
    if not verdict:
        return False, 0, "no-ai"
    ok = bool(eg.ai_accepts(verdict, candidate))
    note = (f"ai {provider} score={verdict.get('score')} happened={verdict.get('happened')} "
            f"scope={verdict.get('scope')}: {verdict.get('reason', '')}")
    candidate["editor_topic"] = str(verdict.get("topic", "") or "")
    eg._cache_put(key, {"ok": ok, "reason": note, "topic": candidate["editor_topic"]})
    _log({"t": int(time.time()), "title": str(candidate.get("title", ""))[:120], "rule": str(reason)[:60],
          "rescued": ok, "ai": note[:160]})
    tier = 4 if int(verdict.get("score", 0) or 0) >= 8 else 3
    return ok, tier, note


def install(main):
    import v13_intelligence as intel
    previous = intel.is_publishable

    def ai_rescue(main_obj, candidate):
        ok, score, reason = previous(main_obj, candidate)
        if ok:
            return ok, score, reason
        try:
            if not eligible(candidate, reason):
                return ok, score, reason
            eg = _eg()
            if eg.rescue_tier(candidate, reason):
                return ok, score, reason  # the editor gate's own rescue path takes it
            rescued, tier, note = second_opinion(main_obj or main, candidate, reason)
            if not rescued:
                return ok, score, reason
            candidate["editor_rescue_tier"] = max(int(candidate.get("editor_rescue_tier", 0) or 0), tier)
            print(f"V13 AI IMPORTANCE RESCUE: [{reason}] -> back in pool ({note[:90]}) {candidate.get('title', '')}",
                  flush=True)
            return True, max(int(score or 0), 14 if tier >= 4 else 11), "ai-importance-rescue:" + str(reason)[:50]
        except Exception as exc:
            print(f"V13 AI IMPORTANCE RESCUE: skipped ({type(exc).__name__}).", flush=True)
            return ok, score, reason

    intel.is_publishable = ai_rescue
    print(f"V13 AI IMPORTANCE RESCUE ACTIVE: keyword rejections get an AI second opinion "
          f"(max {MAX_CALLS} new verdicts/run, 24h cache).", flush=True)
