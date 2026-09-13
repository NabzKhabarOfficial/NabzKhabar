import feedparser
import requests
from bs4 and import BeautifulSoup  # wait, beautifulsoup import is standard: from bs4 import BeautifulSoup
import os
import time
import json
from PIL import Image, ImageDraw, ImageFont
import io

# تنظیمات کلیدی
BOT_TOKEN = os.getenv("BOT_TOKEN")
AI_API_KEY = os.getenv("AI_API_KEY")
SENT_NEWS_FILE = "sent_news.txt"

# لیست فیدهای خبری
RSS_FEEDS = [
    "https://www.isna.ir/rss",
    "https://www.tasnimnews.com/fa/rss/feed/0/7/0/",
    "https://www.mehrnews.com/rss",
    "https://www.farsnews.ir/rss",
    "https://www.irna.ir/rss",
    "https://www.khabaronline.ir/rss",
    "https://www.isna.ir/rss/tp/0",
    "https://www.yjc.ir/fa/rss/allnews",
    "https://www.zoomit.info/feed/",
    "https://www.entekhab.ir/fa/rss/allnews",
    "https://www.asriran.com/fa/rss/allnews",
    "https://www.imna.ir/rss"
]

def load_sent_news():
    if os.path.exists(SENT_NEWS_FILE):
        with open(SENT_NEWS_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f)
    return set()

def save_sent_news(sent_set):
    with open(SENT_NEWS_FILE, "w", encoding="utf-8") as f:
        for link in sent_set:
            f.write(link + "\n")

def clean_text(text):
    if not text:
        return ""
    # پاکسازی عبارت‌های اضافی مثل (عکس)، [عکس]، (ویدیو) و غیره از متن
    unwanted = ["(عکس)", "[عکس]", "(ویدیو)", "[ویدیو]", "تصویر:", "ویدیو:"]
    for item in unwanted:
        text = text.replace(item, "")
    return text.strip()

def rewrite_with_gemini(title, summary):
    if not AI_API_KEY:
        return f"🔻 **{clean_text(title)}**\n\n🔹 {clean_text(summary)}"
    
    prompt = f"""شما یک خبرنگار حرفه‌ای در کانال «نبض خبر» هستید. این خبر را با لحنی جذاب، رسمی و خلاصه (حداکثر در ۳ خط) بازنویسی کنید. از ایموجی‌های مناسب استفاده کنید. هیچ کلمه‌ای مثل (عکس) یا برچسب اضافی در خروجی نیاورید.
عنوان: {title}
متن: {summary}"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={AI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    data = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        response = requests.post(url, headers=headers, json=data, timeout=15)
        if response.status_code == 200:
            res_json = response.json()
            rewritten = res_json['candidates'][0]['content']['parts'][0]['text']
            return clean_text(rewritten)
    except Exception as e:
        print(f"Gemini API Error: {e}")
    
    return f"🔻 **{clean_text(title)}**\n\n🔹 {clean_text(summary)}"

def create_watermarked_image(image_url):
    try:
        res = requests.get(image_url, timeout=10)
        if res.status_code != 200:
            return None
        
        img = Image.open(io.BytesIO(res.content)).convert("RGBA")
        draw = ImageDraw.Draw(img)
        
        # افزودن واترمارک متنی کوچک در گوشه عکس
        text = "NABZ KHABAR"
        width, height = img.size
        
        # رسم پس‌زمینه نیمه‌شفاف برای واترمارک
        padding = 10
        bbox = draw.textbbox((0, 0), text)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        
        x = width - tw - padding - 15
        y = height - th - padding - 15
        
        draw.rectangle([x - 10, y - 5, x + tw + 10, y + th + 5], fill=(15, 17, 26, 180))
        draw.text((x, y), text, fill=(255, 51, 75, 220))
        
        output = io.BytesIO()
        img.convert("RGB").save(output, format="JPEG", quality=85)
        output.seek(0)
        return output
    except Exception as e:
        print(f"Image processing error: {e}")
        return None

def send_to_telegram(text, image_bytes=None):
    channel_id = "@NabzKhabarOfficial"
    footer = "\n\n@NabzKhabarOfficial"
    full_text = text + footer

    if image_bytes:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        files = {"photo": ("image.jpg", image_bytes, "image/jpeg")}
        data = {"chat_id": channel_id, "caption": full_text, "parse_mode": "Markdown"}
        requests.post(url, data=data, files=files)
    else:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = {"chat_id": channel_id, "text": full_text, "parse_mode": "Markdown"}
        requests.post(url, data=data)

def get_nobitex_market():
    try:
        url = "https://api.nobitex.ir/v2/orderbook/all"
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            btc = data.get("USDTIRT", {}).get("last", "نیافته") # به عنوان مثال نرخ تتر/تومان
            return f"💵 **نرخ لحظه‌ای بازار:**\n🔹 تتر: {btc} تومان"
    except:
        pass
    return None

def main():
    sent_news = load_sent_news()
    new_sent_count = 0

    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:2]: # بررسی ۲ خبر آخر هر فید
                link = getattr(entry, 'link', '')
                if not link or link in sent_news:
                    continue
                
                title = getattr(entry, 'title', '')
                summary = getattr(entry, 'summary', getattr(entry, 'description', ''))
                
                # استخراج عکس در صورت وجود لینک معتبر تصویر در فید
                img_url = None
                if 'media_content' in entry and entry.media_content:
                    img_url = entry.media_content[0].get('url')
                elif 'enclosures' in entry and entry.enclosures:
                    for enc in entry.enclosures:
                        if 'image' in enc.get('type', ''):
                            img_url = enc.get('href')
                            break

                final_text = rewrite_with_gemini(title, summary)
                
                img_bytes = None
                if img_url:
                    img_bytes = create_watermarked_image(img_url)

                send_to_telegram(final_text, img_bytes)
                sent_news.add(link)
                new_sent_count += 1
                
                time.sleep(4) # وقفه برای جلوگیری از محدودیت تلگرام
                if new_sent_count >= 5: # محدودیت ارسال در هر دور اجرا
                    break
        except Exception as e:
            print(f"Feed error ({feed_url}): {e}")
        
        if new_sent_count >= 5:
            break

    save_sent_news(sent_news)

if __name__ == "__main__":
    main()
