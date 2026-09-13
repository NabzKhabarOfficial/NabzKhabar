import os
import io
import json
import time
import requests
import feedparser
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin
from difflib import SequenceMatcher
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = "@NabzKhabarOfficial"
HISTORY_FILE = "sent_news.txt"
AI_API_KEY = os.getenv("AI_API_KEY")

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
    "دیجیاتو": "https://digiato.com/feed",
    "زومیت": "https://www.zoomit.ir/feed/"
}

# دسته‌بندی‌های کامل‌تر و دقیق‌تر برای جلوگیری از برچسب اشتباه
CATEGORIES = {
    "#ورزشی": ["استقلال", "پرسپولیس", "فوتبال", "لیگ", "ورزش", "ورزشی", "سرمربی", "المپیک", "جام جهانی", "ورزش سه", "شمشیربازی", "مسابقات", "مدال", "کشتی", "فوتبالیست"],
    "#اقتصادی": ["بورس", "طلا", "سکه", "ارز", "دلار", "گرانی", "بازار", "بانک", "مسکن", "خودرو", "اقتصاد", "اقتصادی", "توکن", "سهام", "بیت کوین", "تورم", "حقوق"],
    "#سیاسی": ["مجلس", "دولت", "رئیس جمهور", "وزیر", "مذاکره", "تحریم", "انتخابات", "شورای امنیت", "آمریکا", "ایران", "سیاسی", "دیپلماتیک", "سفیر"],
    "#حوادث": ["زلزله", "تصادف", "آتش‌سوزی", "دستگیری", "پلیس", "قتل", "کشف", "سقوط", "حوادث", "مصدوم", "جان‌باخته", "فوتی"],
    "#فناوری": ["اینترنت", "هوش مصنوعی", "گوشی", "سامسونگ", "آیفون", "سایبری", "پلتفرم", "فناوری", "دیجیاتو", "زومیت", "اپلیکیشن", "تکنولوژی"],
    "#اجتماعی": ["هواشناسی", "آب و هوا", "دما", "بارندگی", "آموزش و پرورش", "کنکور", "دانشگاه", "پزشکی", "سلامت", "اجتماعی", "ترافیک", "تهران"]
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

def ai_rewrite(title, raw_text):
    if not AI_API_KEY:
        return None

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={AI_API_KEY}"
        prompt = (
            "تو یک خبرنگار ارشد و حرفه‌ای هستی. این خبر را بازنویسی کن.\n"
            "دستورالعمل‌ها:\n"
            "۱. خلاصه خبر را در ۲ یا ۳ جمله روان و جذاب بنویس.\n"
            "۲. در ابتدای هر جمله از ایموجی‌های مناسب با موضوع (مثل ⚽، 💵، 🏛️، 🚨، 💻، 🌤️ یا 🔹) استفاده کن.\n"
            "۳. لحن خبر باید کاملاً حرفه‌ای و بدون توضیحات اضافی باشد.\n\n"
            f"تیتر: {title}\nمتن: {raw_text}"
        )
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        res = requests.post(url, json=payload, timeout=10)
        if res.ok:
            data = res.json()
            return data['candidates'][0]['content']['parts'][0]['text'].strip()
    except Exception as e:
        print(f"AI Rewrite Error: {e}")
    return None

def add_watermark(image_url):
    try:
        response = requests.get(image_url, timeout=10)
        if response.status_code != 200:
            return None
            
        img = Image.open(io.BytesIO(response.content)).convert("RGBA")
        width, height = img.size
        
        overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(overlay)
        
        text_fa = "نبض خبر"
        text_en = "@NabzKhabarOfficial"
        
        # بارگذاری فونت با سایز متناسب و استاندارد (کوچک و شیک در گوشه تصویر)
        try:
            font_fa = ImageFont.truetype("Vazirmatn-Bold.ttf", 11)
            font_en = ImageFont.truetype("Vazirmatn-Regular.ttf", 8)
        except IOError:
            font_fa = ImageFont.load_default()
            font_en = ImageFont.load_default()
        
        # مختصات قرارگیری در گوشه پایین سمت راست با ابعاد کوچک
        box_width = 115
        box_height = 28
        x = width - box_width - 10
        y = height - box_height - 10
        
        # رسم کادر نیمه‌شفاف کوچک
        draw.rounded_rectangle([x, y, x + box_width, y + box_height], radius=4, fill=(0, 0, 0, 150))
        
        # درج متن‌ها داخل کادر
        draw.text((x + 8, y + 3), text_fa, fill=(255, 255, 255, 245), font=font_fa)
        draw.text((x + 8, y + 16), text_en, fill=(200, 220, 255, 230), font=font_en)
        
        watermarked = Image.alpha_composite(img, overlay).convert("RGB")
        
        img_byte_arr = io.BytesIO()
        watermarked.save(img_byte_arr, format='JPEG', quality=95)
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
    
    ai_summary = ai_rewrite(title_clean, text_clean)
    if ai_summary:
        return image_url, ai_summary + "\n\n"

    sentences = [s.strip() for s in re.split(r'[.؛!؟]\s+', text_clean) if len(s.strip()) > 25]
    body_formatted = ""
    filtered_sentences = [s for s in sentences if s not in title_clean and "خبرگزاری" not in s and "دیجیاتو" not in s and "زومیت" not in s]
    
    if not filtered_sentences and len(text_clean) > 20:
        filtered_sentences = [text_clean]

    for s in filtered_sentences[:2]:
        body_formatted += f"🔷 {s}.\n\n"

    return image_url, body_formatted

def send_telegram(caption, image_url=None):
    if not BOT_TOKEN:
        print("Error: BOT_TOKEN is missing!")
        return

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
                    "parse_mode": "HTML"
                }
                res = requests.post(url, data=data, files=files, timeout=15)
            else:
                payload = {
                    "chat_id": CHAT_ID,
                    "photo": image_url,
                    "caption": caption,
                    "parse_mode": "HTML"
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
            "disable_web_page_preview": True
        }
        try:
            requests.post(url, data=payload, timeout=10)
        except Exception:
            pass

