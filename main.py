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
    "تسنیم (عمومی)": "https://www.tasnimnews.com/fa/rss/feed/0/0/0/",
    "تسنیم (اقتصادی)": "https://www.tasnimnews.com/fa/rss/feed/0/8/0/",
    "تسنیم (بین‌الملل و دفاعی/جنگ)": "https://www.tasnimnews.com/fa/rss/feed/0/3/0/",
    "ایسنا": "https://www.isna.ir/rss",
    "مهرنیوز": "https://www.mehrnews.com/rss",
    "فارس (سیاسی و امنیتی)": "https://www.farsnews.ir/rss",
    "ایرنا": "https://www.irna.ir/rss",
    "خبرآنلاین": "https://www.khabaronline.ir/rss",
    "دنیای اقتصاد (بازار، طلا، ارز)": "https://donya-e-eqtesad.com/fa/tinynews/rss/",
    "ورزش سه (ورزشی)": "https://www.varzesh3.com/rss/all",
    "دیجیاتو": "https://digiato.com/feed",
    "زومیت": "https://www.zoomit.ir/feed/"
}

IMPORTANT_KEYWORDS = ["فوری", "مهم", "هشدار", "جان باختن", "شهادت", "زلزله شدید", "سقوط", "انفجار", "درگیری", "حمله"]

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
            "۲. در ابتدای هر جمله از ایموجی‌های مناسب با موضوع (مثل ⚽، 💵، 🏛️، 🚨، 💻، ⚔️ یا 🔹) استفاده کن.\n"
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
        
        try:
            font_fa = ImageFont.truetype("Vazirmatn-Bold.ttf", 11)
            font_en = ImageFont.truetype("Vazirmatn-Regular.ttf", 8)
        except IOError:
            font_fa = ImageFont.load_default()
            font_en = ImageFont.load_default()
        
        box_width = 115
        box_height = 28
        x = width - box_width - 10
        y = height - box_height - 10
        
        draw.rounded_rectangle([x, y, x + box_width, y + box_height], radius=4, fill=(0, 0, 0, 150))
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

def extract_media_and_paragraphs(entry, base_url):
    media_url = None
    media_type = 'photo'
    try:
        if 'enclosures' in entry:
            for enc in entry.enclosures:
                enc_type = enc.get('type', '')
                if enc_type.startswith('video'):
                    media_url = enc.get('href')
                    media_type = 'video'
                    break
                elif enc_type.startswith('image') and not media_url:
                    media_url = enc.get('href')
                    media_type = 'photo'
                    
        if not media_url and 'media_content' in entry:
            for mc in entry.media_content:
                mc_type = mc.get('type', '') or mc.get('medium', '')
                if 'video' in mc_type:
                    media_url = mc.get('url')
                    media_type = 'video'
                    break
                elif 'image' in mc_type and not media_url:
                    media_url = mc.get('url')
                    media_type = 'photo'

        raw_desc = entry.get('summary', entry.get('description', ''))
        soup = BeautifulSoup(raw_desc, 'html.parser')
        
        if not media_url:
            video_tag = soup.find('video')
            if video_tag and video_tag.get('src'):
                media_url = video_tag['src']
                media_type = 'video'
            else:
                img_tag = soup.find('img')
                if img_tag and img_tag.get('src'):
                    media_url = img_tag['src']
                    media_type = 'photo'

        if media_url:
            media_url = urljoin(base_url, media_url)
    except Exception:
        pass

    text_clean = clean_text(entry.get('summary', entry.get('description', '')))
    title_clean = clean_text(entry.title)
    
    ai_summary = ai_rewrite(title_clean, text_clean)
    if ai_summary:
        return media_url, media_type, ai_summary + "\n\n"

    sentences = [s.strip() for s in re.split(r'[.؛!؟]\s+', text_clean) if len(s.strip()) > 25]
    body_formatted = ""
    filtered_sentences = [s for s in sentences if s not in title_clean and "خبرگزاری" not in s and "دیجیاتو" not in s and "زومیت" not in s]
    
    if not filtered_sentences and len(text_clean) > 20:
        filtered_sentences = [text_clean]

    for s in filtered_sentences[:2]:
        body_formatted += f"🔷 {s}.\n\n"

    return media_url, media_type, body_formatted

