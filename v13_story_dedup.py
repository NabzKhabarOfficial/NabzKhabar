"""V13 content-level duplicate guard with defensive state parsing."""
import json
import os
import re
import tempfile
import time

STORE_KEY = "_published_stories"
BLOCK_KEY = "_editorial_blocks"
WINDOW_SECONDS = 36 * 3600
BLOCK_SECONDS = 6 * 3600
MAX_STORIES = 150
CHANNEL_MARK = "t.me/NabzKhabarOfficial"
HEALTH_FILE = "ai_model_health.json"

STOP = set("و در به از که این آن با برای را تا بر هم یا اما نیز شد شده شدن است بود بوده کرد کرده کند کنند کردند کردن می نمی ها های ای یک دو سه پس پیش طی درباره اعلام گفت گفته افزود داد دارد داشت داشته اند خود او وی آنها ما همچنین چنین چون اگر هر همه دیگر بیش بیشتر کم روز امروز دیروز سال ماه هفته اکنون حال جمله بین میان سوی سمت توسط علیه ضد مورد براساس اساس گزارش خبر حدود شود شوند گرفت گرفته گیرد قرار دهد دادند باید نیست هست ادامه جدید کنون".split())
_LETTERS = re.compile(r"[a-z0-9\u0621-\u063A\u0641-\u064A\u067E\u0686\u0698\u06A9\u06AF\u06CC]+")
_SUFFIXES = ("هایی", "های", "ها", "ات", "ان", "ی", "ه")
_FA_DIG = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _norm(text):
    text = str(text or "").lower().replace("\u200c", " ")
    for a, b in (("ي", "ی"), ("ك", "ک"), ("ة", "ه"), ("أ", "ا"), ("إ", "ا"), ("ؤ", "و"), ("ۀ", "ه"), ("آ", "ا")):
        text = text.replace(a, b)
    return re.sub("[\u064B-\u065F\u0670]", "", text)


def _key(word):
    for suffix in _SUFFIXES:
        if len(word) - len(suffix) >= 3 and word.endswith(suffix):
            word = word[:-len(suffix)]
            break
    return word[0] + re.sub("[اوییئء]", "", word[1:])


def story_text(caption):
    kept = []
    for line in str(caption or "").splitlines():
        s = line.strip()
        if not s or s.startswith(("#", "━", "🔗", "💓")) or "t.me/" in s:
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
    shortest = min(len(a), len(b))
    if shortest <= 0:
        return False
    ratio = shared / shortest
    return (shared >= 6 and ratio >= 0.40) or (shared >= 4 and ratio >= 0.60)


def _load_state_strict():
    if not os.path.exists(HEALTH_FILE):
        return {}, False
    try:
        with open(HEALTH_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError("health state is not an object")
        return data, False
    except Exception as exc:
        print(f"V13 STORY DEDUP: state unreadable, blocking publication ({type(exc).__name__})", flush=True)
        return {"_state_corrupt": True}, True


def _save_state_atomic(data):
    directory = os.path.dirname(os.path.abspath(HEALTH_FILE)) or "."
    fd, path = tempfile.mkstemp(prefix=".ai_model_health.", suffix=".tmp", dir=directory, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(path, HEALTH_FILE)
    finally:
        if os.path.exists(path):
            os.unlink(path)


def _health():
    return _load_state_strict()


def _recent(health):
    now = time.time()
    items = health.get(STORE_KEY)
    if not isinstance(items, list):
        return []
    result = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            timestamp = float(item.get("t", 0) or 0)
        except (TypeError, ValueError):
            continue
        if now - timestamp <= WINDOW_SECONDS:
            result.append(item)
    return result


def find_duplicate(caption):
    story = story_text(caption)
    fp = fingerprint(story)
    if len(fp) < 4:
        return None
    health, corrupt = _health()
    if corrupt:
        return {"title": "duplicate state unavailable"}
    recent = _recent(health)
    for item in reversed(recent):
        keys = set(item.get("k") or [])
        if is_same_story(fp, keys):
            return item
    return None


def remember(caption):
    story = story_text(caption)
    fp = fingerprint(story)
    if len(fp) < 4:
        return
    health, corrupt = _health()
    if corrupt:
        return
    items = _recent(health)
    entry = {"t": time.time(), "k": sorted(fp), "title": story[:120]}
    health[STORE_KEY] = (items + [entry])[-MAX_STORIES:]
    _save_state_atomic(health)


def _block_candidate(candidate):
    if not isinstance(candidate, dict):
        return
    candidate["publication_status"] = "skipped_duplicate"
    try:
        health, corrupt = _health()
        if corrupt:
            return
        blocks = health.get(BLOCK_KEY)
        if not isinstance(blocks, dict):
            blocks = {}
        title = str(candidate.get("title", "") or "").strip().lower()
        if title:
            blocks[title] = {"until": time.time() + BLOCK_SECONDS, "reason": "content_duplicate"}
        health[BLOCK_KEY] = blocks
        _save_state_atomic(health)
    except Exception as exc:
        print(f"V13 STORY DEDUP: block warning ({type(exc).__name__})", flush=True)


def install(core, current):
    def guard(name, text_index):
        inner = getattr(core, name, None)
        if not callable(inner):
            return
        def guarded(*args, **kwargs):
            text = args[text_index] if len(args) > text_index else kwargs.get("caption", kwargs.get("text", ""))
            text = str(text or "")
            blocked = current.get("blocked")
            if blocked:
                cand = current.get("candidate")
                if isinstance(cand, dict):
                    cand["publication_status"] = "quality_blocked"
                return False
            if CHANNEL_MARK in text:
                match = find_duplicate(text)
                if match:
                    print("V13 STORY DEDUP: publication refused because duplicate state matched or was unavailable", flush=True)
                    _block_candidate(current.get("candidate"))
                    return False
            result = inner(*args, **kwargs)
            if CHANNEL_MARK in text and result is not False:
                remember(text)
            return result
        setattr(core, name, guarded)
    guard("send_photo", 1)
    guard("send_video", 1)
    guard("send_message", 0)
    print("V13 STORY DEDUP ACTIVE: defensive content-level duplicate guard (36h window).", flush=True)
