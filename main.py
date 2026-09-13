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

def send_to_telegram(text):
    if not TELEGRAM_BOT_TOKEN:
        print("Telegram Token not found!")
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHANNEL_ID, "text": text, "parse_mode": "HTML"}
    response = requests.post(url, json=payload)
    print("Telegram Response:", response.text)
    return response.json()

def main():
    try:
        sent_news = load_sent_news()
        
        for feed_url in FEEDS:
            try:
                feed = feedparser.parse(feed_url)
                if not feed.entries:
                    continue
                for entry in feed.entries[:2]:
                    link = getattr(entry, "link", "")
                    title = getattr(entry, "title", "بدون عنوان")
                    
                    if link and link not in sent_news:
                        clean_title = BeautifulSoup(title, "html.parser").get_text()
                        safe_title = html.escape(clean_title)
                        
                        news_text = (
                            f"📰 <b>{safe_title}</b>\n\n"
                            f"🔗 <a href='{link}'>مطالعه کامل خبر</a>\n\n"
                            "🔴 #نبض_خبر | @NabzKhabarOfficial"
                        )
                        
                        send_to_telegram(news_text)
                        save_sent_news(link)
                        print(f"Sent: {clean_title}")
                        return
            except Exception as feed_err:
                print(f"Skipping feed due to error {feed_url}: {feed_err}")
                continue
                
    except Exception as e:
        print("CRITICAL ERROR IN MAIN:")
        traceback.print_exc()
        raise e

if __name__ == "__main__":
    main()
