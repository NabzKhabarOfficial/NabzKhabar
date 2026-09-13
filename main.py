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
    text = soup.get_text(separator=' ')
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def extract_image_and_paragraphs(entry):
    image_url = None
    
    # ۱. استخراج تصویر اصلی از تگ‌های رسانه‌ای RSS
    if 'enclosures' in entry and len(entry.enclosures) > 0:
        for enc in entry.enclosures:
            if enc.get('type', '').startswith('image'):
                image_url = enc.get('href')
                break
                
    if not image_url and 'media_content' in entry and len(entry.media_content) > 0:
        image_url = entry.media_content[0].get('url')

    # ۲. استخراج عکس و متن از توضیحات
    raw_desc = entry.get('summary', entry.get('description', ''))
    soup = BeautifulSoup(raw_desc, 'html.parser')
    
    if not image_url:
        img_tag = soup.find('img')
        if img_tag and img_tag.get('src'):
            image_url = img_tag['src']

    # استخراج جملات محتوایی برای پاراگراف‌بندی
    text_clean = clean_text(raw_desc)
    title_clean = clean_text(entry.title)
    
    # تفکیک متن به جملات
    sentences = [s.strip() for s in re.split(r'[.؛!؟]\s+', text_clean) if len(s.strip()) > 15]
    
    body_formatted = ""
    filtered_sentences = [s for s in sentences if s not in title_clean and "خبرگزاری" not in s]
    
    # ساخت پاراگراف‌ها با ایموجی 🔷
    for s in filtered_sentences[:3]:
        body_formatted += f"🔷 {s}.\n\n"

    return image_url, body_formatted

def send_telegram(caption, image_url=None):
    # اگر تصویر وجود داشت آن را به صورت Photo ارسال کن
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
        except Exception as e:
            print(f"Error sending photo: {e}")

    # در صورت عدم وجود عکس، ارسال پیام متنی بدون پیش‌نمایش لینک (disable_web_page_preview)
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
                    image_url, body_text = extract_image_and_paragraphs(entry)
                    
                    # قالب‌بندی استاندارد خبر بدونه هیچ لینک اضافه‌ای
                    caption = f"🔻<b>{title}</b>\n\n"
                    if body_text:
                        caption += f"{body_text}"
                    caption += f"{CHAT_ID}"
                    
                    send_telegram(caption, image_url)
                    SENT_NEWS.add(news_id)
        except Exception as e:
            print(f"Error checking {feed_url}: {e}")

if __name__ == "__main__":
    check_feeds()
