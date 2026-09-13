import os
import time
import feedparser
from bs4 import BeautifulSoup
import requests
import traceback

# تنظیمات اصلی
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = "@NabzKhabarOfficial"
SENT_NEWS_FILE = "sent_news.txt"
MARKET_STATE_FILE = "last_market_run.txt"

FEEDS = [
    "https://www.isna.ir/rss",
    "https://www.mehrnews.com/rss",
    "https://www.tasnimnews.com/fa/rss/feed/0/8/0/",
    "https://www.farsnews.ir/rss",
    "https://economictimes.indiatimes.com/rssfeedstopstories.cms"
]

def load_sent_news():
    if not os.path.exists(SENT_NEWS_FILE):
        return set()
    with open(SENT_NEWS_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f)

def save_sent_news(link):
    with open(SENT_NEWS_FILE, "a", encoding="utf-8") as f:
        f.write(link + "\n")

def send_to_telegram(text, image_path=None):
    if not TELEGRAM_BOT_TOKEN:
        print("Telegram Token not found!")
        return
        
    if image_path and os.path.exists(image_path):
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        with open(image_path, "rb") as photo:
            payload = {"chat_id": TELEGRAM_CHANNEL_ID, "caption": text, "parse_mode": "Markdown"}
            files = {"photo": photo}
            response = requests.post(url, data=payload, files=files)
    else:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHANNEL_ID, "text": text, "parse_mode": "Markdown"}
        response = requests.post(url, json=payload)
    
    return response.json()

def get_nobitex_prices():
    try:
        url = "https://api.nobitex.ir/v2/stats"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data.get("status") in ["success", "ok"]:
            stats = data.get("stats", {})
            usdt_price = stats.get("usdt-irt", {}).get("latest", "نامشخص")
            btc_price = stats.get("btc-irt", {}).get("latest", "نامشخص")
            
            if usdt_price != "نامشخص":
                usdt_price = f"{int(float(usdt_price)):,}"
            if btc_price != "نامشخص":
                btc_price = f"{int(float(btc_price)):,}"
                
            text = (
                "📊 **نرخ لحظه‌ای بازار و ارز (نوبیتکس)**\n\n"
                f"💵 تتر (USDT): `{usdt_price}` تومان\n"
                f"₿ بیت‌کوین (BTC): `{btc_price}` تومان\n\n"
                "🔴 #نبض_بازار | @NabzKhabarOfficial"
            )
            return text
    except Exception as e:
        print(f"Error fetching market stats: {e}")
    return None

def check_market_interval():
    current_time = time.time()
    interval = 6 * 3600  # هر ۶ ساعت
    
    if os.path.exists(MARKET_STATE_FILE):
        with open(MARKET_STATE_FILE, "r") as f:
            try:
                last_run = float(f.read().strip())
            except ValueError:
                last_run = 0
    else:
        last_run = 0
        
    if current_time - last_run >= interval:
        market_text = get_nobitex_prices()
        if market_text:
            send_to_telegram(market_text)
            with open(MARKET_STATE_FILE, "w") as f:
                f.write(str(current_time))

def main():
    try:
        sent_news = load_sent_news()
        
        # بررسی قیمت بازار بر اساس بازه ۶ ساعته
        check_market_interval()
        
        # بررسی اخبار جدید
        for feed_url in FEEDS:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:2]:
                link = getattr(entry, "link", "")
                title = getattr(entry, "title", "بدون عنوان")
                
                if link and link not in sent_news:
                    clean_title = BeautifulSoup(title, "html.parser").get_text()
                    
                    news_text = (
                        f"📰 **{clean_title}**\n\n"
                        f"🔗 [مطالعه کامل خبر]({link})\n\n"
                        "🔴 #نبض_خبر | @NabzKhabarOfficial"
                    )
                    
                    send_to_telegram(news_text)
                    save_sent_news(link)
                    print(f"Sent: {clean_title}")
                    return  # در هر اجرا یک خبر ارسال شود تا کانال اسپم نشود
    except Exception as e:
        print("CRITICAL ERROR IN MAIN:")
        traceback.print_exc()
        raise e

if __name__ == "__main__":
    main()
