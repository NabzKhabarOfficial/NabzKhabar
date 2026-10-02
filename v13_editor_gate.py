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
2. AI editor-in-chief (only the few stories selected for this run): scores
   0-10 against a strict "front page of BBC/Reuters, or nationwide Iran news"
   rubric. Published only if score >= 7, the event happened, scope not local.
3. If every AI provider fails: fail closed; only clearly hard, already
   happened, non-local events pass.
Decisions are cached for 24h so a rejected story never costs AI again.
"""

import json
import os
import re
import time

MIN_AI_SCORE = 7
CACHE_KEY = "_editor_gate_cache"
CACHE_TTL = 24 * 3600
CACHE_MAX = 600
AI_TIMEOUT = 15
AI_BUDGET_PER_STORY = 40

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
STRATEGIC = re.compile(
    r"(?:سپاه|ارتش|نیروی دریایی|ناتو|آمریکا|اسرائیل|روسیه|چین|کره شمالی|تنگه هرمز|خلیج فارس|"
    r"شورای امنیت|سازمان ملل|nato|pentagon|navy)",
    re.I,
)


def deterministic_veto(candidate):
    """Reason string when the story can never be first-tier news, else ""."""
    title = _norm(candidate.get("title", ""))
    if not title:
        return ""
    hard = bool(HARD_HAPPENED.search(title))
    if NON_EVENT.search(title) and not hard and not STRATEGIC.search(title):
        return "editor-non-event"
    if LOCAL_LEVEL.search(title) and not hard:
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

Give a LOW score (0-4) to: local, provincial, county or city news; training courses, drills, exercises, preparedness, plans, intentions, "will be held";
conferences, meetings, ceremonies, anniversaries, inaugurations, visits, awards; warnings or forecasts with no event yet; statements, opinions, slogans, sermons,
routine officials' remarks; PR of organisations (Red Crescent, municipalities, ministries' routine programmes); culture/art events; minor crimes; celebrity, lifestyle, product reviews.

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


def ai_accepts(verdict):
    return (int(verdict.get("score", 0)) >= MIN_AI_SCORE and verdict.get("happened")
            and verdict.get("scope") != "local")


def fallback_accepts(candidate):
    """No AI available: only clearly hard, already-happened, non-local events."""
    title = _norm(candidate.get("title", ""))
    return bool(HARD_HAPPENED.search(title)) and not LOCAL_LEVEL.search(title) and not NON_EVENT.search(title)


# --------------------------------------------------------------------------
# Cache (persisted inside ai_model_health.json, which the workflow commits)
# --------------------------------------------------------------------------
def _health_io():
    import v13_ai_router
    return v13_ai_router._load_health, v13_ai_router._save_health


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


def record_blocks(health_file="v13_health.json"):
    """Write this run's editor-gate rejections into the health file as editorial_blocked attempts."""
    if not REJECTED_THIS_RUN:
        return 0
    import json
    try:
        with open(health_file, "r", encoding="utf-8") as f:
            health = json.load(f)
    except Exception as exc:
        print(f"V13 EDITOR GATE: telemetry read warning {type(exc).__name__}: {exc}", flush=True)
        return 0
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
        with open(health_file, "w", encoding="utf-8") as f:
            json.dump(health, f, ensure_ascii=False, indent=2)
        print(f"V13 EDITOR GATE: {added} rejected selection(s) recorded as editorial_blocked", flush=True)
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
    key = _norm(candidate.get("title", "")).lower()
    cached = _cache_get(key)
    if cached:
        return bool(cached.get("ok")), "cached:" + str(cached.get("reason", ""))
    verdict, provider = ai_judge(main, candidate)
    if verdict:
        ok = bool(ai_accepts(verdict))
        reason = f"ai {provider} score={verdict.get('score')} happened={verdict.get('happened')} scope={verdict.get('scope')}: {verdict.get('reason', '')}"
        candidate["editor_topic"] = str(verdict.get("topic", "") or "")
        _cache_put(key, {"ok": ok, "reason": reason, "topic": candidate["editor_topic"]})
        return ok, reason
    ok = fallback_accepts(candidate)
    return ok, "no-ai-fallback-" + ("hard-event" if ok else "fail-closed")


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
            return ok, score, reason
        veto = deterministic_veto(candidate)
        if veto:
            return False, 0, veto
        return ok, score, reason

    intel.is_publishable = editor_publishable

    previous_collect = main.collect_candidates

    def editor_collect(hash_history, title_history):
        selected = previous_collect(hash_history, title_history)
        kept = []
        for candidate in selected:
            ok, reason = judge(main, candidate)
            print(f"V13 EDITOR GATE: {'PUBLISH' if ok else 'REJECT'} [{reason}] {candidate.get('title', '')}", flush=True)
            if ok:
                kept.append(candidate)
            else:
                _audit(main, candidate, int(candidate.get("intelligence_score", 0) or 0), reason[:200])
                REJECTED_THIS_RUN[str(candidate.get("title", "")).strip()] = (candidate, reason)
        print(f"V13 EDITOR GATE: {len(selected)} selected -> {len(kept)} approved", flush=True)
        return kept

    main.collect_candidates = editor_collect
    import atexit
    atexit.register(record_blocks)  # runs after the engine has written v13_health.json
    _patch_topic_label()
    print(f"V13 EDITOR GATE ACTIVE: deterministic veto + AI editor (score>={MIN_AI_SCORE}, happened, not local), fail-closed", flush=True)
