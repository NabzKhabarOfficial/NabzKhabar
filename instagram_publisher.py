import base64
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup
from PIL import Image
from instagrapi import Client

STATE_FILE = Path("instagram_state.json")
SESSION_FILE = Path(".instagram_session.json")
MEDIA_DIR = Path(".instagram_media")
MAX_POSTS_PER_DAY = int(os.getenv("IG_MAX_POSTS_PER_DAY", "2"))
MAX_STORY_AGE_MINUTES = int(os.getenv("IG_MAX_STORY_AGE_MINUTES", "180"))
REQUEST_TIMEOUT = 12
CHANNEL_URL = "https://t.me/NabzKhabarOfficial"

FEEDS = [
    ("ایران", "https://www.yjc.ir/fa/rss/allnews"),
    ("ایران", "https://www.irna.ir/rss"),
    ("جهان", "https://feeds.bbci.co.uk/persian/rss.xml"),
    ("جهان", "https://rss.dw.com/xml/rss-fa-all"),
    ("جهان", "https://www.radiofarda.com/api/z-pqpiev-qpp"),
    ("فناوری", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("فناوری", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ("ورزش", "https://feeds.bbci.co.uk/sport/rss.xml"),
]

PERSIAN_RE = re.compile(r"[\u0600-\u06ff]")
TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid"}
IMPORTANT = re.compile(
    r"جنگ|حمله|موشک|پهپاد|انفجار|زلزله|سیل|آتش.?بس|کشته|زخمی|هشدار|تحریم|مذاکره|ایران|آمریکا|روسیه|اوکراین|اسرائیل|غزه|چین|تایوان|هوش مصنوعی|اپن.?ای|گوگل|مایکروسافت|انویدیا|ترامپ|مقام|دولت|انتخابات",
    re.I,
)


def clean(text):
    text = BeautifulSoup(str(text or ""), "html.parser").get_text(" ")
    text = text.replace("\u200c", " ").replace("\u200f", " ").replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def persian_ratio(text):
    chars = re.findall(r"[A-Za-z\u0600-\u06ff]", str(text or ""))
    return 1.0 if not chars else sum("\u0600" <= c <= "\u06ff" for c in chars) / len(chars)


def canonical(url):
    try:
        p = urlparse(str(url).strip())
        pairs = [(k, v) for k, v in __import__("urllib.parse", fromlist=["parse_qsl"]).parse_qsl(p.query) if k.lower() not in TRACKING and not k.lower().startswith("utm_")]
        query = __import__("urllib.parse", fromlist=["urlencode"]).urlencode(sorted(pairs), doseq=True)
        path = p.path.rstrip("/") or "/"
        return p._replace(query=query, fragment="", path=path).geturl()
    except Exception:
        return str(url or "").strip()


def entry_time(entry):
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        value = getattr(entry, key, None)
        if value:
            return datetime(*value[:6], tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def image_url(entry, article_url):
    for key in ("media_content", "media_thumbnail"):
        items = getattr(entry, key, None) or []
        for item in items:
            value = item.get("url") if isinstance(item, dict) else None
            if value and value.startswith("http"):
                return value
    for link in getattr(entry, "links", []) or []:
        if isinstance(link, dict) and str(link.get("type", "")).startswith("image/") and link.get("href"):
            return urljoin(article_url, link["href"])
    try:
        r = requests.get(article_url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for prop in (("property", "og:image"), ("name", "twitter:image")):
            tag = soup.find("meta", attrs={prop[0]: prop[1]})
            if tag and tag.get("content"):
                return urljoin(article_url, tag["content"])
    except Exception as exc:
        print(f"IG IMAGE: article image lookup failed: {exc}")
    return ""


def score(item):
    title = item["title"]
    score_value = 0
    if persian_ratio(title) >= 0.60:
        score_value += 30
    score_value += min(30, len(IMPORTANT.findall(title)) * 8)
    if item["category"] in {"جهان", "ایران"}:
        score_value += 12
    age = max(0, (datetime.now(timezone.utc) - item["published_at"]).total_seconds() / 60)
    score_value += max(0, 25 - int(age / 10))
    return score_value


def load_state():
    if not STATE_FILE.exists():
        return {"posted": [], "daily": {}}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"posted": [], "daily": {}}
    except Exception:
        return {"posted": [], "daily": {}}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def today_key():
    return datetime.now(timezone.utc).date().isoformat()


def collect():
    items = []
    now = datetime.now(timezone.utc)
    for category, url in FEEDS:
        try:
            feed = feedparser.parse(url, request_headers={"User-Agent": "Mozilla/5.0 NabzKhabar Instagram"})
            for entry in feed.entries[:20]:
                title = clean(getattr(entry, "title", ""))
                link = canonical(getattr(entry, "link", ""))
                summary = clean(getattr(entry, "summary", "") or getattr(entry, "description", ""))
                if not title or not link:
                    continue
                published = entry_time(entry)
                age = (now - published).total_seconds() / 60
                if age < -10 or age > MAX_STORY_AGE_MINUTES:
                    continue
                if persian_ratio(title) < 0.45:
                    # Foreign-language sources are allowed only when the title can be
                    # translated by the optional free AI layer below.
                    pass
                key = hashlib.sha256((title.lower() + "|" + link).encode("utf-8")).hexdigest()
                items.append({"key": key, "title": title, "summary": summary, "link": link, "category": category, "published_at": published, "entry": entry})
        except Exception as exc:
            print(f"IG RSS: {url} -> {exc}")
    unique = {}
    for item in items:
        unique.setdefault(item["key"], item)
    result = list(unique.values())
    result.sort(key=score, reverse=True)
    return result


def free_ai_rewrite(title, summary):
    prompt = (
        "You are the Persian editor of a concise Iranian news Instagram page. "
        "Return JSON only with keys title and body. Translate foreign text to fluent Persian. "
        "Do not invent facts. Title <= 110 Persian characters; body 1-2 short sentences. "
        f"TITLE: {title}\nSUMMARY: {summary[:2500]}"
    )
    timeout = 12
    providers = []
    groq = os.getenv("GROQ_API_KEY", "").strip()
    if groq:
        providers.append(("Groq", "https://api.groq.com/openai/v1/chat/completions", groq, "openai/gpt-oss-20b"))
    gemini = os.getenv("AI_API_KEY", "").strip()
    if gemini:
        try:
            r = requests.post(
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent",
                params={"key": gemini},
                json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": 350}},
                timeout=timeout,
            )
            if r.ok:
                raw = r.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                data = json.loads(raw.strip().strip("`").replace("json\n", "", 1))
                if data.get("title") and data.get("body"):
                    return clean(data["title"]), clean(data["body"])
        except Exception as exc:
            print(f"IG AI: Gemini fallback: {exc}")
    for provider, endpoint, key, model in providers:
        try:
            r = requests.post(endpoint, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2, "response_format": {"type": "json_object"}, "max_tokens": 350}, timeout=timeout)
            if not r.ok:
                continue
            raw = r.json()["choices"][0]["message"]["content"]
            data = json.loads(raw)
            if data.get("title") and data.get("body"):
                return clean(data["title"]), clean(data["body"])
        except Exception as exc:
            print(f"IG AI: {provider} failed: {exc}")
    return "", ""


def make_caption(item):
    # Always try to turn raw feed text into short, natural Instagram copy.
    title, body = free_ai_rewrite(item["title"], item["summary"])
    if not title:
        title = clean(item["title"])
    if not body:
        body = clean(item["summary"])
    body = re.sub(r"\s+", " ", body).strip(" .")
    body = body[:500].rstrip(" .")
    if not title or not body:
        return ""
    return f"📰 {title}\n\n{body}\n\n🔗 {CHANNEL_URL}\n\n#نبض_خبر #NABZ"


def download_image(url, key):
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    raw = MEDIA_DIR / f"{key}.source"
    out = MEDIA_DIR / f"{key}.jpg"
    r = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    raw.write_bytes(r.content)
    with Image.open(raw) as image:
        image = image.convert("RGB")
        # Instagram-friendly 4:5 portrait canvas; keep the full source image
        # visible instead of allowing an aggressive crop/zoom.
        target_w, target_h = 1080, 1350
        src_w, src_h = image.size
        scale = min(target_w / src_w, target_h / src_h)
        new_w = max(1, int(src_w * scale))
        new_h = max(1, int(src_h * scale))

        # Soft enlarged background avoids ugly black bars while preserving
        # the complete original image in the foreground.
        bg_scale = max(target_w / src_w, target_h / src_h)
        bg_w = max(target_w, int(src_w * bg_scale))
        bg_h = max(target_h, int(src_h * bg_scale))
        background = image.resize((bg_w, bg_h), Image.Resampling.LANCZOS)
        left = max(0, (bg_w - target_w) // 2)
        top = max(0, (bg_h - target_h) // 2)
        background = background.crop((left, top, left + target_w, top + target_h))
        background = background.filter(__import__("PIL.ImageFilter", fromlist=["GaussianBlur"]).GaussianBlur(radius=18))

        foreground = image.resize((new_w, new_h), Image.Resampling.LANCZOS)
        x = (target_w - new_w) // 2
        y = (target_h - new_h) // 2
        background.paste(foreground, (x, y))
        background.save(out, "JPEG", quality=92, optimize=True, progressive=True)
    raw.unlink(missing_ok=True)
    return out


def login_client():
    username = os.getenv("IG_USERNAME", "").strip()
    password = os.getenv("IG_PASSWORD", "")
    session_b64 = os.getenv("IG_SESSION_B64", "").strip()
    allow_relogin = os.getenv("IG_ALLOW_RELOGIN", "0").strip().lower() in {"1", "true", "yes"}
    if not username:
        raise RuntimeError("IG_USERNAME is missing")
    if session_b64:
        try:
            SESSION_FILE.write_bytes(base64.b64decode(session_b64, validate=True))
        except Exception as exc:
            raise RuntimeError(f"IG_SESSION_B64 is invalid: {exc}") from exc

    client = Client()
    if SESSION_FILE.exists():
        try:
            client.load_settings(str(SESSION_FILE))
            # Do not call login(username, ""): instagrapi 3.x treats that as
            # a normal credential login and rejects the empty password.
            # The saved settings already contain the authenticated session,
            # device profile and user id. Validate that session directly.
            if not getattr(client, "user_id", None):
                raise RuntimeError("saved session has no user_id")
            client.user_info(client.user_id)
            client.dump_settings(str(SESSION_FILE))
            print("IG: saved session validated and reused without relogin")
            return client
        except Exception as exc:
            if not allow_relogin:
                raise RuntimeError(
                    f"IG session could not be validated; automatic relogin is disabled: {type(exc).__name__}: {exc}"
                ) from exc

    if not password:
        raise RuntimeError("IG_PASSWORD is missing and no reusable session is available")
    client.login(username, password)
    client.dump_settings(str(SESSION_FILE))
    print("IG: fresh login completed")
    return client

def main():
    state = load_state()
    day = today_key()
    daily_count = int(state.setdefault("daily", {}).get(day, 0))
    if daily_count >= MAX_POSTS_PER_DAY:
        print(f"IG: daily limit reached ({MAX_POSTS_PER_DAY})")
        return 0

    candidates = collect()
    posted = set(state.get("posted", []))
    posted_titles = {clean(x).casefold() for x in state.get("posted_titles", []) if x}
    candidate = next((item for item in candidates if item["key"] not in posted and clean(item["title"]).casefold() not in posted_titles), None)
    if not candidate:
        print("IG: no new candidate")
        return 0

    image = image_url(candidate.get("entry", feedparser.FeedParserDict()), candidate["link"])
    if not image:
        print("IG: candidate has no usable image; leaving it unposted")
        return 0

    caption = make_caption(candidate)
    if not caption:
        print("IG: language/AI gate blocked candidate")
        return 0

    path = download_image(image, candidate["key"])
    client = login_client()
    try:
        media = client.photo_upload(str(path), caption=caption)
        print(f"IG: published {media.pk} -> {candidate['title']}")
    finally:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass

    posted.add(candidate["key"])
    state["posted"] = list(posted)[-200:]
    titles = list(state.get("posted_titles", []))
    titles.append(candidate["title"])
    state["posted_titles"] = titles[-200:]
    state["daily"][day] = daily_count + 1
    # Keep the state compact and discard daily counters older than 7 days.
    state["daily"] = {k: v for k, v in state["daily"].items() if k >= day}
    save_state(state)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"IG FATAL: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
