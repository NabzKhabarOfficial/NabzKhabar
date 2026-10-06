"""NABZ KHABAR — final editor gate (the last word before publication).

Why this exists
---------------
Every earlier filter is a keyword *blacklist*, and several layers are
*overrides* that bypass the blacklists when a "big" word appears. A word such
as «سیل» inside «امداد سیلاب» (a Red Crescent training course) turned a local
PR story into a tier-4 "security" story that skipped every other filter. New
kinds of junk always slipped through, so each fix only moved the problem.

This gate inverts the logic: a story is published only when it is *positively*
first-tier news. It runs last, after every override and rescue, so nothing can
bypass it:

1. Deterministic veto (every candidate): non-events (courses, training,
   drills, preparedness, conferences, ceremonies, inaugurations, visits,
   plans) and city/county-level stories, unless a hard event really happened.
2. AI editor-in-chief: scores 0-10 against a strict "front page of
   BBC/Reuters, or nationwide Iran news" rubric. Published only if
   score >= 7, the event happened, scope not local.
3. If every AI provider fails: fail closed; only clearly hard, already
   happened, non-local events pass.
Decisions are cached for 24h so a rejected story never costs AI again.

Backfill (root-cause fix, Oct 2026)
-----------------------------------
The selection engine used to hand this gate only its top 4 stories. When the
AI rejected all 4 (often weak "tier-4" local items), the run published
nothing, while real first-tier stories ranked 5th-10th were never even
judged. Now the engine is asked for a wider pool (POOL_SIZE) and the gate
walks down it in rank order until it has approved the normal per-run
number of stories. Plain (tier-1) event-valid stories are admitted as
reserves too, because the ranker alone often offered only 4. Unjudged
extras are removed from the run's telemetry so the monitor does not count
them as lost publications.

Official positions (Oct 2026)
-----------------------------
"Hormuz stays closed until our seven conditions are met" (parliament speaker)
and "a decision on Iran is coming, easy way or hard way" (US president) were
rejected as mere "statements". On war, ceasefire, Hormuz, nuclear talks,
sanctions and negotiations, a position announced by a top official IS the
event. The rubric now says so, strategic keywords (Hormuz, nuclear,
proposal, conditions...) get the rescue path, and the cache key is versioned
so old wrong rejections are judged again. Speculation and analysis stay low.

War zone (Oct 2026)
-------------------
"Huge explosions in north Riyadh" was rejected as "local" / "unverified"
while Yemen was striking Saudi airports and Aramco. During the regional war,
explosions, interceptions, air-raid sirens and missile/drone attacks in the
capitals and major cities of the countries involved (and on energy sites or
shipping in Hormuz / Red Sea / Bab el-Mandeb) are world news, never local.
WAR_ZONE marks them as hard events: they skip the local veto, get the rescue
path, the rubric says so explicitly, and the AI bar for them is 5 instead of 7.
"""

import json
import os
import re
import time

MIN_AI_SCORE = 7
CACHE_KEY = "_editor_gate_cache"
CACHE_VERSION = "v3"    # bump when the rubric changes: old verdicts are ignored
CACHE_TTL = 24 * 3600
CACHE_MAX = 600
AI_TIMEOUT = 15
AI_BUDGET_PER_STORY = 40
POOL_SIZE = 20          # how many ranked stories the gate may walk through
JUDGE_BUDGET = 180      # seconds of AI judging per run (job timeout is 12 min)

GROQ_MODELS = ("openai/gpt-oss-120b", "openai/gpt-oss-20b")
GEMINI_MODELS = ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite")


def _norm(text):
    text = str(text or "").replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ")
    return re.sub(r"\s+", " ", text).strip()


def _text(candidate, limit=900):
    parts = [candidate.get("title", ""), candidate.get("summary", "") or candidate.get("description", "")]
    return _norm(" ".join(str(p or "") for p in parts))[:limit]


