"""Free direct RSS sources for international news.

This module intentionally does not replace the v11 pipeline. It adds
established publisher RSS feeds and gives those direct foreign sources a
small ranking boost so fresh international stories can compete with the
much larger pool of domestic candidates.
"""

import main


FOREIGN_RSS_FEEDS = [
    ("جهان", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("جهان", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("جهان", "https://rss.dw.com/rdf/rss-en-all"),
    ("جهان", "https://www.france24.com/en/rss"),
    ("جهان", "https://www.theguardian.com/world/rss"),
    ("جهان", "https://www.euronews.com/rss?level=theme&name=news"),
]


FOREIGN_DIRECT_HOSTS = {
    "bbc.com",
    "aljazeera.com",
    "dw.com",
    "france24.com",
    "theguardian.com",
    "euronews.com",
}


for feed in FOREIGN_RSS_FEEDS:
    if feed not in main.DIRECT_RSS_FEEDS:
        main.DIRECT_RSS_FEEDS.append(feed)


# Keep the existing v11 scoring intact, but make fresh direct foreign
# reporting competitive with the much larger domestic candidate pool.
_ORIGINAL_SOURCE_PRIORITY = main.source_priority


def source_priority(url, is_google=False):
    score = _ORIGINAL_SOURCE_PRIORITY(
        url,
        is_google=is_google,
    )

    if is_google:
        return score

    host = main.base_domain(
        main.get_hostname(url)
    )

    if any(
        host == domain or host.endswith("." + domain)
        for domain in FOREIGN_DIRECT_HOSTS
    ):
        score += 20

    return score


main.source_priority = source_priority


print(
    f"Foreign direct RSS: enabled ({len(FOREIGN_RSS_FEEDS)} sources); "
    "ranking boost: +20"
)
