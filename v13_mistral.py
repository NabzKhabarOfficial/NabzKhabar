"""NABZ KHABAR: Mistral's free tier as one more AI provider (Oct 15 2026).

Owner's own free Mistral account (La Plateforme free plan, no card): a different provider, not an
extra key for an existing one. Its free plan is large (about a billion tokens a month, ~1 request a
second), so it can carry the night when Groq's 200k tokens a day and Gemini's daily requests are
used up. It is used only AFTER Groq and Gemini, before OpenRouter (50 free requests a day):

1. Translation / rewrite (v13_ai_router.gemini_request): when the router reaches OpenRouter,
   Mistral (open-mistral-nemo, ministral-8b-latest) is asked first with the
   same prompt, the same JSON check and the same strict content validation.
2. Final editor (v13_ai_extra.ask_pool): open-mistral-nemo is the last resort, after OpenRouter
   (approvals only, see below), with a 1.5s minimum gap and a single 2.5s retry on transient HTTP 429.
3. Event judge + AI sense check (v13_event_judge.ask): open-mistral-nemo first (see below).
4. The AI meter counts it (_ai_usage key "mistral:<model>"); it is not paced (no daily cap).

Oct 15 (night review): with open-mistral-nemo first, the editor gate scored clear first-tier news
0 and "local" («پنتاگون انتشار گزارش حمله به میناب را عقب انداخت»، «لبنان مجوز بانک صادرات ایران را
لغو کرد», the ex-Shin Bet chief suing Netanyahu), and those wrong verdicts were cached for 24 h.
mistral-small-latest (same free plan, far better at the rubric and at Persian) now goes first,
nemo is only a fallback, and the editor-cache rejections made by nemo are dropped once
(_purge_nemo_rejections) so those stories are judged again by a stronger model.
Same night, next run: mistral-small was in cooldown, so nemo judged again and again cached wrong
rejections for 24 h. nemo and ministral-8b now never act as editor (translation fallback only);
when no strong model answers, the gate fails closed WITHOUT caching, so the story is judged again
on the next run. The purge runs once more (v2).

Oct 15, 22:45 Tehran (root cause of the silent evening, from _ai_usage / _ai_pace): from ~21:00 every
Groq, Gemini and OpenRouter model was over its daily share (Groq gpt-oss 103/90 and 100/90 calls,
its real 200k tokens/day also full; Gemini flash-lite 208/360 and 116/210 at noon Pacific; OpenRouter
36/42), Gemini 3.6/3.8 flash answered 503 (high demand), mistral-small-latest answered 429 to all 61
calls, qwen3-32b does not exist on Groq. Only open-mistral-nemo worked (202/202), with ~1B free tokens a
month. The biggest token eaters on Groq/Gemini were the same-event judge (every post + 45 headlines,
~3k tokens a call) and the AI sense check, which ran on the scarce models first. Now:
* same-event judge + sense check ask open-mistral-nemo FIRST. A sense-check flag still needs a second
  model to agree. A nemo "not a repeat" for a post that shares words with a published headline is
  checked again by the strong pool (Groq/Gemini), so no duplicate slips through on nemo's word alone;
* the strong daily quotas are kept for the translation and the editor;
* editor: nemo is the very last resort, after OpenRouter. Its "publish" verdicts count; its "reject"
  verdicts are never cached and fall to the deterministic rule (hard events and war-zone reports pass,
  the rest waits for a strong model on a later run), because its rejections were wrong (scope "local").
* mistral-small-latest is no longer asked at all (always 429 on this plan).

Oct 16, 02:40 Tehran (review of the published evening posts): «ترمپ با معامله سوخت با مسکو، جنگ روسیه را
با پول تأمین می کند» went out with «نوبل پزیش اوکسانا ماتویچوک» (Nobel laureate, transliterated) and «پول گشایی»:
a weak nemo translation (the strong pool was held all evening), and the nemo-first sense check called it "ok".
The headline also stated one activist's accusation as fact. Now:
* every Mistral translation gets extra Persian rules (attribution in the headline for a claim or opinion,
  common Persian name forms, translate words instead of transliterating them);
* a post translated by nemo/ministral is sense-checked by the strong pool FIRST (only these posts, a few a
  day); nemo is asked only when no strong model answers;
* the sense check counts bad machine translation as "garbled" (transliterated English, a misspelled
  well-known name);
* deterministic: «ترمپ» becomes «ترامپ» in every AI output, and «نوبل پزیش/پرایز»-type transliterations
  fail the router's content validation (the next model translates the story).

Oct 16, 15:20 Tehran (day review, from _ai_extra_log / _ai_pace / the published feed):
* 11 of 13 selected stories at 15:12 were dropped "no-ai-fallback-fail-closed": the pacer held every Groq
  and Gemini model, OpenRouter then stalled ~80 s ("Response ended prematurely") and used the whole
  batch budget, so nemo, placed AFTER OpenRouter, was never asked. nemo now comes BEFORE OpenRouter in
  the editor pool (its approvals still need a concrete event, see below; its rejections are still
  never trusted).
* groq qwen/qwen3-32b does not exist (119 HTTP 404 today): removed from every Groq pool.
* nemo approved commentary («علی واعظ ...: توافق کمتر در برابر کمتر تنها راه خروج است»، rhetoric of
  commanders). A nemo approval now counts only for a hard / war-zone / strong-event title; otherwise
  the deterministic rule decides at once (no second AI call, nothing cached).
* Old events went out as news: «آمریکا برای نخستین بار بمب مادر تمام بمب ها ...» (April 2017) and
  «مصدق قطع روابط ایران و انگلیس را اعلام کرد» (1331). A post whose title or lead dates the event two or
  more years back, with no current-year date anywhere, is refused (final guard, logged in guard_log).
* «دونالد ترامپ رئیس جمهور سابق آمریکا» (a weak translation): fixed to «رئیس جمهور آمریکا» in every AI output.

Oct 16, 19:50 Tehran (evening review): at 19:43 all 19 selected stories were dropped
"no-ai-fallback-fail-closed" again. Groq was paced, Gemini answered 503/429, and nemo's 8-story batch
answer could not be parsed ("no usable verdict"); after a failed batch the launcher allows only 2 single
editor calls per run (to protect the scarce quotas), so the rest failed closed. nemo's quota is not
scarce: when the pool gives no verdict, nemo now judges that one story on its own (same rubric, same
trust rules: approvals only for concrete events). The old-event guard also refused a fresh statement
(«آخوندی: دو بار ترور شدم، بار اول در سال ۱۳۶۰»): a quoted speaker's title («X: ...») or a "first/second
time" story is a current event and is no longer refused.

No MISTRAL_API_KEY in the environment = nothing changes. Any error = the bot runs as before.
"""

