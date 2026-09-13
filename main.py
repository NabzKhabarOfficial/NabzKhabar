import requests
import feedparser
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin

BOT_TOKEN = "8863833653:AAGt5P8SUBun1zHDuDOrinn1z7gfwoWerUY"
CHAT_ID = "@NabzKhabarOfficial"

# لیست جامع و کامل منابع خبری اصلی، ورزشی، اقتصادی و فناوری
RSS_FEEDS = {
    # خبرگزاری‌های عمومی و سیاسی
    "تسنیم": "https://www.tasnimnews.com/fa/rss/feed/0/0/0/",
    "ایسنا": "https://www.isna.ir/rss",
    "مهر": "https://www.mehrnews.com/rss",
    "فارس": "https://www.farsnews.ir/rss",
    "ایرنا": "https://www.irna.ir/rss",
    "YJC": "https://www.yjc.ir/fa/rss/allnews",
    "خبرآنلاین": "https://www.khabaronline.ir/rss",
    
    # تخصصی اقتصادی
    "دنیای اقتصاد": "https://donya-e-eqtesad.com/fa/tinynews/rss/",
    
    # تخصصی ورزشی
    "ورزش سه": "https://www.varzesh3.com/rss/all",
    
    # تخصصی فناوری
    "دیجیاتو": "https://digiato.com/feed"
}

SENT_NEWS = set()

# سیستم دسته‌بندی و هشتگ‌گذاری هوشمند موضوعی
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
    
    # ۱. استخراج تصویر از تگ‌های enclosures یا media_content
    if 'enclosures' in entry and len(entry.enclosures) > 0:
        for enc in entry.enclosures:
            if enc.get('type', '').startswith('image'):
                image_url = enc.get('href')
                break
                
    if not image_url and 'media_content' in entry and len(entry.media_content) > 0:
        image_url = entry.media_content[0].get('url')

    # ۲. استخراج عکس و متن از توضیحات HTML
    raw_desc = entry.get('summary', entry.get('description', ''))
    soup = BeautifulSoup(raw_desc, 'html.parser')
    
    if not image_url:
        img_tag = soup.find('img')
        if img_tag and img_tag.get('src'):
            image_url = img_tag['src']

    # اصلاح لینک عکس‌های نسبی (مثلا عکس‌هایی که ابتدای آنها دامنه سایت نیست)
    if image_url:
        image_url = urljoin(base_url, image_url)

    # استخراج و پاراگراف‌بندی متن
    text_clean = clean_text(raw_desc)
    title_clean = clean_text(entry.title)
    
    sentences = [s.strip() for s in re.split(r'[.؛!؟]\s+', text_clean) if len(s.strip()) > 15]
    
    body_formatted = ""
    filtered_sentences = [s for s in sentences if s not in title_clean and "خبرگزاری" not in s]
    
    for s in filtered_sentences[:3]:
        body_formatted += f"🔷 {s}.\n\n"

    return image_url, body_formatted

def send_telegram(caption, image_url=None):
    # ارسال عکس به صورت Photo در صورت وجود
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

    # ارسال متنی در صورت عدم وجود تصویر یا بروز خطا در لینک عکس
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
                    image_url, body_text = extract_image_and_paragraphs(entry, feed_url)
                    tags = detect_category_and_tags(title, body_text)
                    
                    # تعیین علامت تیتر (فوری یا معمولی)
                    header_icon = "🚨 <b>فوری | " if is_important(title) else "🔻<b>"
                    
                    caption = f"{header_icon}{title}</b>\n\n"
                    if body_text:
                        caption += f"{body_text}"
                    caption += f"{tags}\n"
                    caption += f"{CHAT_ID}"
                    
                    send_telegram(caption, image_url)
                    SENT_NEWS.add(news_id)
        except Exception as e:
            print(f"Error checking {feed_url}: {e}")

if __name__ == "__main__":
    check_feeds()
