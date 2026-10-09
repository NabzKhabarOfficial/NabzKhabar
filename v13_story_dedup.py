"""NABZ V13 — content-level duplicate guard.

Headline-based history misses rewrites of the same story ("فلی دوبی پس از
حمله..." vs "تحقیقات برای تعیین انگیزه حمله به فلای دوبای..."). This layer
fingerprints the *final published text* (title + body) and blocks a new post
whose content overlaps strongly with anything published in the last 36 hours.

* Spelling-variant tolerant: words are reduced to a light stem and a
  consonant skeleton, so «فلای دوبای» and «فلی دوبی» match.
* Checked right before sending, on the exact text that would go out.
* A blocked story is labelled skipped_duplicate (not a failed run) and kept
  out of selection for 6 hours, so it does not waste later runs.
* State lives in ai_model_health.json, which the workflow already persists.
"""

import re
import time

STORE_KEY = "_published_stories"
BLOCK_KEY = "_editorial_blocks"
WINDOW_SECONDS = 36 * 3600
BLOCK_SECONDS = 6 * 3600
MAX_STORIES = 150
CHANNEL_MARK = "t.me/NabzKhabarOfficial"

STOP = set("""
و در به از که این آن با برای را تا بر هم یا اما نیز شد شده شدن است بود بوده
کرد کرده کند کنند کردند کردن می نمی ها های ای یک دو سه پس پیش طی درباره
اعلام گفت گفته افزود داد دارد داشت داشته اند خود او وی آنها ما همچنین چنین
چون اگر هر همه دیگر بیش بیشتر کم روز امروز دیروز سال ماه هفته اکنون حال
جمله بین میان سوی سمت توسط علیه ضد مورد براساس اساس گزارش خبر حدود شود
شوند گرفت گرفته گیرد قرار دهد دادند باید نیست هست ادامه جدید کنون
""".split())

_LETTERS = re.compile(r"[a-z0-9\u0621-\u063A\u0641-\u064A\u067E\u0686\u0698\u06A9\u06AF\u06CC]+")
_SUFFIXES = ("هایی", "های", "ها", "ات", "ان", "ی", "ه")


def _norm(text):
    text = str(text or "").lower().replace("\u200c", " ")
    for a, b in (("ي", "ی"), ("ك", "ک"), ("ة", "ه"), ("أ", "ا"), ("إ", "ا"),
                 ("ؤ", "و"), ("ۀ", "ه"), ("آ", "ا")):
        text = text.replace(a, b)
    return re.sub("[\u064B-\u065F\u0670]", "", text)


def _key(word):
    for suffix in _SUFFIXES:
        if len(word) - len(suffix) >= 3 and word.endswith(suffix):
            word = word[:-len(suffix)]
            break
    # Consonant skeleton: tolerant to transliteration (فلای/فلی, دوبای/دوبی).
    return word[0] + re.sub("[اوییئء]", "", word[1:])


def story_text(caption):
    """Strip channel chrome (tags, meter, footer, link) and keep the story."""
    kept = []
    for line in str(caption or "").splitlines():
        s = line.strip()
        if not s or s.startswith(("#", "━", "🔗", "💓")) or "t.me/" in s:
            continue
        if len(s) < 30 and re.match(r"^(🔴|🟠|🌍|🇮🇷|💰|💻|⚽)", s):
            continue
        kept.append(s)
    return " ".join(kept)


def fingerprint(text):
    keys = set()
    for word in _LETTERS.findall(_norm(text)):
        if len(word) < 3 or word in STOP or word.isdigit():
            continue
        key = _key(word)
        if len(key) >= 2:
            keys.add(key)
    return keys


def is_same_story(a, b):
    if not a or not b:
        return False
    shared = len(a & b)
    ratio = shared / min(len(a), len(b))
    return (shared >= 6 and ratio >= 0.40) or (shared >= 4 and ratio >= 0.60)


def _health():
    import v13_ai_router
    return v13_ai_router, v13_ai_router._load_health()


def _recent(health):
    now = time.time()
    items = health.get(STORE_KEY)
    if not isinstance(items, list):
        return []
    return [x for x in items if isinstance(x, dict) and now - float(x.get("t", 0) or 0) <= WINDOW_SECONDS]


RARE_DF = 2          # a word seen in at most this many recent stories is "rare"
RARE_SHARED = 5      # follow-ups share several rare names (people, places, firms)
# Everyday news words never count as "rare", however few stories used them.
COMMON_WORDS = """
ترامپ دونالد ایران ایرانی آمریکا آمریکایی اسرائیل اسرائیلی صهیونیستی رژیم جنگ رئیس جمهور
هسته ای ادعا نظامی حمله هواپیما مسافران پرواز پروازها عربستان روسیه اوکراین چین غزه سپاه
ارتش دولت وزیر مجلس تهران کشته زخمی نیروهای قیمت نفت تحریم اروپا امارات عراق سوریه لبنان
منطقه کشور مردم مقامات منابع خبری بین المللی امنیتی سیاسی اقتصادی رسانه انفجار سقوط
""".split()
COMMON = {_key(w) for w in (_norm(x) for x in COMMON_WORDS) if len(w) >= 3}