import os
import re
import sys
import time

MISTRAL_BASE = "https://api.mistral.ai/v1"
TRANSLATE_MODELS = ("open-mistral-nemo", "ministral-8b-latest")  # mistral-small: 61/61 HTTP 429 on this free plan
EDITOR_MODELS = ("open-mistral-nemo",)  # last resort only: its approvals count, its rejections do not (see notes)
NEMO = "open-mistral-nemo"
JUDGE_HEAD = "You are the duplicate checker"
SENSE_HEAD = "You check a Persian Telegram news post"
MIN_INTERVAL_SEC = 1.5   # La Plateforme free tier is ~1 req/s across the account
RETRY_429_SLEEP_SEC = 2.5
PURGE_MARK = "_mistral_nemo_purge_v2"
MISTRAL_RULES = """
قواعد اضافه (ترجمه دقیق و طبیعی):
- واژه‌های انگلیسی را ترجمه کن، آوانویسی نکن (Nobel laureate = «برنده جایزه نوبل»، نه «نوبل پزیش»).
- نام‌های مشهور را با شکل رایج فارسی بنویس: ترامپ، پوتین، زلنسکی، نتانیاهو، پزشکیان، عراقچی.
- اگر خبر ادعا، اتهام یا نظر یک شخص است، تیتر باید گوینده را بگوید (مثلاً «ماتویچوک: ...» یا «... به گفته ...»)
  و ادعا را به‌صورت واقعیت قطعی ننویسد.
- اگر معنی جمله‌ای را مطمئن نیستی، آن جمله را حذف کن.
"""
WEAK_TITLES = []  # titles translated by nemo/ministral in this run (sense-checked by the strong pool first)
NAME_FIXES = ((re.compile(r"(?<![\u0600-\u06FF])ترمپ(?![\u0600-\u06FF])"), "ترامپ"),
              (re.compile(r"(ترامپ[،,]?\s*)رئیس[\s\u200c]*جمهور\s+(?:سابق|پیشین)(?:\s+آمریکا)?"), r"\1رئیس جمهور آمریکا"))
