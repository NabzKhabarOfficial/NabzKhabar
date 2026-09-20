    candidates = _original_collect_candidates(hash_history, title_history)

    # V13 API layer: add only articles published in the last 30 minutes.
    # The adapter applies provider-specific free-tier quota guards before
    # making calls; API failures never stop the RSS/Google pipeline.
    try:
        candidates.extend(collect_api_candidates())
    except Exception as exc:
        print(f\"V13 API SOURCE LAYER ERROR: {exc}\")

    clean = []
    seen = set()

    for c in candidates:
        title = clean_title(c.get("title", ""))
        link = canonicalize_url(c.get("link", ""))
        if not title or len(title) < 12 or not link:
            continue
        if is_roundup_title(title):