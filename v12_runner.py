import re

SOURCE = "main.py"


def patch_canonical_duplicate_guard(source):
    """Add a second duplicate guard based on the publisher's canonical article URL.

    This runs at workflow time and patches main.py without changing the existing
    v12 architecture. It catches the same article when RSS/Google gives a
    different URL variant or when the feed URL differs from the page canonical URL.
    """

    helper_marker = "def extract_canonical_article_url("

    if helper_marker not in source:
        marker = "# ============================================================\n# IMAGE\n# ============================================================"
        helper = '''# ============================================================
# CANONICAL ARTICLE URL
# ============================================================

def extract_canonical_article_url(url):
    """Return the publisher canonical URL or og:url for an article page."""

    if not url or is_google_host(url) or is_social_host(url):
        return ""

    try:
        response = SESSION.get(
            url,
            timeout=15,
            allow_redirects=True,
        )

        if response.status_code != 200:
            return ""

        content_type = response.headers.get(
            "content-type",
            "",
        ).lower()

        if "text/html" not in content_type:
            return ""

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        canonical = soup.find(
            "link",
            attrs={"rel": lambda value: value and "canonical" in value},
        )

        if canonical:
            value = canonical.get("href", "").strip()
            value = absolute_url(value, response.url)
            value = canonicalize_url(value)
            if value and not is_google_host(value) and not is_social_host(value):
                return value

        og_url = soup.find(
            "meta",
            attrs={"property": "og:url"},
        )

        if og_url:
            value = og_url.get("content", "").strip()
            value = absolute_url(value, response.url)
            value = canonicalize_url(value)
            if value and not is_google_host(value) and not is_social_host(value):
                return value

        final_url = canonicalize_url(response.url)
        if final_url and not is_google_host(final_url) and not is_social_host(final_url):
            return final_url

    except Exception as e:
        print(f"Canonical URL extraction failed: {e}")

    return ""


'''

        if marker not in source:
            raise RuntimeError("IMAGE section marker not found")

        source = source.replace(
            marker,
            helper + marker,
            1,
        )

    process_marker = '''    article_url = (
        candidate.get(
            "resolved_link"
        )
        or candidate.get(
            "link"
        )
    )'''

    guard_block = '''    article_url = (
        candidate.get(
            "resolved_link"
        )
        or candidate.get(
            "link"
        )
    )

    # --------------------------------------------------------
    # Canonical article URL duplicate guard.
    # --------------------------------------------------------

    canonical_article_url = ""

    if article_url:
        canonical_article_url = extract_canonical_article_url(
            article_url
        )

        if canonical_article_url:
            candidate["canonical_article_url"] = canonical_article_url

            if history_key_exists(
                original_title,
                canonical_article_url,
                hash_history,
            ):
                print(
                    "SKIPPED: canonical article URL history (duplicate article)"
                )
                return False'''

    if process_marker in source and "canonical_article_url = \"\"" not in source:
        source = source.replace(
            process_marker,
            guard_block,
            1,
        )

    # After a successful publish, persist the canonical URL identity as well as
    # the existing primary identity. This is intentionally applied to all three
    # Telegram delivery paths: video, photo, and text.
    old_publish = '''                hash_history.add(
                    history_key
                )'''

    new_publish = '''                hash_history.add(
                    history_key
                )

                if canonical_article_url:
                    hash_history.add(
                        make_history_key(
                            original_title,
                            canonical_article_url,
                        )
                    )'''

    source = source.replace(
        old_publish,
        new_publish,
    )

    return source


def main():
    with open(SOURCE, "r", encoding="utf-8") as f:
        source = f.read()

    patched = patch_canonical_duplicate_guard(source)

    if patched != source:
        with open(SOURCE, "w", encoding="utf-8") as f:
            f.write(patched)
        print("NABZ KHABAR: canonical article duplicate guard applied")
    else:
        print("NABZ KHABAR: canonical article duplicate guard already active")

    namespace = {"__name__": "__main__", "__file__": SOURCE}
    exec(compile(patched, SOURCE, "exec"), namespace)


if __name__ == "__main__":
    main()
