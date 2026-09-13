import requests
import feedparser

BOT_TOKEN = "8863833653:AAGt5P8SUBun1zHDuDOrinn1z7gfwoWerUY"
CHAT_ID = "@NabzKhabarOfficial"

RSS_FEEDS = [
    "https://www.tasnimnews.com/fa/rss/feed/0/0/0/",
    "https://www.isna.ir/rss",
    "https://www.mehrnews.com/rss"
]

SENT_NEWS = set()

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"Error sending message: {e}")

def check_feeds():
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:3]:
                news_id = entry.link
                if news_id not in SENT_NEWS:
                    title = entry.title
                    link = entry.link
                    
                    message = f"<b>🔴 {title}</b>\n\n🔗 <a href='{link}'>مشاهده کامل خبر</a>\n\n🆔 {CHAT_ID}"
                    
                    send_telegram(message)
                    SENT_NEWS.add(news_id)
        except Exception as e:
            print(f"Error reading feed {feed_url}: {e}")

if __name__ == "__main__":
    check_feeds()