DEAD_MODELS = ("qwen/qwen3-32b",)  # Groq: model_not_found (HTTP 404) on every call
_KEY = {"v": ""}
_REPEAT_WORDS = re.compile(r"بار\s+(?:اول|دوم|نخست|دیگر)|دو\s+بار|دوباره|مجددا|مجدداً|باز\s+هم")
NEMO_DETERMINISTIC = set()  # editor cache keys whose nemo verdict is not trusted this run
_MONTHS = ("فروردین|اردیبهشت|خرداد|تیر|مرداد|شهریور|مهر|آبان|آذر|دی|بهمن|اسفند|ژانویه|فوریه|مارس|آوریل|"
           "مه|می|ژوئن|ژوئیه|جولای|اوت|آگوست|سپتامبر|اکتبر|نوامبر|دسامبر")
_YEAR_CTX = re.compile(r"(?<![\u0600-\u06FF])(?:سال|(?:" + _MONTHS + r")(?:\s*ماه)?)\s+(1[3][0-9]{2}|19[0-9]{2}|20[0-9]{2})(?![0-9])")
_NOW_WORDS = re.compile(r"امروز|امشب|دیروز|بامداد|روز\s+(?:شنبه|یکشنبه|دوشنبه|سه\s*شنبه|چهارشنبه|پنجشنبه|جمعه)|"
                        r"این\s+هفته|ساعاتی\s+پیش|لحظاتی\s+پیش|اخیرا|اخیراً|هم\s*اکنون|در\s+حال\s+حاضر")
TRANSLIT_BAD = re.compile(r"نوبل[\s\u200c]+پ(?:رای|ری|زی)[زش]|(?<![\u0600-\u06FF])(?:پرایز|لوریت|لاریت)(?![\u0600-\u06FF])")
SENSE_EXTRA = ('\n- "garbled" also covers bad machine translation: English words written in Persian letters instead '
               'of translated (e.g. «نوبل پزیش» for "Nobel Prize"), or a well-known name misspelled (e.g. «ترمپ»).')
_INSTALLED = {"done": False}
_LAST_CALL = {"at": 0.0}


def _key():
    return os.getenv("MISTRAL_API_KEY", "").strip()


def _pace_rps():
    wait = MIN_INTERVAL_SEC - (time.monotonic() - _LAST_CALL["at"])
    if wait > 0:
        time.sleep(wait)
    _LAST_CALL["at"] = time.monotonic()


def _install_rps_guard():
    import requests.sessions as rs
    if getattr(rs.Session.request, "_v13_mistral_rps", False):
        return
    original = rs.Session.request

    def request(self, method, url, *args, **kwargs):
        if "api.mistral.ai" in str(url):
            _pace_rps()
            resp = original(self, method, url, *args, **kwargs)
            if getattr(resp, "status_code", 0) == 429:
                # Transient per-second rate limit on La Plateforme: wait once and retry
                time.sleep(RETRY_429_SLEEP_SEC)
                _LAST_CALL["at"] = time.monotonic()
                resp = original(self, method, url, *args, **kwargs)
            return resp
        return original(self, method, url, *args, **kwargs)

    request._v13_mistral_rps = True
    rs.Session.request = request


def _install_router(key):
    import v13_ai_router as r
    previous = r._fallback_provider_request
    if getattr(previous, "_v13_mistral", False):
        return
    orig_oa = r._openai_compatible_json
    if not getattr(orig_oa, "_v13_mistral_json", False):
        def oa_json(main, provider, base_url, api_key, model, prompt, max_output_tokens=500):
            # Mistral supports response_format={"type": "json_object"} like OpenRouter
            if str(provider).lower() == "mistral":
                return orig_oa(main, "openrouter", base_url, api_key, model, prompt, max_output_tokens=max_output_tokens)
            return orig_oa(main, provider, base_url, api_key, model, prompt, max_output_tokens=max_output_tokens)

        oa_json._v13_mistral_json = True
        r._openai_compatible_json = oa_json

    def fallback(main, provider, models, base_url, api_key, prompt, title, source, foreign, deadline=None):
        if str(provider).lower() == "openrouter":
            got = previous(main, "Mistral", TRANSLATE_MODELS, MISTRAL_BASE, key, str(prompt) + MISTRAL_RULES,
                           title, source, foreign, deadline)
            if got:
                WEAK_TITLES.append(str(got.get("title", "")))
                del WEAK_TITLES[:-30]
                return got
        return previous(main, provider, models, base_url, api_key, prompt, title, source, foreign, deadline)

    fallback._v13_mistral = True
    r._fallback_provider_request = fallback

    orig_validate = r._validate
    if not getattr(orig_validate, "_v13_names", False):
        def validate(main, original_title, source, data, foreign):
            if isinstance(data, dict):
                data = dict(data)
                for k in ("title", "summary"):
                    v = str(data.get(k, "") or "")
                    for rx, good in NAME_FIXES:
                        v = rx.sub(good, v)
                    data[k] = v
            return orig_validate(main, original_title, source, data, foreign)

        validate._v13_names = True
        r._validate = validate
    if TRANSLIT_BAD not in r.TRANSLATION_QUALITY_BAD_PATTERNS:
        r.TRANSLATION_QUALITY_BAD_PATTERNS = tuple(r.TRANSLATION_QUALITY_BAD_PATTERNS) + (TRANSLIT_BAD,)


