import os
import io
import json
import requests
import feedparser
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin
from difflib import SequenceMatcher
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

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
    "#اقتصادی": ["بورس", "طلا", "سکه", "ارز", "دلار", "گرانی", "بازار", "بانک", "مسکن", "خودرو", "اقتصاد", "توکن", "سهام"],
    "#سیاسی": ["مجلس", "دولت", "رئیس جمهور", "وزیر", "مذاکره", "تحریم", "انتخابات", "شورای امنیت", "آمریکا", "ایران"],
    "#حوادث": ["زلزله", "تصادف", "آتش‌سوزی", "دستگیری", "پلیس", "قتل", "کشف", "سقوط"],
    "#فناوری": ["اینترنت", "هوش مصنوعی", "گوشی", "سامسونگ", "آیفون", "سایبری", "پلتفرم", "فناوری", "جاروبرقی", "دیجیاتو"]
}

IMPORTANT_KEYWORDS = ["فوری", "مهم", "هشدار", "جان باختن", "شهادت", "زلزله شدید", "سقوط", "انفجار"]

def load_sent_news():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def save_sent_news(sent_set):
    recent_links = list(sent_set)[-200:]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        for link in recent_links:
            f.write(f"{link}\n")

def clean_text(html_text):
    if not html_text:
        return ""
    soup = BeautifulSoup(html_text, "html.parser")
    text = soup.get_text(separator=' ')
    text = re.sub(r'The post.*?appeared first on.*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'appeared first on.*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def is_similar(title1, title2):
    return SequenceMatcher(None, title1, title2).ratio() > 0.75

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

# ۱. بخش حک واترمارک روی تصاویر
def add_watermark(image_url):
    try:
        response = requests.get(image_url, timeout=10)
        if response.status_code != 200:
            return None
            
        img = Image.open(io.BytesIO(response.content)).convert("RGB")
        width, height = img.size
        
        draw = ImageDraw.Draw(img)
        text = "NabzKhabarOfficial"
        
        # محاسبه ابعاد متن
        font = ImageFont.load_default()
        
        margin = 15
        x = width - 150
        y = height - 30
        
        # کشیدن پس‌زمینه نیمه‌شفاف سیاه
        draw.rectangle([x - 5, y - 5, x + 135, y + 20], fill=(0, 0, 0))
        # نوشتن آیدی کانال با رنگ سفید
        draw.text((x, y), text, fill=(255, 255, 255), font=font)
        
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG', quality=95)
        img_byte_arr.seek(0)
        return img_byte_arr
    except Exception as e:
        print(f"Watermark Error: {e}")
        return None

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
    
    sentences = [s.strip() for s in re.split(r'[.؛!؟]\s+', text_clean) if len(s.strip()) > 25]
    
    body_formatted = ""
    filtered_sentences = [s for s in sentences if s not in title_clean and "خبرگزاری" not in s and "دیجیاتو" not in s]
    
    if not filtered_sentences and len(text_clean) > 20:
        filtered_sentences = [text_clean]

    for s in filtered_sentences[:2]:
        body_formatted += f"🔷 {s}.\n\n"

    return image_url, body_formatted

# ۳. ارسال پیام همراه با دکمه‌های تعاملی شیشه‌ای
def send_telegram(caption, image_url=None):
    # دکمه‌های شیشه‌ای ری‌اکشن
    reply_markup = json.dumps({
        "inline_keyboard": [[
            {"text": "👍 کاربردی بود", "callback_data": "like"},
            {"text": "👎 بی‌کیفیت", "callback_data": "dislike"}
        ]]
    })

    sent_success = False
    if image_url:
        processed_image = add_watermark(image_url)
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        
        try:
            if processed_image:
                files = {'photo': ('image.jpg', processed_image, 'image/jpeg')}
                data = {
                    "chat_id": CHAT_ID,
                    "caption": caption,
                    "parse_mode": "HTML",
                    "reply_markup": reply_markup
                }
                res = requests.post(url, data=data, files=files, timeout=15)
            else:
                payload = {
                    "chat_id": CHAT_ID,
                    "photo": image_url,
                    "caption": caption,
                    "parse_mode": "HTML",
                    "reply_markup": reply_markup
                }
                res = requests.post(url, data=payload, timeout=10)

            if res.ok:
                sent_success = True
        except Exception as e:
            print(f"Error sending photo: {e}")

    if not sent_success:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": caption,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
            "reply_markup": reply_markup
        }
        try:
            requests.post(url, data=payload, timeout=10)
        except Exception:
            pass

# ۲. گزارش روزانه قیمت طلا و ارز
def send_market_prices(sent_news):
    now = datetime.now()
    # چک کردن زمان برای ارسال گزارش قیمت (مثلا در اجرای ظهر)
    price_key = f"MARKET_PRICES_{now.strftime('%Y-%m-%d')}"
    if price_key in sent_news:
        return

    try:
        url = "https://api.nobitex.ir/v2/orderbook/USDTIRT"
        res = requests.get(url, timeout=10).json()
        usdt_price = int(res['lastTradePrice']) // 10 if 'lastTradePrice' in res else None

        caption = "📈 <b>گزارش روزانه قیمت‌های بازار</b>\n\n"
        if usdt_price:
            caption += f"💵 <b>دلار آزاد (تتر):</b> {usdt_price:,} تومان\n"
        caption += "🪙 <b>سکه امامی:</b> نیازمند استعلام لحظه‌ای\n"
        caption += "🏆 <b>طلای ۱۸ عیار:</b> نیازمند استعلام لحظه‌ای\n\n"
        caption += "#بازار #قیمت_ارز\n"
        caption += f"{CHAT_ID}"

        send_telegram(caption)
        sent_news.add(price_key)
    except Exception as e:
        print(f"Market Prices Error: {e}")

def check_feeds():
    sent_news = load_sent_news()
    recent_titles = []

    # ارسال قیمت بازار در صورت لزوم
    send_market_prices(sent_news)

    for source_name, feed_url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:2]:
                news_id = entry.link
                title = clean_text(entry.title)

                if news_id in sent_news:
                    continue

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
