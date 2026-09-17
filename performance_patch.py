"""Performance patch for NabzKhabar.

Keeps the existing clustering rules but avoids the expensive O(n^2) comparison
of every candidate against every previous candidate. No paid service/API is
used.
"""

import main


_ORIGINAL_CLUSTER = main.cluster_candidates


def fast_cluster_candidates(candidates):
    if not candidates:
        return []

    # Preserve the exact ordering used by the original implementation.
    ordered = sorted(
        candidates,
        key=lambda x: (
            main.publisher_quality(x.get("link", "")),
            x.get("published_at")
            or main.datetime.min.replace(tzinfo=main.timezone.utc),
        ),
        reverse=True,
    )

    clusters = []
    cluster_by_id = {}
    token_index = {}
    short_pool = []
    previous = []

    for candidate in ordered:
        story_tokens = main.story_tokens(candidate.get("title", ""))

        # For titles with >3 story tokens, same_story() can only return True
        # against another long title when at least one story token is shared.
        # Short titles are kept in a fallback pool because the original logic
        # also allows high title similarity for them.
        if len(story_tokens) <= 3:
            comparison_ids = range(len(previous))
        else:
            candidate_ids = set(short_pool)
            for token in story_tokens:
                candidate_ids.update(token_index.get(token, ()))
            comparison_ids = candidate_ids

        matched_cluster = None
        for previous_id in comparison_ids:
            existing = previous[previous_id]
            if main.same_story(candidate, existing):
                matched_cluster = cluster_by_id[previous_id]
                break

        candidate_id = len(previous)
        previous.append(candidate)

        if matched_cluster is None:
            matched_cluster = len(clusters)
            clusters.append([candidate])
        else:
            clusters[matched_cluster].append(candidate)

        cluster_by_id[candidate_id] = matched_cluster

        if len(story_tokens) <= 3:
            short_pool.append(candidate_id)

        for token in story_tokens:
            token_index.setdefault(token, []).append(candidate_id)

    result = []

    for cluster in clusters:
        representative = main.choose_cluster_representative(cluster)
        if not representative:
            continue

        representative["cluster_size"] = len(cluster)

        for item in cluster:
            if (
                not representative.get("summary")
                and item.get("summary")
            ):
                representative["summary"] = item["summary"]

            if (
                not representative.get("image_url")
                and item.get("image_url")
                and not main.is_google_host(item.get("image_url", ""))
            ):
                representative["image_url"] = item["image_url"]

        result.append(representative)

    return result


main.cluster_candidates = fast_cluster_candidates
print("PERFORMANCE PATCH: fast story clustering enabled")
