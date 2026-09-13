import requests
import feedparser
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin

BOT_TOKEN = "8863833653:AAGt5P8SUBun1zHDuDOrinn1z7gfwoWerUY"
CHAT_ID = "@NabzKhabarOfficial"

RSS_FEEDS = {
    "تسنیم": "https://www.tasnimnews.com/fa/rss/feed/0/0/0/",
    "ایسنا": "https://www.isna.ir/rss",
    "مهر": "https://www.mehrnews.com/rss",
    "فارس": "https://www.farsnews.ir/rss",
    "ایرنا": "https://www.irna.ir/rss",
    "YJC": "https://www.yjc.ir/fa/rss/allnews",
    "خبرآنلاین": "https://www.khabaronline.ir/rss",
    "دنیای اقتصاد": "https://donya-e-eqtesad.com/fa/tinynews/rss/",
    "ورزش سه": "https://www.varzesh3.com/rss/all",
    "دیجیاتو": "https://digiato.com/feed"
}

SENT_NEWS = set()

CATEGORIES = {
    "#ورزشی": ["استقلال", "پرسپولیس", "فوتبال", "لیگ", "ورزش", "سرمربی", "المپیک", "جام جهانی", "ورزش سه"],
    "#اقتصادی": ["بورس", "طلا", "سکه", "ارز", "دلار", "گرانی", "بازار", "بانک", "مسکن", "خودرو", "اقتصاد"],
    "#سیاسی": ["مجلس", "دولت", "رئیس جمهور", "وزیر", "مذاکره", "تحریم", "انتخابات", "شورای امنیت", "آمریکا", "ایران"],
    "#حوادث": ["زلزله", "تصادف", "آتش‌سوزی", "دستگیری", "پلیس", "قتل", "کشف", "سقوط"],
    "#فناوری": ["اینترنت", "هوش مصنوعی", "گوشی", "سامسونگ", "آیفون", "سایبری", "پلتفرم", "فناوری"]
}

IMPORTANT_KEYWORDS = ["فوری", "مهم", "هشدار", "جان باختن", "شهادت", "زلزله شدید", "سقوط", "انفجار"]

def clean_text(html_text):
    if not html_text:
        return ""
    soup = BeautifulSoup(html_text, "html.parser")
    text = soup.get_text(separator=' ')
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def detect_category_and_tags(title, body):
    full_text = f"{title} {body}"
    detected_tags = set()
    
    for tag, keywords in CATEGORIES.items():
        for kw in keywords:
            if kw in full_text:
                detected_tags.add(tag)
                break
                
    if not detected_tags:
        detected_tags.add("#اخبار")
        
    return " ".join(detected_tags)

def is_important(title):
    return any(kw in title for kw in IMPORTANT_KEYWORDS)

def extract_image_and_paragraphs(entry, base_url):
    image_url = None
    
    try:
        if 'enclosures' in entry and len(entry.enclosures) > 0:
            for enc in entry.enclosures:
                if enc.get('type', '').startswith('image'):
                    image_url = enc.get('href')
                    break
                    
        if not image_url and 'media_content' in entry and len(entry.media_content) > 0:
            image_url = entry.media_content[0].get('url')

        raw_desc = entry.get('summary', entry.get('description', ''))
        soup = BeautifulSoup(raw_desc, 'html.parser')
        
        if not image_url:
            img_tag = soup.find('img')
            if img_tag and img_tag.get('src'):
                image_url = img_tag['src']

        if image_url:
            image_url = urljoin(base_url, image_url)
    except Exception:
        pass

    text_clean = clean_text(entry.get('summary', entry.get('description', '')))
    title_clean = clean_text(entry.title)
    
    sentences = [s.strip() for s in re.split(r'[.؛!؟]\s+', text_clean) if len(s.strip()) > 15]
    
    body_formatted = ""
    filtered_sentences = [s for s in sentences if s not in title_clean and "خبرگزاری" not in s]
    
    for s in filtered_sentences[:3]:
        body_formatted += f"🔷 {s}.\n\n"

    return image_url, body_formatted

def send_telegram(caption, image_url=None):
    sent_success = False
    
    if image_url:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        payload = {
            "chat_id": CHAT_ID,
            "photo": image_url,
            "caption": caption,
            "parse_mode": "HTML"
        }
        try:
            res = requests.post(url, data=payload, timeout=10)
            if res.ok:
                sent_success = True
        except Exception as e:
            print(f"Photo send failed: {e}")

    if not sent_success:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": caption,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        try:
            requests.post(url, data=payload, timeout=10)
        except Exception as e:
            print(f"Message send failed: {e}")

def check_feeds():
    for source_name, feed_url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:2]:
                news_id = entry.link
                if news_id not in SENT_NEWS:
                    title = clean_text(entry.title)
                    image_url, body_text = extract_image_and_paragraphs(entry, feed_url)
                    tags = detect_category_and_tags(title, body_text)
                    
                    header_icon = "🚨 <b>فوری | " if is_important(title) else "🔻 <b>"
                    
                    caption = f"{header_icon}{title}</b>\n\n"
                    if body_text:
                        caption += f"{body_text}"
                    caption += f"{tags}\n"
                    caption += f"{CHAT_ID}"
                    
                    send_telegram(caption, image_url)
                    SENT_NEWS.add(news_id)
        except Exception as e:
            print(f"Error checking {source_name}: {e}")

if __name__ == "__main__":
    check_feeds()