def send_market_prices(sent_news):
    now = datetime.now()
    price_key = f"MARKET_PRICES_{now.strftime('%Y-%m-%d')}"
    if price_key in sent_news:
        return

    try:
        url_usdt = "https://api.nobitex.ir/v2/orderbook/USDTIRT"
        res_usdt = requests.get(url_usdt, timeout=10).json()
        usdt_price = int(res_usdt['lastTradePrice']) // 10 if 'lastTradePrice' in res_usdt else None

        url_btc = "https://api.nobitex.ir/v2/orderbook/BTCUSDT"
        res_btc = requests.get(url_btc, timeout=10).json()
        btc_price = float(res_btc['lastTradePrice']) if 'lastTradePrice' in res_btc else None

        caption = "📈 <b>گزارش روزانه قیمت‌های بازار و رمزارز</b>\n\n"
        if usdt_price:
            caption += f"💵 <b>دلار آزاد (تتر):</b> {usdt_price:,} تومان\n"
        if btc_price:
            caption += f"🪙 <b>بیت‌کوین:</b> ${btc_price:,.2f}\n"
        caption += "🪙 <b>سکه امامی:</b> استعلام لحظه‌ای\n"
        caption += "🏆 <b>طلای ۱۸ عیار:</b> استعلام لحظه‌ای\n\n"
        caption += "#بازار #قیمت_ارز #کریپتو\n"
        caption += f"{CHAT_ID}"

        send_telegram(caption)
        sent_news.add(price_key)
        time.sleep(3)
    except Exception as e:
        print(f"Market Prices Error: {e}")

def check_feeds():
    sent_news = load_sent_news()
    recent_titles = []

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
                
                time.sleep(3)
        except Exception as e:
            print(f"Error checking {source_name}: {e}")

    save_sent_news(sent_news)

if __name__ == "__main__":
    check_feeds()
