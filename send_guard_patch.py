"""Final pre-send duplicate lock for NabzKhabar.

A story is reserved in sent_news.txt immediately BEFORE the Telegram API
request. This closes the crash/timeout window where Telegram can receive a
post but the normal end-of-run history save never happens.
"""

import main

_ORIGINAL_PROCESS_NEWS = main.process_news
_ORIGINAL_SEND_MESSAGE = main.send_message
_ORIGINAL_SEND_PHOTO = main.send_photo
_ORIGINAL_SEND_VIDEO = main.send_video

_CONTEXT = None


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
    global _CONTEXT
    if not _CONTEXT:
        return True

    candidate, hash_history, title_history, reserved = _CONTEXT
    if reserved:
        # The same process may fall back from video -> photo -> text.
        # Do not treat its own reservation as a duplicate.
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
    _CONTEXT = (candidate, hash_history, title_history, False)

    try:
        result = _ORIGINAL_PROCESS_NEWS(candidate, hash_history, title_history)

        # If no Telegram method succeeded, undo this run's reservation so a
        # genuinely failed publication can be retried later. If the process
        # crashes after Telegram accepts the request, this cleanup never runs,
        # so the reservation survives and prevents a duplicate.
        if not result:
            hash_history.clear()
            hash_history.update(before_hashes)
            title_history[:] = before_titles
            main.save_history(hash_history, title_history)
            print("FINAL SEND RESERVATION RELEASED: publication did not succeed")

        return result
    finally:
        _CONTEXT = previous


main.send_message = guarded_send_message
main.send_photo = guarded_send_photo
main.send_video = guarded_send_video
main.process_news = guarded_process_news

print("Final pre-send duplicate lock: enabled")
