"""NABZ V13 — automatic channel growth.

1) Website: every published news post also becomes a page on a free GitHub
   Pages site (docs/), with an index, RSS feed and sitemap so search engines
   index it. Every page invites the reader to the Telegram channel.
2) Daily digest: once a day, after 22:00 Tehran time, the channel gets a
   "top stories of today" post built from the day's published news. Digest
   posts are the most forwarded format, and every forward carries the brand.
3) One-time cleanup (Oct 12 2026): pages published before the source/wording
   cleaners existed (Oct 8-11) still carried outlet names («به گزارش خبرگزاری مهر»,
   «پایگاه خبری تحلیلی انتخاب (Entekhab.ir)») and loaded words («رژیم صهیونیستی», «هلاکت»).
   retro_clean() runs the same cleaners over every stored item once, rebuilds
   its page, and marks docs/.retro_clean_v2 so it never runs again. v2 also strips
   page headers («۱۶ مهر ۱۴۰۵، ۲۲:۰۶ کد مطلب ... بین الملل ...»), repairs headlines cut mid-word
   («... با حوثی ها در ار» + lead «تباط هستیم/ ...»), and drops «در ادامه می آید» teasers.
4) Oct 12 (night review): the site title gets the same headline repair as the channel
   (v13_chrome_scrub.fix_title / fix_names), and retro_fix_v3() fixes today's bad pages once
   (docs/.retro_clean_v3): two repeats of the Galilee blast are taken off the site, and a cut
   headline, a lost surname, page chrome and leads that start mid-sentence are repaired.
5) Oct 13 (review): retro_fix_v4() (docs/.retro_clean_v4) repairs 6 more pages once: a sticky
   teaser before the lead, outlet names («العربی», «صداوسیما»), a 150+ character headline and
   leads that are only a relative clause («حملاتی که ...»).

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
RETRO_MARK = os.path.join(DOCS, ".retro_clean_v2")
RETRO_V3 = os.path.join(DOCS, ".retro_clean_v3")
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


def _repair_text(title, lead, details):
    """Same headline/name repair as the channel post (v13_chrome_scrub)."""
    try:
        import v13_chrome_scrub as cs
        title = cs.fix_names(cs.fix_title(title))
        lead = cs.fix_names(lead)
        details = [cs.fix_names(d) for d in details]
    except Exception:
        pass
    return title, lead, details


def parse_caption(caption, plan):
    lead, details = "", []
    for line in str(caption or "").splitlines():
        s = line.strip()
        if s.startswith("⚡️") or s.startswith("⚡"):
            lead = s.lstrip("⚡️").strip()
        elif s.startswith("▫️") or s.startswith("▫"):
            details.append(s.lstrip("▫️").strip())
    title, lead, details = _repair_text(plan.get("title", ""), lead, details)
    return {
        "title": title,
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
# One-time cleanup of pages published before the cleaners (Oct 12 2026)
# --------------------------------------------------------------------------

def _scrub(text, is_detail=False):
    """The owner's rules on an old line: no outlet name or «به گزارش ...», neutral wording.
    A detail line that only says what some outlet wrote is dropped ("").
    Order matters: strip_media removes the whole «به گزارش خبرگزاری مهر نیویورک تایمز،»
    first; clean() first would cut only «به گزارش خبرگزاری مهر» and leave «نیویورک تایمز،»."""
    import v13_byline_cleaner as bc
    raw = str(text or "")
    s = bc.strip_media(raw)
    s = bc.strip_outlet_leads(s)
    s = bc.clean(s)
    s = bc.neutral(s)
    s = re.sub(r"\s{2,}", " ", s).strip(" :،,")
    if is_detail and bc._MEDIA_SUBJECT_RE.search(s) and bc._REPORTING.search(s):
        return ""
    return s


def _scrub_title(title):
    import v13_byline_cleaner as bc
    t = bc.neutral(bc.clean(str(title or ""))).strip()
    return t or str(title or "")


def _repair(item):
    """v2: page header glued to the lead, a headline cut mid-word, a lead that is junk + a detail
    line, and «در ادامه می آید» teasers. Never leaves an empty lead."""
    import v13_byline_cleaner as bc
    title = str(item.get("title", "") or "")
    lead = str(item.get("lead", "") or "")
    details = [str(d or "") for d in item.get("details") or []]
    new = bc.strip_chrome(lead, title).strip()
    if len(new.split()) >= 6:
        lead = new
    if bc.looks_cut(title):
        ends = [m.start() for m in bc._SEG_END.finditer(title) if m.start() >= 40]
        if ends:
            title = title[:ends[-1]].strip(" /؛|،,:")
    for d in details:  # «<cut headline tail> ... <detail line>»: the detail line is the real lead
        if len(d) >= 40 and d in lead and lead.strip() != d.strip():
            lead = d
            details = [x for x in details if x != d]
            break
    details = [d for d in details if not bc._READ_ON.search(d) and d.strip() != lead.strip()]
    item.update(title=title, lead=lead, details=details)


_H1 = re.compile(r"(<h1>)(.*?)(</h1>)", re.S)
_LEAD = re.compile(r'(<p class="lead">)(.*?)(</p>)', re.S)
_LI = re.compile(r"(<li>)(.*?)(</li>)", re.S)


def _scrub_html(raw):
    """A page whose item is no longer in items.json: clean its headline, lead and details in place."""
    import v13_byline_cleaner as bc

    def sub(rx, fn, page):
        def rep(m):
            new = fn(html.unescape(m.group(2)))
            return f"{m.group(1)}{html.escape(new)}{m.group(3)}" if new else ""
        return rx.sub(rep, page)

    page = sub(_H1, _scrub_title, raw)
    page = sub(_LEAD, lambda s: _scrub(s) or s, page)
    page = sub(_LI, lambda s: "" if bc._READ_ON.search(s) else _scrub(s, True), page)
    page = page.replace("<ul></ul>", "")
    return bc.neutral(page)  # <title>, meta description, og tags


def retro_clean():
    if os.path.exists(RETRO_MARK):
        return
    try:
        items = load_items()
        if not items:
            return
        changed = 0
        for item in items:
            if not isinstance(item, dict) or not item.get("id") or "t" not in item:
                continue
            before = json.dumps(item, ensure_ascii=False, sort_keys=True)
            item["title"] = _scrub_title(item.get("title", ""))
            lead = _scrub(item.get("lead", ""))
            if lead:
                item["lead"] = lead
            item["details"] = [d for d in (_scrub(x, True) for x in item.get("details") or []) if d]
            try:
                _repair(item)
            except Exception as exc:
                print(f"V13 GROWTH: repair skipped for {item.get('id')} ({type(exc).__name__})", flush=True)
            if json.dumps(item, ensure_ascii=False, sort_keys=True) != before:
                _write(os.path.join(DOCS, "news", item["id"] + ".html"), render_item(item))
                changed += 1
        known = {x.get("id") for x in items if isinstance(x, dict)}
        orphans = 0
        folder = os.path.join(DOCS, "news")
        if os.path.isdir(folder):
            for name in sorted(os.listdir(folder)):
                if not name.endswith(".html") or name[:-5] in known:
                    continue
                path = os.path.join(folder, name)
                with open(path, "r", encoding="utf-8") as f:
                    raw = f.read()
                new = _scrub_html(raw)
                if new != raw:
                    _write(path, new)
                    orphans += 1
        _write(ITEMS_FILE, json.dumps(items, ensure_ascii=False, indent=1))
        build_site(items)
        stamp = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
        _write(RETRO_MARK, f"{stamp} pages_cleaned={changed} older_pages_cleaned={orphans}\n")
        print(f"V13 GROWTH: one-time cleanup done ({changed} pages + {orphans} older pages).", flush=True)
    except Exception as exc:
        print(f"V13 GROWTH: one-time cleanup skipped ({type(exc).__name__}: {exc})", flush=True)


# Oct 12 (night review): today's pages that broke the owner's rules.
V3_DROP = {
    "20261012-141808-ee5c48",  # Galilee blast, third time; the owner removed it from the channel
    "20261012-132935-6434ea",  # Galilee blast, second time; lead was a chain of related-video links
}
V3_FIX = {
    "20261012-163627-6d1abb": {"title": "عربستان امروز از برنامه های خود برای افزایش ظرفیت خط لوله راهبردی خود که تنگه هرمز را دور می زند خبر داد"},
    "20261012-093411-a23e94": {"lead": "دونالد ترامپ، رئیس جمهور آمریکا، به طور غیرمنتظره ای از برقراری «آتش بس انرژی» میان اوکراین و روسیه خبر داد که با ابراز شگفتی کی یف و سکوت مسکو روبه رو شد."},
    "20261012-003712-5e5c71": {"lead": "رسانه های خبری از حمله موشکی ارتش یمن به مواضع عربستان در خمیس مشیط و شهر ابها خبر دادند."},
    "20261012-080430-03f5b3": {"lead": "سخنگوی فراجا از شناسایی و دستگیری اعضای یک تیم تروریستی مرتبط با ترورهای اخیر در استان سیستان وبلوچستان خبر داد."},
    "20261012-001131-a11b2c": {"lead": "حمله به فرودگاه ریاض لحظه خطرناک دیگری را در منطقه ای رقم می زند که هم اکنون نیز غرق در تنش و درگیری است."},
    "20261012-062301-8bcf1a": {"lead": "ایران اعلام کرد آمریکا برخی از شرایط صلح را پذیرفته، اما این پاسخ را ناکافی دانست."},
    "20261012-061435-bf3bbc": {"lead": "نخست وزیر اسرائیل در پی حملات اخیر یمن به عربستان، با ریاض ابراز همدردی کرد."},
    "20261012-073048-f4b472": {"lead": "رسانه های عبری زبان از موافقت اسرائیل با اعزام نیروهای آمریکایی به مناطق تحت کنترل ارتش اسرائیل در جنوب نوار غزه خبر دادند."},
}


def _gone_page():
    body = ('<h1>این خبر برداشته شد</h1><p class="lead">این مطلب تکراری بود و از نبض خبر حذف شد.</p>'
            f'<a class="cta" href="../index.html">آخرین خبرها</a>')
    return _page("این خبر برداشته شد | نبض خبر", "این مطلب از نبض خبر برداشته شد.", body, SITE_URL, depth=1,
                 extra_head='<meta name="robots" content="noindex">\n'
                            '<meta http-equiv="refresh" content="0;url=../index.html">\n')


def retro_fix_v3():
    if os.path.exists(RETRO_V3):
        return
    try:
        items = load_items()
        if not items:
            return
        keep, dropped, fixed = [], 0, 0
        for item in items:
            iid = item.get("id") if isinstance(item, dict) else None
            if iid in V3_DROP:
                _write(os.path.join(DOCS, "news", iid + ".html"), _gone_page())
                dropped += 1
                continue
            if iid in V3_FIX:
                item.update(V3_FIX[iid])
                t, lead, details = _repair_text(item.get("title", ""), item.get("lead", ""),
                                                [str(d or "") for d in item.get("details") or []])
                item.update(title=t, lead=lead, details=[d for d in details if d.strip() != lead.strip()])
                _write(os.path.join(DOCS, "news", iid + ".html"), render_item(item))
                fixed += 1
            keep.append(item)
        _write(ITEMS_FILE, json.dumps(keep, ensure_ascii=False, indent=1))
        build_site(keep)
        stamp = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
        _write(RETRO_V3, f"{stamp} removed={dropped} fixed={fixed}\n")
        print(f"V13 GROWTH: v3 fix done ({dropped} repeats removed, {fixed} pages repaired).", flush=True)
    except Exception as exc:
        print(f"V13 GROWTH: v3 fix skipped ({type(exc).__name__}: {exc})", flush=True)


# Oct 13 (review): pages from Oct 12-13 that the v3 fix did not know yet (a sticky teaser, an outlet
# name in the headline, a headline over 150 characters, leads that are only a relative clause).
RETRO_V4 = os.path.join(DOCS, ".retro_clean_v4")
V4_FIX = {
    "20261012-175202-16e074": {"lead": "دولت بریتانیا روز دوشنبه از اعمال تحریم علیه دو مقام ایرانی خبر داد."},
    "20261012-201652-14984b": {"title": "شنیده شدن صدای انفجار در پایتخت عربستان؛ سامانه های هشدار ریاض فعال شدند",
                               "lead": "سامانه های هشدار در ریاض فعال شدند."},
    "20261012-201639-1d3e86": {"title": "سعدالله زارعی: امارات در ترورهای روزهای اخیر شرق ایران نقش داشته است",
                               "lead": "سعدالله زارعی، تحلیلگر سیاسی، گفت: «سیستم های پدافندی و دفاعی آمریکا در منطقه از بین رفته است و پس از جنگ با ایران نه تادها موفق شدند نه پاتریوت ها.»"},
    "20261012-163627-6d1abb": {"title": "عربستان ظرفیت خط لوله ای را که تنگه هرمز را دور می زند افزایش می دهد",
                               "lead": "این خط لوله تنگه هرمز را دور می زند و ظرفیت اسمی آن روزانه ۷ میلیون بشکه است."},
    "20261012-183138-79e877": {"lead": "این توافق با اعتراض قانون گذاران هر دو حزب جمهوری خواه و دموکرات روبه رو شده است."},
    "20261013-061428-f91cd8": {"lead": "حملات انصارالله، از جمله حمله به فرودگاه ریاض، دست کم ۱۳ کشته و بیش از ۳۰۰ زخمی بر جای گذاشت."},
}
_V4_OUTLET = re.compile(r"العربی|صدا ?و ?سیما|چرخش ناگهانی واشنگتن")


def retro_fix_v4():
    if os.path.exists(RETRO_V4):
        return
    try:
        items = load_items()
        if not items:
            return
        fixed = 0
        for item in items:
            iid = item.get("id") if isinstance(item, dict) else None
            if iid not in V4_FIX:
                continue
            item.update(V4_FIX[iid])
            t, lead, details = _repair_text(item.get("title", ""), item.get("lead", ""),
                                            [str(d or "") for d in item.get("details") or []])
            details = [d for d in details if d.strip() and d.strip() != lead.strip()
                       and not _V4_OUTLET.search(d.replace("\u200c", " "))]
            item.update(title=t, lead=lead, details=details)
            _write(os.path.join(DOCS, "news", iid + ".html"), render_item(item))
            fixed += 1
        _write(ITEMS_FILE, json.dumps(items, ensure_ascii=False, indent=1))
        build_site(items)
        stamp = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
        _write(RETRO_V4, f"{stamp} fixed={fixed}\n")
        print(f"V13 GROWTH: v4 fix done ({fixed} pages repaired).", flush=True)
    except Exception as exc:
        print(f"V13 GROWTH: v4 fix skipped ({type(exc).__name__}: {exc})", flush=True)


# --------------------------------------------------------------------------
# Install
# --------------------------------------------------------------------------

def install(core, current, plan_for):
    retro_clean()
    retro_fix_v3()
    retro_fix_v4()

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
