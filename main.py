import requests
import feedparser
from bs4 import BeautifulSoup
import re

BOT_TOKEN = "8863833653:AAGt5P8SUBun1zHDuDOrinn1z7gfwoWerUY"
CHAT_ID = "@NabzKhabarOfficial"

RSS_FEEDS = {
    "تسنیم": "https://www.tasnimnews.com/fa/rss/feed/0/0/0/",
    "ایسنا": "https://www.isna.ir/rss",
    "مهر": "https://www.mehrnews.com/rss"
}

SENT_NEWS = set()

def clean_text(html_text):
    if not html_text:
        return ""
    soup = BeautifulSoup(html_text, "html.parser")
    text = soup.get_text()
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def extract_image(entry):
    # ۱. جستجو در media_content یا enclosures
    if 'media_content' in entry and len(entry.media_content) > 0:
        return entry.media_content[0].get('url')
    if 'enclosures' in entry and len(entry.enclosures) > 0:
        for enc in entry.enclosures:
            if enc.get('type', '').startswith('image'):
                return enc.get('href')
    
    # ۲. جستجو در HTML خلاصه خبر
    description = entry.get('summary', entry.get('description', ''))
    soup = BeautifulSoup(description, "html.parser")
    img_tag = soup.find('img')
    if img_tag and img_tag.get('src'):
        return img_tag['src']
        
    return None

def send_telegram(caption, image_url=None):
    if image_url:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        payload = {
            "chat_id": CHAT_ID,
            "photo": image_url,
            "caption": caption,
            "parse_mode": "HTML"
        }
        try:
            res = requests.post(url, data=payload, timeout=12)
            if res.ok:
                return
        except Exception:
            pass

    # ارسال متنی در صورت عدم وجود عکس یا خطا در عکس
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": caption,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    requests.post(url, data=payload, timeout=12)

def check_feeds():
    for source_name, feed_url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:2]:
                news_id = entry.link
                if news_id not in SENT_NEWS:
                    title = clean_text(entry.title)
                    summary = clean_text(entry.get('summary', entry.get('description', '')))
                    
                    # حذف عنوان از ابتدای خلاصه در صورت تکرار
                    if summary.startswith(title):
                        summary = summary[len(title):].strip()
                    
                    # کوتاه کردن خلاصه خبر
                    if len(summary) > 200:
                        summary = summary[:200] + "..."

                    image_url = extract_image(entry)

                    # ساخت پیام با ظاهر جذاب و استاندارد
                    caption = f"🔻 <b>{title}</b>\n\n"
                    if summary:
                        caption += f"🔷 {summary}\n\n"
                    caption += f"📌 <b>خبرگزاری {source_name}</b>\n"
                    caption += f"🆔 {CHAT_ID}"

                    send_telegram(caption, image_url)
                    SENT_NEWS.add(news_id)
        except Exception as e:
            print(f"Error checking {feed_url}: {e}")

if __name__ == "__main__":
    check_feeds()
