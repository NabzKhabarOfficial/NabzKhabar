"""NabzKhabar image relevance patch.
Rejects publisher logos/branding and prefers article-specific images.
No paid service or API is used.

Performance note:
Image discovery is intentionally NOT performed for every RSS candidate.
Doing that during feed collection caused an extra HTTP request for many
unused stories. Images are resolved later, only for stories selected for
publication, inside main.process_news().
"""

import re
import json
import main
from bs4 import BeautifulSoup

LOGO_WORDS = {
    "logo", "logos", "logotype", "brand", "branding", "masthead",
    "favicon", "icon", "avatar", "placeholder", "default-image",
    "default_image", "defaultimage", "site-logo", "site_logo",
    "header-logo", "header_logo", "news-logo", "news_logo",
    "watermark", "sprite"
}

LOGO_CONTEXT_WORDS = {
    "foxnews-logo", "fox-news-logo", "cnn-logo", "bbc-logo",
    "reuters-logo", "ap-logo", "aljazeera-logo", "euronews-logo"
}


def _bad_logo_url(url):
    value = str(url or "").lower()
    if not value:
        return True
    path = re.sub(r"[^a-z0-9_-]+", " ", value)
    tokens = set(path.split())
    if tokens & LOGO_WORDS:
        return True
    return any(word in value for word in LOGO_CONTEXT_WORDS)


def enhanced_image_is_acceptable(url):
    if not main.image_is_acceptable(url):
        return False
    if _bad_logo_url(url):
        return False
    lower = str(url or "").lower()
    if lower.startswith(("data:", "blob:")):
        return False
    if ".svg" in lower:
        return False
    return True


# Keep the original validator available through this stronger wrapper.
main.image_is_acceptable = enhanced_image_is_acceptable


def _image_candidate_score(url, source, tag=None):
    if not enhanced_image_is_acceptable(url):
        return -999
    score = 0
    if source == "og":
        score += 30
    elif source == "twitter":
        score += 26
    elif source == "article":
        score += 22
    elif source == "jsonld":
        score += 20

    if tag is not None:
        try:
            width = int(tag.get("width", 0) or 0)
            height = int(tag.get("height", 0) or 0)
        except Exception:
            width = height = 0
        if width >= 900 or height >= 600:
            score += 10
        elif width >= 500 or height >= 300:
            score += 6
        elif (width and width < 250) or (height and height < 180):
            score -= 20

        classes = tag.get("class", [])
        class_text = " ".join(classes) if isinstance(classes, list) else str(classes or "")
        context = " ".join([
            tag.get("alt", ""), tag.get("title", ""),
            class_text, tag.get("id", "")
        ]).lower()
        if any(x in context for x in ("logo", "icon", "avatar", "brand", "masthead")):
            score -= 80
        if any(x in context for x in ("article", "hero", "featured", "main", "news")):
            score += 4

    return score


def enhanced_extract_image_from_html(html, page_url):
    if not html:
        return ""
    try:
        soup = BeautifulSoup(html, "html.parser")
        candidates = []

        meta_names = [
            ("property", "og:image", "og"),
            ("property", "og:image:url", "og"),
            ("property", "og:image:secure_url", "og"),
            ("name", "twitter:image", "twitter"),
            ("name", "twitter:image:src", "twitter"),
        ]
        for attr, value, source in meta_names:
            for tag in soup.find_all("meta", attrs={attr: value}):
                url = main.absolute_url(tag.get("content", "").strip(), page_url)
                if enhanced_image_is_acceptable(url):
                    candidates.append((_image_candidate_score(url, source), url))

        article_nodes = soup.select(
            "article img, [itemprop='articleBody'] img, "
            ".article-body img, .article__body img, "
            ".news-body img, .news-content img, main img"
        )
        seen = set()
        for img in article_nodes:
            src = (
                img.get("data-src") or img.get("data-original") or
                img.get("data-lazy-src") or img.get("src") or ""
            )
            src = main.absolute_url(src, page_url)
            if src in seen or not enhanced_image_is_acceptable(src):
                continue
            seen.add(src)
            candidates.append((_image_candidate_score(src, "article", img), src))

        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            try:
                data = json.loads(script.string or script.get_text())
                objects = data if isinstance(data, list) else [data]
                for obj in objects:
                    if not isinstance(obj, dict):
                        continue
                    images = obj.get("image")
                    if isinstance(images, str):
                        images = [images]
                    elif isinstance(images, dict):
                        images = [images.get("url", "")]
                    if not isinstance(images, list):
                        continue
                    for item in images:
                        image_url = item if isinstance(item, str) else (item or {}).get("url", "")
                        image_url = main.absolute_url(image_url, page_url)
                        if enhanced_image_is_acceptable(image_url):
                            candidates.append((_image_candidate_score(image_url, "jsonld"), image_url))
            except Exception:
                continue

        if not candidates:
            return ""
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1] if candidates[0][0] >= 0 else ""
    except Exception as exc:
        print(f"Enhanced image extraction error: {exc}")
        return ""


main.extract_image_from_html = enhanced_extract_image_from_html


def enhanced_extract_image_from_article(url):
    if not url:
        return ""
    try:
        response = main.SESSION.get(
            url, timeout=main.ARTICLE_TIMEOUT, allow_redirects=True
        )
        if response.status_code != 200:
            return ""
        content_type = response.headers.get("content-type", "").lower()
        if "text/html" not in content_type:
            return ""
        return enhanced_extract_image_from_html(response.text, response.url)
    except Exception as exc:
        print(f"Enhanced article image extraction error: {exc}")
        return ""


main.extract_image_from_article = enhanced_extract_image_from_article


def enhanced_collect_feed(category, url, is_google=False):
    """Keep feed collection network-light.

    RSS media URLs are retained and bad logo URLs are removed, but we do not
    fetch each article page here. The previous implementation fetched article
    HTML for almost every RSS candidate, including stories that would later be
    rejected by history/quality filters. The selected story gets full image
    relevance processing later in process_news().
    """
    candidates = main.collect_feed(category, url, is_google)
    for candidate in candidates:
        image_url = candidate.get("image_url", "")
        if image_url and _bad_logo_url(image_url):
            candidate["image_url"] = ""
    return candidates


# This wrapper is deliberately light: no article HTTP requests during RSS
# discovery. It preserves the existing image-quality logic for publication.
_original_collect_feed = main.collect_feed
main.collect_feed = enhanced_collect_feed

print("IMAGE PATCH: relevance enabled; feed discovery optimized")
