import re

SOURCE = "main.py"


def patch_canonical_duplicate_guard(source):
    """Add a second duplicate guard based on the publisher's canonical article URL."""
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
        response = SESSION.get(url, timeout=15, allow_redirects=True)
        if response.status_code != 200:
            return ""
        content_type = response.headers.get("content-type", "").lower()
        if "text/html" not in content_type:
            return ""
        soup = BeautifulSoup(response.text, "html.parser")
        canonical = soup.find("link", attrs={"rel": lambda value: value and "canonical" in value})
        if canonical:
            value = canonical.get("href", "").strip()
            value = absolute_url(value, response.url)
            value = canonicalize_url(value)
            if value and not is_google_host(value) and not is_social_host(value):
                return value
        og_url = soup.find("meta", attrs={"property": "og:url"})
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
        source = source.replace(marker, helper + marker, 1)

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

    canonical_article_url = ""

    if article_url:
        canonical_article_url = extract_canonical_article_url(article_url)
        if canonical_article_url:
            candidate["canonical_article_url"] = canonical_article_url
            if history_key_exists(
                original_title,
                canonical_article_url,
                hash_history,
            ):
                print("SKIPPED: canonical article URL history (duplicate article)")
                return False'''

    if process_marker in source and "canonical_article_url = \"\"" not in source:
        source = source.replace(process_marker, guard_block, 1)

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
    source = source.replace(old_publish, new_publish)
    return source


def patch_source_coverage(source):
    """Expand only the free RSS/Google discovery lists; keep the v12 pipeline intact."""
    direct_marker = "DIRECT_RSS_FEEDS = ["
    direct_end = "\n]\n\n\n# ============================================================\n# GOOGLE NEWS DISCOVERY"

    expanded_direct = '''DIRECT_RSS_FEEDS = [
    ("ایران", "https://www.irna.ir/rss"),
    ("فناوری", "https://www.zoomit.ir/feed/"),
    ("ایران", "https://www.mehrnews.com/rss"),
    ("ایران", "https://www.isna.ir/rss"),
    ("اقتصاد", "https://www.isna.ir/rss/service/economy"),
    ("ورزش", "https://www.isna.ir/rss?serviceid=5"),
    ("جهان", "https://www.irna.ir/rss/service/world"),
    ("فناوری", "https://digiato.com/feed"),
    ("ایران", "https://www.yjc.ir/fa/rss/allnews"),
    ("فرهنگ", "https://www.irna.ir/rss/service/culture"),
    ("اجتماعی", "https://www.irna.ir/rss/service/society"),
    ("جهان", "https://www.isna.ir/rss/service/world"),
    # Additional free publisher feeds for broader coverage.
    ("ایران", "https://www.tabnak.ir/fa/rss/allnews"),
    ("ایران", "https://www.khabaronline.ir/rss"),
    ("ایران", "https://www.tasnimnews.com/fa/rss/feed/0/8/0/%D9%85%D9%87%D9%85%D8%AA%D8%B1%DB%8C%D9%86-%D8%AE%D8%A8%D8%B1%D8%A7%DB%8C-%D8%AA%D8%B3%D9%86%DB%8C%D9%85"),
    ("ایران", "https://www.asriran.com/fa/rss/allnews"),
    ("ایران", "https://www.entekhab.ir/fa/rss/allnews"),
    ("اقتصاد", "https://donya-e-eqtesad.com/fa/feeds/?p=all"),
    ("بین الملل", "https://www.iranpress.com/rss"),
    ("جهان", "https://www.iranintl.com/en/feed"),
    ("جهان", "https://irannewsdaily.com/feed/"),
    ("جهان", "https://www.theguardian.com/world/iran/rss"),
    ("جهان", "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml"),
]
'''

    if direct_marker in source and direct_end in source:
        start = source.index(direct_marker)
        end = source.index(direct_end, start) + 2
        source = source[:start] + expanded_direct + source[end:]

    google_marker = "GOOGLE_NEWS_FEEDS = ["
    google_end = "\n]\n\n\n# ============================================================\n# IMPORTANCE"

    expanded_google = '''GOOGLE_NEWS_FEEDS = [
    ("ایران", google_news_search_url("ایران")),
    ("خبر فوری", google_news_search_url("خبر فوری ایران")),
    ("خبر مهم", google_news_search_url("خبر مهم ایران")),
    ("رویترز", google_news_search_url("Reuters Iran world news")),
    ("حوادث", google_news_search_url("حادثه انفجار تصادف سقوط آتش سوزی ایران")),
    ("اقتصاد", google_news_search_url("اقتصاد ایران")),
    ("دلار", google_news_search_url("قیمت دلار بازار ایران")),
    ("ارز", google_news_search_url("قیمت ارز ایران")),
    ("طلا", google_news_search_url("قیمت طلا ایران")),
    ("سکه", google_news_search_url("قیمت سکه ایران")),
    ("بورس", google_news_search_url("بورس ایران")),
    ("نفت", google_news_search_url("نفت انرژی ایران")),
    ("هوش مصنوعی", google_news_search_url("هوش مصنوعی AI")),
    ("فناوری", google_news_search_url("فناوری تکنولوژی")),
    ("موبایل", google_news_search_url("موبایل گوشی")),
    ("خودرو", google_news_search_url("خودرو ماشین")),
    ("ورزش", google_news_search_url("ورزش فوتبال")),
    ("سلامت", google_news_search_url("سلامت پزشکی")),
    ("علم", google_news_search_url("علم دانش")),
    ("فرهنگ", google_news_search_url("فرهنگ هنر سینما")),
    ("جامعه", google_news_search_url("جامعه اجتماعی")),
    ("کریپتو", google_news_search_url("ارز دیجیتال بیت کوین کریپتو")),
    ("مسکن", google_news_search_url("مسکن اجاره خانه ایران")),
    ("کار", google_news_search_url("حقوق دستمزد اشتغال ایران")),
    ("آموزش", google_news_search_url("آموزش دانشگاه مدرسه کنکور ایران")),
    ("هواشناسی", google_news_search_url("هواشناسی ایران بارندگی")),
    ("انرژی", google_news_search_url("برق گاز انرژی ایران")),
    ("بانک", google_news_search_url("بانک مرکزی نرخ بهره ایران")),
    ("گمرک", google_news_search_url("تجارت واردات صادرات ایران")),
]
'''

    if google_marker in source and google_end in source:
        start = source.index(google_marker)
        end = source.index(google_end, start) + 2
        source = source[:start] + expanded_google + source[end:]

    return source


def main():
    with open(SOURCE, "r", encoding="utf-8") as f:
        source = f.read()

    patched = patch_canonical_duplicate_guard(source)
    patched = patch_source_coverage(patched)

    if patched != source:
        with open(SOURCE, "w", encoding="utf-8") as f:
            f.write(patched)
        print("NABZ KHABAR: v12 source coverage expanded")
    else:
        print("NABZ KHABAR: v12 source coverage already active")

    namespace = {"__name__": "__main__", "__file__": SOURCE}
    exec(compile(patched, SOURCE, "exec"), namespace)


if __name__ == "__main__":
    main()