# --------------------------------------------------------------------------
# 1) Deterministic veto
# --------------------------------------------------------------------------
NON_EVENT = re.compile(
    r"(?:دوره (?:آموزشی|کشوری|تخصصی|ملی|استانی|مهارت)|توانمند ?سازی|مهارت ?افزایی|کارگاه(?: آموزشی)?|"
    r"آموزش (?:امدادگران|نیروها|کارکنان|شهروندان)|آماده ?سازی|آمادگی (?:برای|در برابر|مقابله)|"
    r"رزمایش|مانور|تمرین (?:امداد|میدانی)|همایش|هم ?اندیشی|سمینار|وبینار|نشست (?:تخصصی|علمی|خبری|هم)|"
    r"جشنواره|نمایشگاه|افتتاح|کلنگ ?زنی|بهره ?برداری|بازدید|تجلیل|تقدیر از|نکوداشت|گرامیداشت|"
    r"بزرگداشت|سالگرد|مراسم|برگزار (?:می ?شود|شد|خواهد شد|می ?گردد)|میزبانی [^،؛.]{0,25} از|"
    r"قرار است|در دستور کار|برنامه ریزی برای|تشکیل کمیته|کارگروه|جلسه شورای)"
)
LOCAL_LEVEL = re.compile(
    r"(?:شهرستان|بخشدار|بخشداری|فرماندار|فرمانداری|دهیار|دهیاری|روستای|روستاهای|شهردار|شهرداری|"
    r"شورای شهر|امام جمعه|استاندار|استانداری|مدیرکل|اداره کل|هلال احمر استان|"
    r"(?:در|از) استان [^\s،]+|میزبانی (?:شهر |شهرستان )?[^\s،]+ از)"
)
# Hard event that already happened (title only, past tense / tolls).
HARD_HAPPENED = re.compile(
    r"(?:کشته (?:شد|شدند)|\d+\s*کشته|جان (?:باخت|باختند|سپرد)|کشته و زخمی|\d+\s*(?:نفر )?زخمی|"
    r"انفجار (?:در|رخ)|زلزله(?: ای)? (?:\d|به بزرگی|شدید)|سقوط (?:هواپیما|بالگرد)|"
    r"حمله (?:موشکی|پهپادی|هوایی|تروریستی)|حمله کرد|بمباران|ترور|گروگان|"
    r"killed|dead|explosion|earthquake|airstrike|missile strike|plane crash)",
    re.I,
)
# Regional war: events in capitals / major cities / energy and shipping hubs of the
# countries involved are first-tier, never "local".
WAR_PLACES = (
    r"(?<!\w)(?:ریاض|جده|جیزان|جازان|نجران|ابها|ینبع|رابغ|دمام|ظهران|دوحه|دبی|ابوظبی|ابو ظبی|فجیره|کویت|منامه|بحرین|مسقط|"
    r"تل ?آویو|حیفا|اورشلیم|ایلات|بیروت|دمشق|بغداد|اربیل|کرکوک|صنعا|عدن|حدیده|موچا|تهران|اصفهان|"
    r"شیراز|تبریز|مشهد|بندرعباس|بندر عباس|بوشهر|خارک|چابهار|کیش|قشم|هرمز|خلیج فارس|دریای سرخ|باب ?المندب|"
    r"آرامکو|پالایشگاه|riyadh|jeddah|doha|dubai|abu dhabi|kuwait|manama|bahrain|muscat|tel aviv|haifa|"
    r"jerusalem|eilat|beirut|damascus|baghdad|erbil|sanaa|aden|hodeidah|tehran|isfahan|bandar abbas|"
    r"hormuz|red sea|bab el-mandeb|aramco|refinery)"
)
WAR_EVENT = (
    r"(?:انفجار|صدای انفجار|آژیر|پدافند|رهگیری|سرنگون|اصابت|موشک|پهپاد|حمله(?! قلبی| مغزی)|بمباران|"
    r"explosion|blast|siren|intercept|shot down|missile|drone|strike|attack)"
)
WAR_ZONE = re.compile(
    WAR_EVENT + r"[^.؛]{0,60}" + WAR_PLACES + r"|" + WAR_PLACES + r"[^.؛]{0,60}" + WAR_EVENT,
    re.I,
)
WAR_ZONE_MIN_SCORE = 5


def war_zone(title):
    return bool(WAR_ZONE.search(_norm(title)))


