"""NABZ KHABAR: review log of everything the bot sends and refuses (owner, Oct 18 2026).

The owner wants Brain to read EVERY post exactly as it went to Telegram, and every story that was refused,
to find risky / broken / incomplete news fast. The site pages (docs/news) only keep the headline, lead and
bullets, so a post cut short in Telegram looked fine there (Oct 18: two posts at 16:11 went out without
their bullets and footer). Now:

* docs/review/telegram_log.json: every Telegram send of this bot (sendMessage / sendPhoto / sendVideo /
  sendMediaGroup / edits): time, method, the exact text or caption, its length, ok / error description and
  message id. Last 3 days, at most 900 entries. The bot token is never stored.
* docs/review/rejected_log.json: every refused story, once per (title, reason) with first / last time and how
  many runs refused it (the same story is refused every 10 minutes). Last 48 hours.
* Root cause of the cut posts: the media-caption guard (v13_content_enhancer._safe_media_caption) cut the caption
  at 1000 characters from the START, so a long post lost its footer (hashtags, link) and the cut could fall
  inside a bullet. A long caption now keeps its footer and drops whole bullets from the end instead; the log
  records each trim ("trimmed_from").
Any error = the bot runs as before (the log is best effort).
"""

import atexit
import json
import os
import re
import time
from datetime import datetime, timezone

