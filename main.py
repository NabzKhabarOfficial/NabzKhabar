import os
import time
import feedparser
from bs4 import BeautifulSoup
import requests
import traceback
import html

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = "@NabzKhabarOfficial"
SENT_NEWS_FILE = "sent_news.txt"

FEEDS = [
    "https://www.isna.ir/rss",
    "https://www.mehrnews.com/rss",
    "https://www.tasnimnews.com/fa/rss/feed/0/8/0/",
    "https://www.farsnews.ir/rss",
    "https://www.irna.ir/rss",
    "https://www.varzesh3.com/rss/all",
    "https://www.zoomit.ir/feed/",
    "https://economictimes.indiatimes.com/rssfeedstopstories.cms"
]

def load_sent_news():
    if not os.path.exists(SENT_NEWS_FILE):
        return set()
    with open(SENT_NEWS_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f)

def save_sent_news(link):
    with open(SENT_NEWS_FILE, "a", encoding="utf-8") as f:
        f.write(link + "\n")

def extract_image_url(entry):
    if hasattr(entry, 'media_content') and entry.media_content:
        for media in entry.media_content:
            if 'url' in media:
                return media['url']
                
    if hasattr(entry, 'enclosures') and entry.enclosures:
        for enclosure in entry.enclosures:
            if 'type' in enclosure and 'image' in enclosure['type']:
                return enclosure['href']
                
    content_to_check = ""
    if hasattr(entry, 'summary'):
        content_to_check = entry.summary
    elif hasattr(entry, 'content'):
        content_to_check = entry.content[0].value
        
    if content_to_check:
        soup = BeautifulSoup(content_to_check, "html.parser")
        img_tag = soup.find('img')
        if img_tag and img_tag.get('src'):
            return img_tag.get('src')
            
    return None

def send_to_telegram(text, image_url=None):
    if not TELEGRAM_BOT_TOKEN:
        print("Telegram Token not found!")
        return None
        
    if image_url:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        payload = {
            "chat_id": TELEGRAM_CHANNEL_ID,
            "photo": image_url,
            "caption": text,
            "parse_mode": "HTML"
        }
    else:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHANNEL_ID,
            "text": text,
            "parse_mode": "HTML"
        }
        
    response = requests.post(url, json=payload)
    print("Telegram Response:", response.text)
    return response.json()

def main():
    try:
        sent_news = load_sent_news()
        print(f"Loaded {len(sent_news)} previously sent news links.")
        
        for feed_url in FEEDS:
            print(f"Checking feed: {feed_url}")
            try:
                feed = feedparser.parse(feed_url)
                print(f"Found {len(feed.entries)} entries in {feed_url}")
                
                for entry in feed.entries[:2]:
                    link = getattr(entry, "link", "")
                    title = getattr(entry, "title", "بدون عنوان")
                    
                    if link:
                        if link not in sent_news:
                            clean_title = BeautifulSoup(title, "html.parser").get_text()
                            safe_title = html.escape(clean_title)
                            image_url = extract_image_url(entry)
                            
                            news_text = (
                                f"📰 <b>{safe_title}</b>\n\n"
                                f"🔗 <a href='{link}'>مطالعه کامل خبر</a>\n\n"
                                "🔴 #نبض_خبر | @NabzKhabarOfficial"
                            )
                            
                            print(f"Sending new news: {clean_title}")
                            send_to_telegram(news_text, image_url)
                            save_sent_news(link)
                            return
                        else:
                            print(f"Skipping already sent: {link}")
            except Exception as feed_err:
                print(f"Skipping feed due to error {feed_url}: {feed_err}")
                continue
                
    except Exception as e:
        print("CRITICAL ERROR IN MAIN:")
        traceback.print_exc()
        raise e

if __name__ == "__main__":
    main()
