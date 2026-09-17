"""Final pre-send duplicate lock for NabzKhabar.

The important difference from ordinary history checks is timing: a story is
reserved in sent_news.txt immediately BEFORE the Telegram API call. This
prevents a successful Telegram send followed by a timeout/crash from losing
the history record and being published again on the next run.
"""

import main

_ORIGINAL_PROCESS_NEWS = main.process_news
_ORIGINAL_SEND_MESSAGE = main.send_message
_ORIGINAL_SEND_PHOTO = main.send_photo
_ORIGINAL_SEND_VIDEO = main.send_video

_CONTEXT = None


def _context_candidate():
    return _CONTEXT[0] if _CONTEXT else None


def _context_history():
    if not _CONTEXT:
        return None, None
    return _CONTEXT[1], _CONTEXT[2]


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

    if main.history_key_exists(title, link, hash_history):
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
    candidate = _context_candidate()
    hash_history, title_history = _context_history()
    if not candidate or hash_history is None or title_history is None:
        return True

    title = main.clean_title(candidate.get("title", ""))
    link = _candidate_url(candidate)

    duplicate, reason = _already_seen(candidate, hash_history, title_history)
    if duplicate:
        print(f"FINAL SEND BLOCKED: duplicate ({reason}) | {title}")
        return False

    # Reserve every identity that can be used by a later run.
    hash_history.add(main.make_history_key(title, link))
    hash_history.add(main.make_legacy_history_key(title, link))
    hash_history.add(main.make_title_history_key(title))

    canonical = candidate.get("canonical_article_url", "")
    if canonical:
        hash_history.add(main.make_history_key(title, canonical))

    main.record_semantic_history(title, title_history)

    # Persist BEFORE Telegram. If the process is killed after Telegram accepts
    # the request, the reservation is still present on disk and the next run
    # will refuse the same story.
    main.save_history(hash_history, title_history)
    print(f"FINAL SEND RESERVED: {title}")
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
    _CONTEXT = (candidate, hash_history, title_history)
    try:
        return _ORIGINAL_PROCESS_NEWS(candidate, hash_history, title_history)
    finally:
        _CONTEXT = previous


main.send_message = guarded_send_message
main.send_photo = guarded_send_photo
main.send_video = guarded_send_video
main.process_news = guarded_process_news

print("Final pre-send duplicate lock: enabled")
