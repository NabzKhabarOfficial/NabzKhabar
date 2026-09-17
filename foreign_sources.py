"""Free direct RSS sources for international news.

This module intentionally does not wrap or replace the v11 pipeline. It only
adds a small set of established publisher RSS feeds to main.DIRECT_RSS_FEEDS
when imported once by run_bot.py.
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


for feed in FOREIGN_RSS_FEEDS:
    if feed not in main.DIRECT_RSS_FEEDS:
        main.DIRECT_RSS_FEEDS.append(feed)


print(f"Foreign direct RSS: enabled ({len(FOREIGN_RSS_FEEDS)} sources)")
