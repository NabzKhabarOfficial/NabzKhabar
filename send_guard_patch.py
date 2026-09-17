"""Final publication integrity guard for NabzKhabar.

This layer prevents three classes of corruption:
1) an already-published article being sent again;
2) a candidate title carrying another candidate's RSS summary;
3) an article URL resolving to a page whose extracted text is clearly about
   another story.

No extra API calls or paid services are used.
"""

import re
import main

_ORIGINAL_PROCESS_NEWS = main.process_news
_ORIGINAL_FETCH_ARTICLE = main.fetch_article
_ORIGINAL_SEND_MESSAGE = main.send_message
_ORIGINAL_SEND_PHOTO = main.send_photo
_ORIGINAL_SEND_VIDEO = main.send_video

_CONTEXT = None
_GENERIC = {
    "خبر", "گزارش", "اعلام", "آخرین", "جدید", "مهم", "تازه", "واکنش", "اظهارات", "مواضع",
    "توضیح", "انتقاد", "تاکید", "تأکید", "گفت", "گفتند", "کرد", "کردند", "شد", "شدند",
    "خواهد", "می", "شود", "است", "هست", "این", "آن", "یک", "از", "به", "در", "با",
    "برای", "و", "که", "را", "تا", "بر", "های", "ها", "هم", "نیز", "مورد", "درباره",
    "تصمیم", "انتشار", "کرده", "شده", "ایران", "آمریکا",
}


def _norm(text):
    text = main.normalize_digits(str(text or "")).lower()
    text = text.replace("ي", "ی").replace("ى", "ی").replace("ك", "ک").replace("‌", " ")
    text = re.sub(r"[\u200b-\u200f\ufeff]", " ", text)
    text = re.sub(r"[،؛,:.!؟()\[\]{}\"'«»/\\|_–—-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokens(text):
    return {x for x in _norm(text).split() if len(x) >= 2 and x not in _GENERIC}


def _same_topic(title, text):
    a, b = _tokens(title), _tokens(text)
    if not a or not b:
        return False
    common = a & b
    if len(common) >= 2:
        return True
    return any(len(w) >= 6 for w in common)


def _candidate_summary_is_safe(candidate):
    title = candidate.get("title", "")
    summary = candidate.get("summary", "") or candidate.get("description", "")
    if not summary:
        return True
    if _same_topic(title, summary):
        return True
    print(f"MIXED STORY BLOCKED: RSS summary does not match title | {title}")
    candidate["summary"] = ""
    candidate["description"] = ""
    return False


def guarded_fetch_article(url):
    text = _ORIGINAL_FETCH_ARTICLE(url)
    candidate = _CONTEXT[0] if _CONTEXT else None
    if candidate and text:
        title = candidate.get("title", "")
        if not _same_topic(title, text):
            print(f"ARTICLE TEXT BLOCKED: resolved page does not match title | {title}")
            return ""
    return text


def _candidate_url(candidate):
    if not candidate:
        return ""
    url = candidate.get("canonical_article_url") or candidate.get("resolved_link") or candidate.get("link") or ""
    try:
        return main.canonicalize_url(url)
    except Exception:
        return str(url).strip()


def _already_seen(candidate, hash_history, title_history):
    title = candidate.get("title", "") if candidate else ""
    link = _candidate_url(candidate)

    # main.py does not expose history_key_exists(). Check every history key
    # format directly so the final guard cannot crash the whole publication run.
    exact_keys = (
        main.make_history_key(title, link),
        main.make_legacy_history_key(title, link),
        main.make_title_history_key(title),
    )
    if any(key in hash_history for key in exact_keys):
        return True, "url_or_exact_title"
    if main.history_contains_story(title, title_history):
        return True, "semantic_title"

    event_checker = getattr(main, "event_history_contains", None)
    if event_checker is not None:
        try:
            if event_checker(candidate, title_history):
                return True, "same_real_world_event"
        except Exception as exc:
            print(f"Final event guard warning: {exc}")
    return False, ""


def _reserve_before_send():
    global _CONTEXT
    if not _CONTEXT:
        return True

    candidate, hash_history, title_history, reserved = _CONTEXT
    if reserved:
        return True

    title = main.clean_title(candidate.get("title", ""))
    link = _candidate_url(candidate)
    duplicate, reason = _already_seen(candidate, hash_history, title_history)
    if duplicate:
        print(f"FINAL SEND BLOCKED: duplicate ({reason}) | {title}")
        return False

    hash_history.add(main.make_history_key(title, link))
    hash_history.add(main.make_legacy_history_key(title, link))
    hash_history.add(main.make_title_history_key(title))
    canonical = candidate.get("canonical_article_url", "")
    if canonical:
        hash_history.add(main.make_history_key(title, canonical))

    main.record_semantic_history(title, title_history)
    main.save_history(hash_history, title_history)
    _CONTEXT = (candidate, hash_history, title_history, True)
    print(f"FINAL SEND RESERVED BEFORE TELEGRAM: {title}")
    return True


def guarded_send_message(text):
    if not _reserve_before_send():
        return False
    return _ORIGINAL_SEND_MESSAGE(text)


def guarded_send_photo(path, caption):
    if not _reserve_before_send():
        return False
    return _ORIGINAL_SEND_PHOTO(path, caption)


def guarded_send_video(path, caption):
    if not _reserve_before_send():
        return False
    return _ORIGINAL_SEND_VIDEO(path, caption)


def guarded_process_news(candidate, hash_history, title_history):
    global _CONTEXT
    previous = _CONTEXT
    before_hashes = set(hash_history)
    before_titles = list(title_history)
    _candidate_summary_is_safe(candidate)
    _CONTEXT = (candidate, hash_history, title_history, False)
    try:
        result = _ORIGINAL_PROCESS_NEWS(candidate, hash_history, title_history)
        if not result:
            hash_history.clear()
            hash_history.update(before_hashes)
            title_history[:] = before_titles
            main.save_history(hash_history, title_history)
            print("FINAL SEND RESERVATION RELEASED: publication did not succeed")
        return result
    finally:
        _CONTEXT = previous


main.fetch_article = guarded_fetch_article
main.send_message = guarded_send_message
main.send_photo = guarded_send_photo
main.send_video = guarded_send_video
main.process_news = guarded_process_news

print("Final publication integrity guard: enabled")