STRATEGIC = re.compile(
    r"(?:سپاه|ارتش|نیروی دریایی|ناتو|آمریکا|اسرائیل|روسیه|چین|کره شمالی|تنگه هرمز|خلیج فارس|"
    r"شورای امنیت|سازمان ملل|nato|pentagon|navy)",
    re.I,
)


# --------------------------------------------------------------------------
# 1b) Rescue: upstream keyword filters also kill real first-tier stories
# (e.g. "13 dead in Saveh-Hamadan bus crash" -> no-concrete-event, or
# "Russia strikes second major bridge in Kyiv" -> local-routine-low-value).
# Stories with a strong event signal get a second chance; the AI editor
# below still has the final say, so junk cannot sneak in through this path.
# --------------------------------------------------------------------------
RESCUABLE_REASONS = (
    "no-concrete-event", "final-scope-preselection", "foreign-local-preselection",
    "below-event-threshold", "analysis-or-opinion", "foreign-soft-local",
    "routine-statement", "strict-source-below-importance", "local-routine-low-value",
)
STRONG_EVENT = re.compile(
    r"(?:هدف قرار (?:داد|دادند|گرفت)|حمله (?:کرد|کردند)|حملات|حمله به|تجاوز|ربود|"
    r"اعزام [^،؛]{0,30}نیرو|هزاران نیرو|ناو هواپیمابر|ناو جنگی|"
    r"(?:تسلط|تصرف|کنترل) [^،؛]{0,25}(?:شهر|منطقه|بندر)|"
    r"بانک مرکزی|نرخ (?:ارز|دلار)|قیمت (?:دلار|بنزین|نفت|طلا)|تحریم|آتش ?بس|مذاکرات|مذاکره|توافق|"
    r"استعفا|برکنار|بازداشت|اعدام|تنگه هرمز|هرمز|ممنوعیت|لغو شد|تصویب شد|رد کرد|"
    r"هسته ای|برنامه هسته|پیشنهاد(?:ات|ها)? (?:جدید|آمریکا|ایران)|شروط|شرط های|اولتیماتوم|محاصره|"
    r"تهدید|زخمی|مجروح|اعتراض|کودتا|آشوب|شورش|ازسرگیری|از سر گرفت|"
    r"\bstrikes?\b|struck|attack|troops|aircraft carrier|deploy|sanction|ceasefire|captur|seiz|"
    r"intercept|suspend|\bbans?\b|banned|reject|protest|detain|arrest|injur|wound|"
    r"hormuz|nuclear|negotiat|proposal|ultimatum|blockade|conditions|"
    r"hostage|coup|resign|riot|resum|permission to)",
    re.I,
)
SPORT_WORDS = re.compile(
    r"(?:فوتبال|فوتسال|والیبال|بسکتبال|لیگ|جام |تیم |گل |cycling|football|league|cup\b|match)", re.I)


def rescue_tier(candidate, reason):
    """0 = no rescue; 3/4 = publication tier for a rescued strong story."""
    reason = str(reason or "")
    if not any(reason.startswith(r) for r in RESCUABLE_REASONS):
        return 0
    title = _norm(candidate.get("title", ""))
    if not title or deterministic_veto(candidate):
        return 0
    hard = bool(HARD_HAPPENED.search(title)) or war_zone(title)
    if SPORT_WORDS.search(title) and not hard:
        return 0
    if hard:
        return 4
    if STRONG_EVENT.search(title):
        return 3
    return 0


def deterministic_veto(candidate):
    """Reason string when the story can never be first-tier news, else ""."""
    title = _norm(candidate.get("title", ""))
    if not title:
        return ""
    hard = bool(HARD_HAPPENED.search(title))
    if NON_EVENT.search(title) and not hard and not STRATEGIC.search(title):
        return "editor-non-event"
    if LOCAL_LEVEL.search(title) and not hard and not war_zone(title):
        return "editor-local-level"
    return ""