def is_follow_up(a, b, df):
    """Same incident retold from a new angle ("captain says...", "probe...")."""
    shared = a & b
    if len(shared) < 6:
        return False
    rare = [k for k in shared if k not in COMMON and df.get(k, 0) <= RARE_DF]
    return len(rare) >= RARE_SHARED


def find_duplicate(caption):
    fp = fingerprint(story_text(caption))
    if len(fp) < 4:
        return None
    try:
        _, health = _health()
    except Exception:
        return None
    recent = _recent(health)
    df = {}
    for item in recent:
        for k in set(item.get("k") or []):
            df[k] = df.get(k, 0) + 1
    for item in reversed(recent):
        keys = set(item.get("k") or [])
        if is_same_story(fp, keys) or is_follow_up(fp, keys, df):
            return item
    return None


def remember(caption):
    fp = fingerprint(story_text(caption))
    if len(fp) < 4:
        return
    try:
        router, health = _health()
        items = _recent(health)
        title = story_text(caption)[:120]
        items.append({"t": time.time(), "k": sorted(fp), "title": title})
        health[STORE_KEY] = items[-MAX_STORIES:]
        router._save_health(health)
    except Exception as exc:
        print(f"V13 STORY DEDUP: remember warning ({type(exc).__name__})", flush=True)


def _block_candidate(candidate):
    if not isinstance(candidate, dict):
        return
    candidate["publication_status"] = "skipped_duplicate"
    try:
        import v13_intelligence
        title = str(v13_intelligence._norm(candidate.get("title", "") or "")).strip().lower()
        if not title:
            return
        router, health = _health()
        blocks = health.get(BLOCK_KEY)
        if not isinstance(blocks, dict):
            blocks = {}
        blocks[title] = {"until": time.time() + BLOCK_SECONDS, "reason": "content_duplicate"}
        health[BLOCK_KEY] = blocks
        router._save_health(health)
    except Exception as exc:
        print(f"V13 STORY DEDUP: block warning ({type(exc).__name__})", flush=True)


def install(core, current):
    """Wrap the outermost senders. `current` holds the story being processed."""

    def guard(name, text_index):
        inner = getattr(core, name, None)
        if not callable(inner):
            return

        def guarded(*args, **kwargs):
            if len(args) > text_index:
                text = args[text_index]
            else:
                text = kwargs.get("caption", kwargs.get("text", ""))
            text = str(text or "")
            blocked = current.get("blocked")
            if blocked:
                cand = current.get("candidate")
                if isinstance(cand, dict):
                    cand["publication_status"] = "quality_blocked"
                print(f"V13 POST QUALITY: publication refused ({blocked}).", flush=True)
                return False
            if CHANNEL_MARK in text:
                match = find_duplicate(text)
                if match:
                    print("V13 STORY DEDUP: same story already published -> "
                          f"{story_text(text)[:90]} | earlier: {str(match.get('title', ''))[:90]}",
                          flush=True)
                    _block_candidate(current.get("candidate"))
                    return False
            result = inner(*args, **kwargs)
            # True = published, None = may have been published: remember both.
            if CHANNEL_MARK in text and result is not False:
                remember(text)
            return result

        setattr(core, name, guarded)

    guard("send_photo", 1)
    guard("send_video", 1)
    guard("send_message", 0)
    print("V13 STORY DEDUP ACTIVE: content-level duplicate guard (36h window).", flush=True)

    # Text polish (Oct 2026): labels, filler details, AI wording, 12h incident dedup.
    try:
        import v13_text_polish
        v13_text_polish.install()
    except Exception as exc:
        print(f"V13 TEXT POLISH: not installed ({type(exc).__name__}: {exc})", flush=True)

    # Same incident, different wording (Oct 9): same event + same city/region within 8h.
    try:
        import v13_incident_dedup
        v13_incident_dedup.install()
    except Exception as exc:
        print(f"V13 INCIDENT DEDUP: not installed ({type(exc).__name__}: {exc})", flush=True)

    # Root fix (Oct 9): an AI judge compares the final post with every headline of
    # the last 24h and blocks the same event in any wording. Runs last.
    try:
        import v13_event_judge
        v13_event_judge.install()
    except Exception as exc:
        print(f"V13 EVENT JUDGE: not installed ({type(exc).__name__}: {exc})", flush=True)

    # No important news lost (Oct 9): keyword rejections get a second opinion from
    # the same free AI editor. Installed here, before the final editor gate.
    try:
        import v13_importance_rescue
        v13_importance_rescue.install(core)
    except Exception as exc:
        print(f"V13 AI IMPORTANCE RESCUE: not installed ({type(exc).__name__}: {exc})", flush=True)