def send_telegram(caption, media_url=None, media_type='photo'):
    if not BOT_TOKEN:
        print("Error: BOT_TOKEN is missing!")
        return False

    if media_url:
        if media_type == 'video':
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo"
            payload = {
                "chat_id": CHAT_ID,
                "video": media_url,
                "caption": caption,
                "parse_mode": "HTML"
            }
            try:
                res = requests.post(url, data=payload, timeout=20)
                if res.ok:
                    return True
            except Exception as e:
                print(f"Error sending video: {e}")
            return False
        else:
            # ارسال عکس همراه با واترمارک
            processed_image = add_watermark(media_url)
            if not processed_image:
                print("Skipping post: Image download or watermark failed.")
                return False  # پستی که عکس دارد ولی عکس نمی‌دهد/خطا دارد ارسال نمی‌شود
                
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
            try:
                files = {'photo': ('image.jpg', processed_image, 'image/jpeg')}
                data = {
                    "chat_id": CHAT_ID,
                    "caption": caption,
                    "parse_mode": "HTML"
                }
                res = requests.post(url, data=data, files=files, timeout=15)
                if res.ok:
                    return True
            except Exception as e:
                print(f"Error sending photo: {e}")
            return False
    else:
        # اگر خبر کلاً عکس ندارد، به صورت متن ارسال شود
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": caption,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        try:
            res = requests.post(url, data=payload, timeout=10)
            if res.ok:
                return True
        except Exception as e:
            print(f"Error sending text message: {e}")
        return False

def send_market_prices(sent_news):
    now = datetime.now()
    current_block = now.hour // 8
    price_key = f"MARKET_PRICES_{now.strftime('%Y-%m-%d')}_block_{current_block}"
    
    if price_key in sent_news:
        return

    try:
        url_usdt = "https://api.nobitex.ir/v2/orderbook/USDTIRT"
        res_usdt = requests.get(url_usdt, timeout=10).json()
        usdt_price = int(res_usdt['lastTradePrice']) // 10 if 'lastTradePrice' in res_usdt else None

        url_btc = "https://api.nobitex.ir/v2/orderbook/BTCUSDT"
        res_btc = requests.get(url_btc, timeout=10).json()
        btc_price = float(res_btc['lastTradePrice']) if 'lastTradePrice' in res_btc else None

        caption = "📈 <b>گزارش بروز قیمت‌های بازار و ارز</b>\n\n"
        if usdt_price:
            caption += f"💵 <b>دلار آزاد (تتر):</b> {usdt_price:,} تومان\n"
        else:
            caption += f"💵 <b>دلار آزاد:</b> در حال به‌روزرسانی\n"
            
        caption += "🪙 <b>سکه امامی:</b> بر اساس آخرین نرخ بازار\n"
        caption += "🏆 <b>طلای ۱۸ عیار:</b> بر اساس آخرین نرخ بازار\n"
        
        if btc_price:
            caption += f"🪙 <b>بیت‌کوین:</b> ${btc_price:,.2f}\n"
            
        caption += f"\n{CHAT_ID}"

        if send_telegram(caption):
            sent_news.add(price_key)
            save_sent_news(sent_news)
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

                media_url, media_type, body_text = extract_media_and_paragraphs(entry, feed_url)
                
                header_icon = "🚨 <b>فوری | " if is_important(title) else "🔻 <b>"
                
                caption = f"{header_icon}{title}</b>\n\n"
                if body_text:
                    caption += f"{body_text}"
                caption += f"{CHAT_ID}"
                
                # ارسال به تلگرام و بررسی موفقیت‌آمیز بودن آن
                success = send_telegram(caption, media_url, media_type)
                if success:
                    sent_news.add(news_id)
                    recent_titles.append(title)
                    save_sent_news(sent_news)
                    time.sleep(3)
                    break # یک خبر موفق از این فید ارسال شد، برو سراغ فید بعدی
        except Exception as e:
            print(f"Error checking {source_name}: {e}")

if __name__ == "__main__":
    check_feeds()