def _install_editor(key):
    extra = sys.modules.get("__main__")
    attempts = getattr(extra, "_attempts", None)
    oa_raw = getattr(extra, "_oa_raw", None)
    if not callable(attempts) or not callable(oa_raw) or not hasattr(extra, "ask_pool"):
        return False
    hosts = getattr(extra, "AI_HOSTS", None)
    if isinstance(hosts, dict):
        hosts["api.mistral.ai"] = "mistral"
    if getattr(attempts, "_v13_mistral", False):
        return True

    def with_mistral(main, session, prompt, max_tokens, timeout):
        out = [a for a in attempts(main, session, prompt, max_tokens, timeout)
               if not any(d in str(a[0]) for d in DEAD_MODELS)]
        # before OpenRouter (slow, 50 free calls a day): nemo approvals only, see _install_nemo_editor_rules
        pos = next((i for i, a in enumerate(out) if str(a[0]).startswith("openrouter/")), len(out))
        for m in reversed(EDITOR_MODELS):
            item = ("mistral/" + m, "mistral:" + m, lambda m=m: oa_raw(
                session, MISTRAL_BASE + "/chat/completions", key, m, prompt, max_tokens,
                timeout=timeout))
            out.insert(pos, item)
        return out

    with_mistral._v13_mistral = True
    extra._attempts = with_mistral
    return True


def _mistral_ask(ej, key, prompt, model):
    tag = f"mistral/{model}"
    try:
        r = ej._post(MISTRAL_BASE + "/chat/completions",
                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                     json={"model": model, "temperature": 0, "max_tokens": 350,
                           "response_format": {"type": "json_object"},
                           "messages": [{"role": "user", "content": prompt}]})
        if r.ok:
            data = ej._parse(r.json()["choices"][0]["message"]["content"])
            if isinstance(data, dict) and data.get("verdict"):
                return dict(data, model=tag)
        print(f"V13 EVENT JUDGE: {tag} HTTP {r.status_code}.", flush=True)
    except Exception as exc:
        print(f"V13 EVENT JUDGE: {tag} error ({type(exc).__name__}).", flush=True)
    return None


def _related_to_published(ej, prompt):
    """True when the NEW POST of a same-event prompt shares words with any listed headline."""
    try:
        head = prompt.split("NEW POST (about to be published):", 1)[1].split("ALREADY PUBLISHED", 1)[0].strip()
        listing = prompt.split("ALREADY PUBLISHED in the last 24 hours:", 1)[1].split("Does the NEW POST", 1)[0]
        for line in listing.splitlines():
            title = re.sub(r"^\s*\d+\.\s*", "", line).strip()
            if title and ej.related(head, title):
                return True
    except Exception:
        return True  # unsure: let the strong pool look
    return False


def _weak_translation(ej, prompt):
    """True when the sense-check HEADLINE is a title nemo/ministral translated in this run."""
    if not WEAK_TITLES:
        return False
    try:
        head = prompt.split("HEADLINE:", 1)[1].split("TEXT:", 1)[0].strip()
    except Exception:
        return False
    for t in WEAK_TITLES:
        if t and (t[:40] in head or head[:40] in t or ej.related(head, t)):
            return True
    return False


def _install_sense_rules():
    import v13_final_guard as fg
    p = fg.COHERENCE_PROMPT
    if SENSE_EXTRA not in p and '\n- "ok":' in p:
        fg.COHERENCE_PROMPT = p.replace('\n- "ok":', SENSE_EXTRA + '\n- "ok":', 1)


def _digits(text):
    return str(text or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))