# --------------------------------------------------------------------------
# 2) AI editor-in-chief
# --------------------------------------------------------------------------
PROMPT = """You are the editor-in-chief of "NABZ KHABAR", a Persian Telegram news channel that publishes ONLY first-tier news.
First-tier = a story that BBC Persian / Reuters / AP would put among today's top stories, OR Iranian news that matters to people across the whole country.

Give a HIGH score (7-10) only for a concrete event that has ALREADY happened or an official decision already taken, with wide national or international consequences, e.g.:
wars, attacks, military escalation; major disasters or accidents with deaths or large damage; decisions of heads of state, governments, parliaments, central banks;
sanctions, nuclear talks, ceasefires; big economic shocks (currency, fuel price, oil, inflation); election results; death or arrest of world-famous people;
landmark court rulings; global-scale tech/business events; finals and decisive results of top sports competitions (World Cup, Olympics, Iran national team, Champions League final).

OFFICIAL POSITIONS COUNT AS EVENTS: when a head of state or government, a top negotiator, a foreign minister or their official spokesman,
a parliament speaker or a top military commander announces a position on war, ceasefire, the Strait of Hormuz, the nuclear programme, sanctions
or Iran-US/international negotiations, the announcement itself has happened (happened=true). Score it 7-9 when it sets, changes or confirms
a concrete position, condition, proposal, deadline, threat of an imminent decision or a reply to the other side
(e.g. "Hormuz will stay closed until our seven conditions are met", "the US sent new proposals through Qatar", "a decision on Iran is coming").

REGIONAL WAR ZONE: a regional war involving Iran, the US, Israel, Saudi Arabia, the Gulf states and Yemen is under way. Explosions, air-raid sirens,
interceptions, missile or drone strikes and fires reported in the capitals or major cities of these countries, or at oil/energy facilities and
shipping in Hormuz, the Persian Gulf, the Red Sea or Bab el-Mandeb, are WORLD news: scope="world", happened=true when the outlet reports them
(e.g. "explosions heard in Riyadh"), score 7-9. They are NEVER "local", even before the cause is confirmed.

Give a LOW score (0-4) to: local, provincial, county or city news; training courses, drills, exercises, preparedness, plans, intentions, "will be held";
conferences, meetings, ceremonies, anniversaries, inaugurations, visits, awards; warnings or forecasts with no event yet; opinions, slogans, sermons,
routine officials' remarks on non-strategic topics; analysis, explainers or speculation about what might happen; claims by lower officials or commentators;
PR of organisations (Red Crescent, municipalities, ministries' routine programmes); culture/art events; minor crimes; celebrity, lifestyle, product reviews.

Story:
TITLE: %s
TEXT: %s

Return only JSON:
{"score": 0-10, "happened": true or false, "scope": "world" or "iran_national" or "local", "topic": "سیاست|نظامی|حادثه|اقتصاد|فناوری|سلامت|ورزش|قضایی|آب و هوا|جامعه", "reason": "max 12 words"}"""


def _parse(raw):
    raw = str(raw or "").strip()
    raw = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", raw)
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(raw[start:end + 1])
    except Exception:
        return None
    if not isinstance(data, dict) or "score" not in data:
        return None
    try:
        data["score"] = int(round(float(data.get("score"))))
    except Exception:
        return None
    happened = data.get("happened")
    data["happened"] = happened is True or str(happened).lower() == "true"
    data["scope"] = str(data.get("scope", "")).lower()
    return data


def _openai_style(session, url, key, model, prompt, extra=None):
    payload = {"model": model, "temperature": 0, "max_tokens": 400,
               "messages": [{"role": "user", "content": prompt}],
               "response_format": {"type": "json_object"}}
    payload.update(extra or {})
    r = session.post(url, timeout=AI_TIMEOUT, json=payload,
                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                              "User-Agent": "NabzKhabar-EditorGate/1.0"})
    if not r.ok:
        raise RuntimeError(f"HTTP {r.status_code}")
    content = (r.json().get("choices") or [{}])[0].get("message", {}).get("content", "")
    return _parse(content)


