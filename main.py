import os
import requests
import feedparser
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin
from difflib import SequenceMatcher

BOT_TOKEN = "8863833653:AAGt5P8SUBun1zHDuDOrinn1z7gfwoWerUY"
CHAT_ID = "@NabzKhabarOfficial"
HISTORY_FILE = "sent_news.txt"

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

CATEGORIES = {
    "#ورزشی": ["استقلال", "پرسپولیس", "فوتبال", "لیگ", "ورزش", "سرمربی", "المپیک", "جام جهانی", "ورزش سه"],
    "#اقتصادی": ["بورس", "طلا", "سکه", "ارز", "دلار", "گرانی", "بازار", "بانک", "مسکن", "خودرو", "اقتصاد"],
    "#سیاسی": ["مجلس", "دولت", "رئیس جمهور", "وزیر", "مذاکره", "تحریم", "انتخابات", "شورای امنیت", "آمریکا", "ایران"],
    "#حوادث": ["زلزله", "تصادف", "آتش‌سوزی", "دستگیری", "پلیس", "قتل", "کشف", "سقوط"],
    "#فناوری": ["اینترنت", "هوش مصنوعی", "گوشی", "سامسونگ", "آیفون", "سایبری", "پلتفرم", "فناوری"]
}

IMPORTANT_KEYWORDS = ["فوری", "مهم", "هشدار", "جان باختن", "شهادت", "زلزله شدید", "سقوط", "انفجار"]

def load_sent_news():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def save_sent_news(sent_set):
    # نگه‌داشتن فقط ۲۰۰ لینک اخیر برای جلوگیری از بزرگ شدن فایل
    recent_links = list(sent_set)[-200:]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        for link in recent_links:
            f.write(f"{link}\n")

def clean_text(html_text):
    if not html_text:
        return ""
    soup = BeautifulSoup(html_text, "html.parser")
    text = soup.get_text(separator=' ')
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def is_similar(title1, title2):
    # بررسی شباهت متنی برای جلوگیری از ارسال خبر یکسان از دو خبرگزاری مختلف
    ratio = SequenceMatcher(None, title1, title2).ratio()
    return ratio > 0.75

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
        except Exception:
            pass

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
        except Exception:
            pass

def check_feeds():
    sent_news = load_sent_news()
    recent_titles = []

    for source_name, feed_url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:2]:
                news_id = entry.link
                title = clean_text(entry.title)

                # ۱. بررسی تکراری بودن لینک
                if news_id in sent_news:
                    continue

                # ۲. بررسی شباهت تیتر با اخبار تازه فرستاده شده
                if any(is_similar(title, prev_title) for prev_title in recent_titles):
                    sent_news.add(news_id)
                    continue

                image_url, body_text = extract_image_and_paragraphs(entry, feed_url)
                tags = detect_category_and_tags(title, body_text)
                
                header_icon = "🚨 <b>فوری | " if is_important(title) else "🔻 <b>"
                
                caption = f"{header_icon}{title}</b>\n\n"
                if body_text:
                    caption += f"{body_text}"
                caption += f"{tags}\n"
                caption += f"{CHAT_ID}"
                
                send_telegram(caption, image_url)
                sent_news.add(news_id)
                recent_titles.append(title)
        except Exception as e:
            print(f"Error checking {source_name}: {e}")

    save_sent_news(sent_news)

if __name__ == "__main__":
    check_feeds()