TG_LOG = os.path.join("docs", "review", "telegram_log.json")
REJ_LOG = os.path.join("docs", "review", "rejected_log.json")
TG_KEEP_SECONDS = 3 * 24 * 3600
TG_MAX = 900
REJ_KEEP_SECONDS = 48 * 3600
REJ_MAX = 4000
CAPTION_LIMIT = 1000
_SEND = re.compile(r"/(sendMessage|sendPhoto|sendVideo|sendAnimation|sendMediaGroup|editMessageText|editMessageCaption)(?:$|\?)")
SENT = []
REJECTED = {}
TRIMMED = {}
_DONE = {"v": False}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_caption(caption, limit=CAPTION_LIMIT):
    """Caption of at most `limit` characters that keeps the footer and drops whole lines from the body's end."""
    value = str(caption or "")
    if len(value) <= limit:
        return value
    lines = value.split("\n")
    sep = max((i for i, l in enumerate(lines) if "━━" in l), default=-1)
    if sep < 1:
        cut = value[:limit]
        boundary = max(cut.rfind("؟"), cut.rfind("."), cut.rfind("؛"), cut.rfind("\n"))
        return (cut[:boundary] if boundary >= 600 else cut).rstrip()
    start = sep
    while start > 1 and lines[start - 1].strip().startswith("#"):
        start -= 1
    tail = "\n".join(lines[start:]).strip()
    body = lines[:start]
    budget = max(200, limit - len(tail) - 2)

    def joined():
        return "\n".join(body).rstrip()

    while len(body) > 2 and len(joined()) > budget:
        body.pop()
        while len(body) > 2 and not body[-1].strip():
            body.pop()
    text = joined()
    if len(text) > budget:
        cut = text[:budget]
        boundary = max(cut.rfind("؟"), cut.rfind("."), cut.rfind("؛"), cut.rfind("!"))
        text = (cut[:boundary + 1] if boundary >= budget // 2 else cut).rstrip()
    out = text + "\n\n" + tail
    TRIMMED[out] = len(value)
    return out


def _install_caption_fix():
    import v13_content_enhancer as ce
    if getattr(ce._safe_media_caption, "_v13_keep_footer", False):
        return

    def keep_footer(caption):
        return safe_caption(caption)

    keep_footer._v13_keep_footer = True
    ce._safe_media_caption = keep_footer


def _install_send_log():
    import requests.sessions as rs
    if getattr(rs.Session.request, "_v13_review_log", False):
        return
    original = rs.Session.request

    def request(self, method, url, *args, **kwargs):
        m = _SEND.search(str(url)) if "api.telegram.org" in str(url) else None
        if not m:
            return original(self, method, url, *args, **kwargs)
        payload = kwargs.get("json") or kwargs.get("data") or {}
        if not isinstance(payload, dict):
            payload = {}
        text = payload.get("caption") or payload.get("text") or ""
        if not text and payload.get("media"):
            try:
                media = payload["media"]
                media = json.loads(media) if isinstance(media, str) else media
                text = " | ".join(str(x.get("caption", "")) for x in media if isinstance(x, dict))
            except Exception:
                text = ""
        entry = {"t": _now(), "method": m.group(1), "chat": str(payload.get("chat_id", ""))[:40],
                 "len": len(str(text)), "text": str(text)[:4096]}
        if str(text) in TRIMMED:
            entry["trimmed_from"] = TRIMMED.pop(str(text))
        try:
            resp = original(self, method, url, *args, **kwargs)
        except Exception as exc:
            entry.update({"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}"})
            SENT.append(entry)
            raise
        try:
            data = resp.json()
            entry["ok"] = bool(data.get("ok"))
            res = data.get("result")
            if isinstance(res, dict):
                entry["message_id"] = res.get("message_id")
            elif isinstance(res, list) and res and isinstance(res[0], dict):
                entry["message_id"] = res[0].get("message_id")
            if not entry["ok"]:
                entry["error"] = str(data.get("description", ""))[:300]
        except Exception:
            entry["ok"] = getattr(resp, "status_code", 0) == 200
            entry["status"] = getattr(resp, "status_code", 0)
        SENT.append(entry)
        return resp

    request._v13_review_log = True
    rs.Session.request = request


def _install_rejected_log():
    import v13_intelligence as intel
    prev = intel._rejected_record
    if getattr(prev, "_v13_review_log", False):
        return

    def rejected_record(main, candidate, score, reason, stage="intelligence_filter"):
        record = prev(main, candidate, score, reason, stage=stage)
        try:
            title = re.sub(r"\s+", " ", str(candidate.get("title", "") or "")).strip()[:220]
            why = str(reason or "")[:200]
            key = title + "|" + why
            now = _now()
            item = REJECTED.get(key)
            if item:
                item["last"] = now
                item["runs"] += 1
            else:
                REJECTED[key] = {"title": title, "reason": why, "stage": str(stage), "score": score,
                                 "source": str(candidate.get("source", "") or "")[:60],
                                 "url": str(candidate.get("link", "") or candidate.get("url", "") or "")[:300],
                                 "first": now, "last": now, "runs": 1}
        except Exception:
            pass
        return record

    rejected_record._v13_review_log = True
    intel._rejected_record = rejected_record


def _load(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _age(iso):
    try:
        return time.time() - datetime.fromisoformat(str(iso)).timestamp()
    except Exception:
        return 0


def save():
    try:
        os.makedirs(os.path.dirname(TG_LOG), exist_ok=True)
        if SENT:
            old = _load(TG_LOG, {}).get("sent", [])
            sent = [x for x in old + SENT if _age(x.get("t")) <= TG_KEEP_SECONDS][-TG_MAX:]
            with open(TG_LOG, "w", encoding="utf-8") as f:
                json.dump({"updated": _now(), "sent": sent}, f, ensure_ascii=False, indent=1)
        if REJECTED:
            old = {f"{x.get('title')}|{x.get('reason')}": x for x in _load(REJ_LOG, {}).get("rejected", [])}
            for key, item in REJECTED.items():
                prev = old.get(key)
                if prev:
                    prev["last"] = item["last"]
                    prev["runs"] = int(prev.get("runs", 1)) + item["runs"]
                else:
                    old[key] = item
            items = [x for x in old.values() if _age(x.get("last")) <= REJ_KEEP_SECONDS]
            items.sort(key=lambda x: str(x.get("last", "")), reverse=True)
            with open(REJ_LOG, "w", encoding="utf-8") as f:
                json.dump({"updated": _now(), "rejected": items[:REJ_MAX]}, f, ensure_ascii=False, indent=1)
    except Exception as exc:
        print(f"V13 REVIEW LOG: save skipped ({type(exc).__name__}: {exc})", flush=True)


def install():
    if _DONE["v"]:
        return
    for fix in (_install_caption_fix, _install_send_log, _install_rejected_log):
        try:
            fix()
        except Exception as exc:
            print(f"V13 REVIEW LOG: {fix.__name__} not installed ({type(exc).__name__}: {exc})", flush=True)
    atexit.register(save)
    _DONE["v"] = True
    print("V13 REVIEW LOG ACTIVE: docs/review/telegram_log.json (every send) + rejected_log.json; "
          "long captions keep their footer", flush=True)