def ai_judge(main, candidate):
    """(verdict dict, provider) or (None, "") when every provider failed."""
    session = getattr(main, "SESSION", None)
    if session is None:
        import requests
        session = requests.Session()
    title = _norm(candidate.get("title", ""))
    body = _norm(candidate.get("summary", "") or candidate.get("description", "") or candidate.get("article_text", ""))[:900]
    prompt = PROMPT % (title, body)
    deadline = time.monotonic() + AI_BUDGET_PER_STORY
    groq = os.getenv("GROQ_API_KEY", "").strip()
    gem = str(getattr(main, "AI_API_KEY", "") or os.getenv("AI_API_KEY", "")).strip()
    orouter = os.getenv("OPENROUTER_API_KEY", "").strip()
    attempts = []
    if groq:
        attempts += [("groq/" + m, lambda m=m: _openai_style(
            session, "https://api.groq.com/openai/v1/chat/completions", groq, m, prompt,
            {"include_reasoning": False})) for m in GROQ_MODELS]
    if gem:
        def _gemini(m):
            r = session.post(f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent",
                             params={"key": gem}, timeout=AI_TIMEOUT,
                             json={"contents": [{"parts": [{"text": prompt}]}],
                                   "generationConfig": {"responseMimeType": "application/json", "temperature": 0}})
            if not r.ok:
                raise RuntimeError(f"HTTP {r.status_code}")
            parts = ((r.json().get("candidates") or [{}])[0].get("content") or {}).get("parts") or [{}]
            return _parse(parts[0].get("text", ""))
        attempts += [("gemini/" + m, lambda m=m: _gemini(m)) for m in GEMINI_MODELS]
    if orouter:
        attempts.append(("openrouter/free", lambda: _openai_style(
            session, "https://openrouter.ai/api/v1/chat/completions", orouter, "openrouter/free", prompt)))
    for name, call in attempts:
        if time.monotonic() >= deadline:
            break
        try:
            verdict = call()
            if verdict:
                return verdict, name
            print(f"V13 EDITOR GATE: {name} returned no usable verdict", flush=True)
        except Exception as exc:
            print(f"V13 EDITOR GATE: {name} failed ({exc})", flush=True)
    return None, ""


def ai_accepts(verdict, candidate=None):
    score = int(verdict.get("score", 0))
    if candidate is not None and war_zone(candidate.get("title", "")) and not NON_EVENT.search(_norm(candidate.get("title", ""))):
        return score >= WAR_ZONE_MIN_SCORE  # war-zone reports: happened, never local
    return (score >= MIN_AI_SCORE and verdict.get("happened")
            and verdict.get("scope") != "local")


def fallback_accepts(candidate):
    """No AI available: only clearly hard, already-happened, non-local events."""
    title = _norm(candidate.get("title", ""))
    if war_zone(title):
        return True
    return bool(HARD_HAPPENED.search(title)) and not LOCAL_LEVEL.search(title) and not NON_EVENT.search(title)


# --------------------------------------------------------------------------
# Cache (persisted inside ai_model_health.json, which the workflow commits)
# --------------------------------------------------------------------------
def _health_io():
    import v13_ai_router
    return v13_ai_router._load_health, v13_ai_router._save_health


def _cache_key(candidate):
    return CACHE_VERSION + "|" + _norm(candidate.get("title", "")).lower()


def _cache_get(key):
    try:
        load, _ = _health_io()
        entry = (load().get(CACHE_KEY) or {}).get(key)
        if entry and float(entry.get("until", 0)) > time.time():
            return entry
    except Exception:
        pass
    return None


def _cache_put(key, entry):
    try:
        load, save = _health_io()
        health = load()
        cache = {k: v for k, v in (health.get(CACHE_KEY) or {}).items()
                 if float(v.get("until", 0) or 0) > time.time()}
        entry["until"] = time.time() + CACHE_TTL
        cache[key] = entry
        if len(cache) > CACHE_MAX:
            cache = dict(sorted(cache.items(), key=lambda kv: kv[1].get("until", 0))[-CACHE_MAX:])
        health[CACHE_KEY] = cache
        save(health)
    except Exception as exc:
        print(f"V13 EDITOR GATE: cache warning {exc}", flush=True)


# Stories this gate rejected after selection, so telemetry can count them as
# deliberate editorial blocks instead of "selected but not published".
REJECTED_THIS_RUN = {}
# Pool stories that were never judged (enough approved / time budget used).
# They were only backfill reserves, so they are removed from the run's
# "selected" telemetry instead of being reported as lost publications.
UNUSED_RESERVES = set()