def old_event(title, sentences):
    """The old year when the title or lead dates the event 2+ years back and no current-year date
    appears anywhere in the post, else ""."""
    now_g = int(time.strftime("%Y", time.gmtime()))
    now_j = now_g - 621
    title = _digits(title)
    sents = [_digits(x) for x in sentences or []]
    whole = " ".join([title] + sents)
    for y in re.findall(r"(?<![0-9])(1[3-4][0-9]{2}|20[0-9]{2})(?![0-9])", whole):
        y = int(y)
        if (y >= now_g - 1 and y <= now_g + 1) or (now_j - 1 <= y <= now_j + 1):
            return ""  # a current date is in the post: an old year is background, not the event
    if _NOW_WORDS.search(" ".join([title] + sents[:2])):
        return ""  # "today ... the case from 2022": a new development of an old story
    if re.match(r"^[^:：]{2,40}[:：]", title) or _REPEAT_WORDS.search(title):
        return ""  # «X: ...» is a statement made now; "the second time" is a new event
    for text in [title] + sents[:1]:
        for m in _YEAR_CTX.finditer(text):
            y = int(m.group(1))
            old = (y < now_j - 1) if y < 1500 else (y < now_g - 1)
            if old:
                return m.group(0)
    return ""


def _install_old_event_guard():
    import v13_relevance_gate as rg
    import v13_final_guard as fg
    previous = rg.caption_problem
    if getattr(previous, "_v13_old_event", False):
        return

    def caption_problem(title, sentences):
        reason = previous(title, sentences)
        if reason:
            return reason
        try:
            if fg._BOARD.search(str(title or "")):
                return ""
            found = old_event(title, sentences)
        except Exception:
            return ""
        if not found:
            return ""
        fg._log(title, [("old-event", found)])
        print(f"V13 FINAL GUARD: refused (old-event: {found}) -> {str(title or '')[:120]}", flush=True)
        return "final-guard:old-event"

    caption_problem._v13_old_event = True
    rg.caption_problem = caption_problem


def _drop_dead_models():
    import v13_ai_router as r
    mods = [r]
    for name in ("v13_editor_gate", "v13_event_judge"):
        try:
            mods.append(__import__(name))
        except Exception:
            pass
    for mod in mods:
        pool = getattr(mod, "GROQ_MODELS", None)
        if isinstance(pool, (tuple, list)):
            mod.GROQ_MODELS = tuple(m for m in pool if m not in DEAD_MODELS)


def _install_event_judge(key):
    try:
        import v13_event_judge as ej
    except Exception:
        return False
    orig_ask = getattr(ej, "ask", None)
    if not callable(orig_ask) or getattr(orig_ask, "_v13_mistral", False):
        return True

    def ask_with_mistral(prompt, skip=""):
        text = str(prompt or "")
        if text.startswith(SENSE_HEAD) and _weak_translation(ej, text):
            got = orig_ask(prompt, skip=skip)  # a weak translation: the strong pool reads it first
            if got:
                return got
            return _mistral_ask(ej, key, prompt, NEMO) if skip != f"mistral/{NEMO}" else None
        cheap_first = text.startswith(JUDGE_HEAD) or text.startswith(SENSE_HEAD)
        if cheap_first and skip != f"mistral/{NEMO}":
            got = _mistral_ask(ej, key, prompt, NEMO)
            if got:
                verdict = str(got.get("verdict", "")).strip().lower()
                if (text.startswith(JUDGE_HEAD) and verdict not in ("repeat", "duplicate", "same")
                        and _related_to_published(ej, text)):
                    strong = orig_ask(prompt, skip=skip)
                    if strong:
                        return strong
                return got
        got = orig_ask(prompt, skip=skip)
        if got:
            return got
        for model in TRANSLATE_MODELS:
            tag = f"mistral/{model}"
            if tag == skip or (cheap_first and model == NEMO):
                continue
            got = _mistral_ask(ej, key, prompt, model)
            if got:
                return got
        return None

    ask_with_mistral._v13_mistral = True
    ej.ask = ask_with_mistral
    return True


