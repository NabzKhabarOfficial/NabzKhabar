"""NABZ V13 — automatic channel growth.

1) Website: every published news post also becomes a page on a free GitHub
   Pages site (docs/), with an index, RSS feed and sitemap so search engines
   index it. Every page invites the reader to the Telegram channel.
2) Daily digest: once a day, after 22:00 Tehran time, the channel gets a
   "top stories of today" post built from the day's published news. Digest
   posts are the most forwarded format, and every forward carries the brand.

All of it is best-effort: any failure is logged and never affects news
publication. The digest state lives in ai_model_health.json (persisted).
"""

import html
import json
import os
import re
import shutil
import time
from datetime import datetime, timedelta, timezone

SITE_URL = "https://nabzkhabarofficial.github.io/NabzKhabar/"
CHANNEL_URL = "https://t.me/NabzKhabarOfficial"
CHANNEL_MARK = "t.me/NabzKhabarOfficial"
DOCS = "docs"
ITEMS_FILE = os.path.join(DOCS, "items.json")
MAX_ITEMS = 300
INDEX_ITEMS = 60

DAILY_KEY = "_daily_items"
DIGEST_KEY = "_digest_last_date"
DIGEST_HOUR_TEHRAN = 22
DIGEST_MIN_ITEMS = 3
DIGEST_SIZE = 5
TEHRAN = timezone(timedelta(hours=3, minutes=30))