def record_blocks(health_file="v13_health.json"):
    """Fix this run's telemetry: rejections -> editorial_blocked, reserves -> not selected."""
    if not REJECTED_THIS_RUN and not UNUSED_RESERVES:
        return 0
    try:
        with open(health_file, "r", encoding="utf-8") as f:
            health = json.load(f)
    except Exception as exc:
        print(f"V13 EDITOR GATE: telemetry read warning {type(exc).__name__}: {exc}", flush=True)
        return 0
    changed = False
    if UNUSED_RESERVES:
        selected = health.get("selected_news_this_run") or []
        kept = [x for x in selected if str(x.get("title", "")).strip() not in UNUSED_RESERVES]
        if len(kept) != len(selected):
            health["selected_news_this_run"] = kept
            health["selected_for_publication"] = len(kept)
            changed = True
    attempts = health.setdefault("publication_attempts", [])
    have = {str(x.get("title", "")).strip() for x in attempts}
    added = 0
    for title, (candidate, reason) in REJECTED_THIS_RUN.items():
        if title in have:
            continue
        attempts.append({"title": title, "source": candidate.get("source", ""), "url": candidate.get("url", ""),
                         "result": "editorial_blocked", "reason": "editor_gate: " + reason[:180], "error": ""})
        added += 1
    if added:
        health["editorial_blocked_publications"] = int(health.get("editorial_blocked_publications", 0) or 0) + added
        changed = True
    if changed:
        with open(health_file, "w", encoding="utf-8") as f:
            json.dump(health, f, ensure_ascii=False, indent=2)
        print(f"V13 EDITOR GATE: telemetry fixed ({added} editorial_blocked, "
              f"{len(UNUSED_RESERVES)} unused reserve(s) removed)", flush=True)
    return added


def _audit(main, candidate, score, reason):
    try:
        import v13_intelligence as intel
        history = intel._load_rejected_history()
        history.append(intel._rejected_record(main, candidate, score, reason, stage="editor_gate"))
        intel._save_rejected_history(history)
    except Exception:
        pass


def judge(main, candidate):
    """(publish?, reason). Never raises."""
    veto = deterministic_veto(candidate)
    if veto:
        return False, veto
    key = _cache_key(candidate)
    cached = _cache_get(key)
    if cached:
        return bool(cached.get("ok")), "cached:" + str(cached.get("reason", ""))
    verdict, provider = ai_judge(main, candidate)
    if verdict:
        ok = bool(ai_accepts(verdict, candidate))
        reason = f"ai {provider} score={verdict.get('score')} happened={verdict.get('happened')} scope={verdict.get('scope')}: {verdict.get('reason', '')}"
        candidate["editor_topic"] = str(verdict.get("topic", "") or "")
        _cache_put(key, {"ok": ok, "reason": reason, "topic": candidate["editor_topic"]})
        return ok, reason
    ok = fallback_accepts(candidate)
    return ok, "no-ai-fallback-" + ("hard-event" if ok else "fail-closed")


def gate_pool(main, pool, target, budget=JUDGE_BUDGET, judge_fn=None):
    """Walk the ranked pool until `target` stories are approved. Returns approved list."""
    judge_fn = judge_fn or judge
    kept = []
    started = time.monotonic()
    for index, candidate in enumerate(pool):
        title = str(candidate.get("title", "")).strip()
        if len(kept) >= target or time.monotonic() - started > budget:
            UNUSED_RESERVES.update(str(c.get("title", "")).strip() for c in pool[index:])
            break
        ok, reason = judge_fn(main, candidate)
        print(f"V13 EDITOR GATE: {'PUBLISH' if ok else 'REJECT'} [{reason}] {candidate.get('title', '')}", flush=True)
        if ok:
            kept.append(candidate)
        else:
            _audit(main, candidate, int(candidate.get("intelligence_score", 0) or 0), reason[:200])
            REJECTED_THIS_RUN[title] = (candidate, reason)
    return kept