def _install_nemo_editor_rules():
    """nemo's editor approvals count; its rejections are not cached and fall to the deterministic rule."""
    import v13_editor_gate as g
    if getattr(g, "_v13_nemo_rules", False):
        return
    prev_put, prev_judge = g._cache_put, g.ai_judge

    def concrete(title):
        t = g._norm(title)
        return bool(g.war_zone(t) or g.HARD_HAPPENED.search(t) or g.STRONG_EVENT.search(t))

    def cache_put(key, entry):
        if isinstance(entry, dict) and NEMO in str(entry.get("reason", "")):
            title = str(key).split("|", 1)[-1]
            if not entry.get("ok") or not concrete(title):
                NEMO_DETERMINISTIC.add(key)  # this run: the deterministic rule decides, no second AI call
                return  # never cached: judged again on a later run, when a strong model may answer
        return prev_put(key, entry)

    def nemo_single(main, candidate):
        extra = sys.modules.get("__main__")
        oa_raw = getattr(extra, "_oa_raw", None)
        if not callable(oa_raw) or not _KEY["v"]:
            return None, ""
        session = getattr(main, "SESSION", None)
        if session is None:
            import requests
            session = requests.Session()
        title = g._norm(candidate.get("title", ""))
        body = g._norm(candidate.get("summary", "") or candidate.get("description", "")
                       or candidate.get("article_text", ""))[:900]
        try:
            verdict = g._parse(oa_raw(session, MISTRAL_BASE + "/chat/completions", _KEY["v"], NEMO,
                                      g.PROMPT % (title, body), 400, timeout=20))
        except Exception as exc:
            print(f"V13 MISTRAL: nemo single editor call failed ({type(exc).__name__})", flush=True)
            return None, ""
        return (verdict, "mistral/" + NEMO) if verdict else (None, "")

    def ai_judge(main, candidate):
        if g._cache_key(candidate) in NEMO_DETERMINISTIC:
            return None, ""
        verdict, provider = prev_judge(main, candidate)
        if not verdict:
            verdict, provider = nemo_single(main, candidate)  # pool empty or capped: nemo is not scarce
        if verdict and NEMO in str(provider) and (not g.ai_accepts(verdict, candidate)
                                                  or not concrete(candidate.get("title", ""))):
            print(f"V13 MISTRAL: nemo verdict not trusted -> deterministic rule: {str(candidate.get('title', ''))[:80]}",
                  flush=True)
            return None, ""
        return verdict, provider

    g._cache_put = cache_put
    g.ai_judge = ai_judge
    g._v13_nemo_rules = True


def _purge_nemo_rejections():
    """One time: editor-gate cache rejections made by open-mistral-nemo are dropped (see notes)."""
    try:
        import v13_ai_router as r
        health = r._load_health()
        if health.get(PURGE_MARK):
            return 0
        cache = health.get("_editor_gate_cache") or {}
        bad = [k for k, v in cache.items()
               if isinstance(v, dict) and not v.get("ok") and "open-mistral-nemo" in str(v.get("reason", ""))]
        for k in bad:
            cache.pop(k, None)
        health["_editor_gate_cache"] = cache
        health[PURGE_MARK] = int(time.time())
        r._save_health(health)
        print(f"V13 MISTRAL: {len(bad)} editor rejection(s) by open-mistral-nemo dropped from the cache "
              "(judged again by a stronger model)", flush=True)
        return len(bad)
    except Exception as exc:
        print(f"V13 MISTRAL: nemo cache purge skipped ({type(exc).__name__})", flush=True)
        return 0


def install():
    if _INSTALLED["done"]:
        return
    key = _key()
    if not key:
        print("V13 MISTRAL: no MISTRAL_API_KEY; not used", flush=True)
        return
    _KEY["v"] = key
    _install_rps_guard()
    _install_router(key)
    editor = _install_editor(key)
    ej = _install_event_judge(key)
    try:
        _install_nemo_editor_rules()
    except Exception as exc:
        print(f"V13 MISTRAL: nemo editor rules not installed ({type(exc).__name__}: {exc})", flush=True)
    for fix in (_drop_dead_models, _install_old_event_guard):
        try:
            fix()
        except Exception as exc:
            print(f"V13 MISTRAL: {fix.__name__} not installed ({type(exc).__name__}: {exc})", flush=True)
    try:
        _install_sense_rules()
    except Exception as exc:
        print(f"V13 MISTRAL: sense rules not installed ({type(exc).__name__}: {exc})", flush=True)
    _purge_nemo_rejections()
    _INSTALLED["done"] = True
    print("V13 MISTRAL ACTIVE: nemo first for duplicate/sense checks (strong first for nemo translations), editor nemo before OpenRouter; after Groq and Gemini for translation"
          + (" + editor" if editor else "") + (" + event_judge" if ej else "") + ")", flush=True)
