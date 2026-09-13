import requests
import feedparser
from bs4 import BeautifulSoup

BOT_TOKEN = "8863833653:AAGt5P8SUBun1zHDuDOrinn1z7gfwoWerUY"
CHAT_ID = "@NabzKhabarOfficial"

RSS_FEEDS = [
    "https://www.tasnimnews.com/fa/rss/feed/0/0/0/",
    "https://www.isna.ir/rss",
    "https://www.mehrnews.com/rss"
]

SENT_NEWS = set()

def extract_image_and_text(entry):
    image_url = None
    
    # ۱. جستجوی تصویر در enclosure یا media
    if 'enclosures' in entry and len(entry.enclosures) > 0:
        for enc in entry.enclosures:
            if enc.get('type', '').startswith('image'):
                image_url = enc.get('href')
                break
                
    if not image_url and 'media_content' in entry:
        image_url = entry.media_content[0].get('url')

    # ۲. استخراج تصویر و متن از خلاصه/توضیحات
    description = entry.get('summary', entry.get('description', ''))
    soup = BeautifulSoup(description, 'html.parser')
    
    if not image_url:
        img_tag = soup.find('img')
        if img_tag and img_tag.get('src'):
            image_url = img_tag['src']

    # پاکسازی متن و آماده‌سازی پاراگراف‌ها
    text_content = soup.get_text().strip()
    sentences = [s.strip() for s in text_content.replace('\r', '').split('\n') if s.strip()]
    
    formatted_body = ""
    for s in sentences[:3]:  # استفاده از ۲ تا ۳ جمله اول
        if len(s) > 10:
            formatted_body += f"🔷 {s}\n\n"

    return image_url, formatted_body

def send_telegram(caption, image_url=None):
    if image_url:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        payload = {
            "chat_id": CHAT_ID,
            "photo": image_url,
            "caption": caption,
            "parse_mode": "HTML"
        }
    else:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": caption,
            "parse_mode": "HTML"
        }

    try:
        resp = requests.post(url, data=payload, timeout=12)
        # اگر ارسال عکس با خطا روبرو شد، پیام متنی ساده بفرست
        if not resp.ok and image_url:
            send_telegram(caption, image_url=None)
    except Exception as e:
        print(f"Error sending to Telegram: {e}")

def check_feeds():
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:3]:
                news_id = entry.link
                if news_id not in SENT_NEWS:
                    title = entry.title.strip()
                    image_url, body_text = extract_image_and_text(entry)
                    
                    # قالب‌بندی دقیقاً مشابه الگوی تصویر شما
                    caption = f"🔻<b>{title}</b>\n\n"
                    if body_text:
                        caption += f"{body_text}"
                    caption += f"{CHAT_ID}"
                    
                    send_telegram(caption, image_url)
                    SENT_NEWS.add(news_id)
        except Exception as e:
            print(f"Error reading feed {feed_url}: {e}")

if __name__ == "__main__":
    check_feeds()