# --------------------------------------------------------------------------
# Accident label fix: «🚨 حادثه» only when something actually happened.
# --------------------------------------------------------------------------
INCIDENT_WORDS = ("انفجار", "تصادف", "سقوط", "غرق", "ریزش", "آتش سوزی", "آتش گرفت", "واژگون")


def _patch_topic_label():
    try:
        import v13_post_design as pd
    except Exception:
        return
    if getattr(pd.topic_of, "_editor_gate", False):
        return
    original = pd.topic_of

    def topic_of(title, label):
        emoji, name = original(title, label)
        if name != "حادثه":
            return emoji, name
        text = _norm(title)
        if any(w in text for w in pd.HAPPENED) or any(w in text for w in INCIDENT_WORDS) or HARD_HAPPENED.search(text):
            return emoji, name
        for t_emoji, t_name, words in pd.TOPICS:
            if any(w in text for w in words):
                return t_emoji, t_name
        return pd.TOPIC_DEFAULT

    topic_of._editor_gate = True
    pd.topic_of = topic_of


# --------------------------------------------------------------------------
# Install: outermost layer on both selection functions.
# --------------------------------------------------------------------------
def install(main):
    import v13_intelligence as intel

    previous_publishable = intel.is_publishable

    def editor_publishable(main_obj, candidate):
        ok, score, reason = previous_publishable(main_obj, candidate)
        if not ok:
            tier = rescue_tier(candidate, reason)
            if not tier:
                return ok, score, reason
            candidate["editor_rescue_tier"] = tier
            print(f"V13 EDITOR GATE: rescue tier {tier} [{reason}] {candidate.get('title', '')}", flush=True)
            return True, max(int(score or 0), 14 if tier >= 4 else 11), "editor-rescue:" + str(reason)[:60]
        veto = deterministic_veto(candidate)
        if veto:
            return False, 0, veto
        return ok, score, reason

    intel.is_publishable = editor_publishable

    previous_tier = intel._publication_tier
    reserve_mode = {"on": False}

    def real_tier(candidate):
        return max(int(previous_tier(candidate) or 1), int(candidate.get("editor_rescue_tier", 0) or 0))

    def editor_tier(candidate):
        real = real_tier(candidate)
        if reserve_mode["on"]:
            # The ranker only lets tier-4 stories through when two of them
            # exist, and never plain tier-1 stories, so the gate used to see
            # just the same 4 weak picks. While the gate collects, every
            # event-valid story is eligible; the real tier is restored and
            # used for ranking right after, and the AI editor judges each one.
            candidate["_editor_real_tier"] = real
            return 4
        return real

    intel._publication_tier = editor_tier

    previous_collect = main.collect_candidates

    def editor_collect(hash_history, title_history):
        target = int(getattr(intel, "MAX_NEWS_PER_RUN", 4) or 4)
        original_cap = getattr(intel, "MAX_NEWS_PER_RUN", 4)
        intel.MAX_NEWS_PER_RUN = max(target, POOL_SIZE)  # ask the ranker for reserves
        reserve_mode["on"] = True
        try:
            pool = list(previous_collect(hash_history, title_history) or [])
        finally:
            intel.MAX_NEWS_PER_RUN = original_cap
            reserve_mode["on"] = False
        for candidate in pool:
            if "_editor_real_tier" in candidate:
                candidate["publication_tier"] = candidate.pop("_editor_real_tier")
        # Real editorial priority: tier first, then the intelligence score.
        pool.sort(key=lambda c: (int(c.get("publication_tier", 1) or 1),
                                 int(c.get("intelligence_score", 0) or 0)), reverse=True)
        kept = gate_pool(main, pool, target)
        print(f"V13 EDITOR GATE: pool {len(pool)} -> judged {len(pool) - len(UNUSED_RESERVES)} "
              f"-> {len(kept)} approved (target {target})", flush=True)
        return kept

    main.collect_candidates = editor_collect
    import atexit
    atexit.register(record_blocks)  # runs after the engine has written v13_health.json
    _patch_topic_label()
    print(f"V13 EDITOR GATE ACTIVE: deterministic veto + AI editor (score>={MIN_AI_SCORE}, happened, not local), "
          f"fail-closed, backfill pool {POOL_SIZE}", flush=True)