NUMBERS = ("1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣")
FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
FA_MONTHS = ("فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
             "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند")


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _jalali(gy, gm, gd):
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = (355666 + 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100
            + (gy2 + 399) // 400 + gd + g_d_m[gm - 1])
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm, jd = 1 + days // 31, 1 + days % 31
    else:
        jm, jd = 7 + (days - 186) // 30, 1 + (days - 186) % 30
    return jy, jm, jd


def fa_date(dt):
    jy, jm, jd = _jalali(dt.year, dt.month, dt.day)
    return f"{jd} {FA_MONTHS[jm - 1]} {jy}".translate(FA_DIGITS)


def fa_time(dt):
    return dt.strftime("%H:%M").translate(FA_DIGITS)


def parse_caption(caption, plan):
    lead, details = "", []
    for line in str(caption or "").splitlines():
        s = line.strip()
        if s.startswith("⚡️") or s.startswith("⚡"):
            lead = s.lstrip("⚡️").strip()
        elif s.startswith("▫️") or s.startswith("▫"):
            details.append(s.lstrip("▫️").strip())
    return {
        "title": plan.get("title", ""),
        "lead": lead,
        "details": details,
        "label": plan.get("label", "جهان"),
        "level": int(plan.get("level", 3) or 3),
        "urgent": bool(plan.get("urgent")),
    }


def _health():
    import v13_ai_router
    return v13_ai_router, v13_ai_router._load_health()


# --------------------------------------------------------------------------
# Daily store (persisted) + digest
# --------------------------------------------------------------------------

def remember_daily(item):
    try:
        router, health = _health()
        now = time.time()
        items = [x for x in (health.get(DAILY_KEY) or []) if isinstance(x, dict)
                 and now - float(x.get("t", 0) or 0) <= 48 * 3600]
        items.append({"t": now, "title": item["title"][:200], "level": item["level"],
                      "urgent": item["urgent"], "label": item["label"]})
        health[DAILY_KEY] = items[-120:]
        router._save_health(health)
    except Exception as exc:
        print(f"V13 GROWTH: daily store warning ({type(exc).__name__})", flush=True)


def build_digest(items, now_tehran):
    ranked = sorted(items, key=lambda x: (int(x.get("level", 3)), float(x.get("t", 0))), reverse=True)
    top = []
    seen = set()
    for x in ranked:
        title = str(x.get("title", "")).strip()
        if title and title not in seen:
            seen.add(title)
            top.append(x)
        if len(top) >= DIGEST_SIZE:
            break
    top.sort(key=lambda x: float(x.get("t", 0)))
    header = "🗞 مهم‌ترین خبرهای امروز"
    lines = [header, f"📅 {fa_date(now_tehran)}", ""]
    for i, x in enumerate(top):
        mark = "🔴 " if x.get("urgent") else ""
        lines.append(f"{NUMBERS[i]} {mark}{x['title']}")
        lines.append("")
    lines += ["💓 نبض خبر | خبرهای مهم، بدون حاشیه", "━━━━━━━━━━", f"🔗 {CHANNEL_MARK}"]
    text = "\n".join(lines)
    entities = [{"type": "bold", "offset": 0, "length": len(header.encode("utf-16-le")) // 2}]
    return text, entities, len(top)


def maybe_post_digest(core):
    try:
        now_utc = datetime.now(timezone.utc)
        now_tehran = now_utc.astimezone(TEHRAN)
        if now_tehran.hour < DIGEST_HOUR_TEHRAN:
            return
        today = now_tehran.date().isoformat()
        router, health = _health()
        if health.get(DIGEST_KEY) == today:
            return
        start = now_tehran.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        items = [x for x in (health.get(DAILY_KEY) or []) if isinstance(x, dict)
                 and float(x.get("t", 0) or 0) >= start]
        if len(items) < DIGEST_MIN_ITEMS:
            return
        text, entities, count = build_digest(items, now_tehran)
        response = core.SESSION.post(
            core.telegram_api("sendMessage"),
            data={
                "chat_id": core.CHANNEL_ID,
                "text": text,
                "entities": json.dumps(entities, ensure_ascii=False),
                "disable_web_page_preview": "true",
            },
            timeout=30,
        )
        if getattr(response, "ok", False):
            health = router._load_health()
            health[DIGEST_KEY] = today
            router._save_health(health)
            print(f"V13 GROWTH: daily digest published ({count} stories).", flush=True)
        else:
            print(f"V13 GROWTH: digest rejected ({getattr(response, 'status_code', '?')}).", flush=True)
    except Exception as exc:
        # Never print the exception text: it may contain the bot URL/token.
        print(f"V13 GROWTH: digest skipped ({type(exc).__name__}).", flush=True)


# --------------------------------------------------------------------------
# Website (GitHub Pages from /docs)
# --------------------------------------------------------------------------

CSS = """
@font-face{font-family:Vazirmatn;src:url(assets/Vazirmatn-Regular.ttf)}
*{box-sizing:border-box}body{margin:0;font-family:Vazirmatn,Tahoma,sans-serif;background:#0b0f17;color:#e9edf3;line-height:1.9}
a{color:inherit;text-decoration:none}.wrap{max-width:760px;margin:0 auto;padding:0 18px}
header{border-bottom:1px solid #1d2533;padding:18px 0}header .wrap{display:flex;justify-content:space-between;align-items:center}
.brand{font-weight:800;font-size:22px}.brand span{color:#e51c2d}.join{background:#e51c2d;color:#fff;border-radius:12px;padding:8px 16px;font-weight:700;font-size:15px}
.card{display:block;background:#121826;border:1px solid #1d2533;border-radius:16px;padding:16px 18px;margin:14px 0}
.card:hover{border-color:#e51c2d}.meta{font-size:13px;color:#8d98aa}.tag{display:inline-block;background:#1d2533;border-radius:8px;padding:0 8px;margin-left:6px}
.tag.urgent{background:#e51c2d;color:#fff}h1{font-size:26px;line-height:1.6;margin:22px 0 8px}h2{font-size:18px;margin:6px 0}
.lead{font-size:18px;color:#fff}ul{padding-right:20px}.cta{display:block;text-align:center;background:#e51c2d;color:#fff;border-radius:14px;padding:14px;margin:26px 0;font-weight:800;font-size:17px}
footer{color:#8d98aa;font-size:13px;text-align:center;padding:30px 0}
"""


def _page(title, description, body, canonical, depth=0, extra_head=""):
    prefix = "../" * depth
    css = CSS.replace("url(assets/", f"url({prefix}assets/")
    return f"""<!doctype html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(description)}">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{html.escape(title)}">
<meta property="og:description" content="{html.escape(description)}">
<meta property="og:type" content="article"><meta property="og:url" content="{canonical}">
<link rel="alternate" type="application/rss+xml" title="نبض خبر" href="{SITE_URL}feed.xml">
{extra_head}<style>{css}</style></head><body>
<header><div class="wrap"><a class="brand" href="{prefix}index.html">نبض <span>خبر</span></a>
<a class="join" href="{CHANNEL_URL}">عضویت در تلگرام</a></div></header>
<main class="wrap">{body}</main>
<footer>💓 نبض خبر | خبرهای مهم ایران و جهان، بدون حاشیه — <a href="{CHANNEL_URL}">t.me/NabzKhabarOfficial</a></footer>
</body></html>"""


def _tags(item):
    out = ""
    if item.get("urgent"):
        out += '<span class="tag urgent">فوری</span>'
    out += f'<span class="tag">{html.escape(item.get("label", ""))}</span>'
    return out


def render_item(item):
    when = datetime.fromtimestamp(item["t"], TEHRAN)
    canonical = f"{SITE_URL}news/{item['id']}.html"
    details = "".join(f"<li>{html.escape(d)}</li>" for d in item.get("details", []))
    ld = json.dumps({
        "@context": "https://schema.org", "@type": "NewsArticle",
        "headline": item["title"][:110], "datePublished": when.isoformat(),
        "inLanguage": "fa", "publisher": {"@type": "Organization", "name": "نبض خبر"},
        "mainEntityOfPage": canonical,
    }, ensure_ascii=False)
    body = f"""<p class="meta">{_tags(item)} {fa_date(when)} · {fa_time(when)}</p>
<h1>{html.escape(item['title'])}</h1>
<p class="lead">{html.escape(item.get('lead', ''))}</p>
{f'<ul>{details}</ul>' if details else ''}
<a class="cta" href="{CHANNEL_URL}">💓 خبرهای فوری و مهم را زودتر در کانال تلگرام نبض خبر ببینید</a>"""
    desc = item.get("lead") or item["title"]
    return _page(f"{item['title']} | نبض خبر", desc[:160], body, canonical, depth=1,
                 extra_head=f'<script type="application/ld+json">{ld}</script>\n')


def render_index(items):
    cards = []
    for item in items[:INDEX_ITEMS]:
        when = datetime.fromtimestamp(item["t"], TEHRAN)
        cards.append(f"""<a class="card" href="news/{item['id']}.html">
<p class="meta">{_tags(item)} {fa_date(when)} · {fa_time(when)}</p>
<h2>{html.escape(item['title'])}</h2></a>""")
    body = ('<a class="cta" href="' + CHANNEL_URL + '">💓 عضویت در کانال تلگرام نبض خبر</a>'
            + ("".join(cards) or '<p class="card">به‌زودی…</p>'))
    return _page("نبض خبر | خبرهای مهم ایران و جهان", "خبرهای فوری و مهم ایران و جهان، کوتاه و بدون حاشیه.",
                 body, SITE_URL)


def render_feed(items):
    entries = []
    for item in items[:50]:
        when = datetime.fromtimestamp(item["t"], timezone.utc)
        link = f"{SITE_URL}news/{item['id']}.html"
        entries.append(
            f"<item><title>{html.escape(item['title'])}</title><link>{link}</link><guid>{link}</guid>"
            f"<pubDate>{when.strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate>"
            f"<description>{html.escape(item.get('lead', ''))}</description></item>")
    return ('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
            f"<title>نبض خبر</title><link>{SITE_URL}</link><description>خبرهای مهم ایران و جهان</description>"
            f"<language>fa</language>{''.join(entries)}</channel></rss>")


def render_sitemap(items):
    urls = [f"<url><loc>{SITE_URL}</loc></url>"]
    for item in items:
        urls.append(f"<url><loc>{SITE_URL}news/{item['id']}.html</loc></url>")
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(urls) + "</urlset>")


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def load_items():
    try:
        with open(ITEMS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def build_site(items):
    _write(os.path.join(DOCS, "index.html"), render_index(items))
    _write(os.path.join(DOCS, "feed.xml"), render_feed(items))
    _write(os.path.join(DOCS, "sitemap.xml"), render_sitemap(items))
    _write(os.path.join(DOCS, "robots.txt"), f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}sitemap.xml\n")
    _write(os.path.join(DOCS, ".nojekyll"), "")
    font = os.path.join(DOCS, "assets", "Vazirmatn-Regular.ttf")
    if not os.path.exists(font) and os.path.exists("Vazirmatn-Regular.ttf"):
        os.makedirs(os.path.dirname(font), exist_ok=True)
        shutil.copyfile("Vazirmatn-Regular.ttf", font)


def publish_to_site(item):
    try:
        items = load_items()
        when = datetime.fromtimestamp(item["t"], timezone.utc)
        slug = re.sub(r"[^0-9a-f]", "", format(abs(hash(item["title"])) % (16 ** 6), "06x"))
        item["id"] = when.strftime("%Y%m%d-%H%M%S") + "-" + slug
        items.insert(0, item)
        items = items[:MAX_ITEMS]
        _write(os.path.join(DOCS, "news", item["id"] + ".html"), render_item(item))
        _write(ITEMS_FILE, json.dumps(items, ensure_ascii=False, indent=1))
        build_site(items)
        print(f"V13 GROWTH: site page created -> news/{item['id']}.html", flush=True)
    except Exception as exc:
        print(f"V13 GROWTH: site update skipped ({type(exc).__name__}: {exc})", flush=True)


# --------------------------------------------------------------------------
# Install
# --------------------------------------------------------------------------

def install(core, current, plan_for):
    def wrap(name, text_index):
        inner = getattr(core, name, None)
        if not callable(inner):
            return

        def recorded(*args, **kwargs):
            text = args[text_index] if len(args) > text_index else kwargs.get("caption", kwargs.get("text", ""))
            result = inner(*args, **kwargs)
            try:
                if result is True and CHANNEL_MARK in str(text or ""):
                    plan = plan_for(text)
                    if plan:
                        item = parse_caption(text, plan)
                        item["t"] = time.time()
                        remember_daily(item)
                        publish_to_site(dict(item))
            except Exception as exc:
                print(f"V13 GROWTH: record skipped ({type(exc).__name__})", flush=True)
            return result

        setattr(core, name, recorded)

    wrap("send_photo", 1)
    wrap("send_video", 1)
    wrap("send_message", 0)

    inner_main = getattr(core, "main", None)
    if callable(inner_main):
        def main_with_digest(*args, **kwargs):
            try:
                return inner_main(*args, **kwargs)
            finally:
                maybe_post_digest(core)

        core.main = main_with_digest
    print("V13 GROWTH ACTIVE: website pages + daily digest.", flush=True)
