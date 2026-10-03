# نبض خبر | NabzKhabar

ربات خبری خودکار فارسی که خبرهای مهم ایران و جهان را از منابع معتبر جمع می‌کند، با چند لایه کنترل کیفیت و سردبیری هوش مصنوعی فیلتر می‌کند و در کانال تلگرام و اینستاگرام منتشر می‌کند.

📢 تلگرام: https://t.me/NabzKhabarOfficial  
🌐 سایت: https://nabzkhabarofficial.github.io/NabzKhabar/

## جریان کار

1. جمع‌آوری خبر از RSS منابع معتبر
2. حذف تبلیغ، تکراری‌ها و خبرهای کهنه (`v13_ad_filter`, `v13_story_dedup`, `v13_freshness_rescue`)
3. سنجش اهمیت و ارتباط (`v13_intelligence`, `v13_relevance_gate`, `v13_quality_gate`)
4. سردبیر هوش مصنوعی و گارد سیاست محتوا (`v13_editor_gate`, `v13_policy_guard`)
5. نگارش و قالب‌بندی فارسی (`v13_editorial_formatter`, `v13_content_enhancer`, `v13_post_design`, `v13_media_branding`)
6. انتشار در تلگرام و ساخت صفحه‌های سایت در `docs/`
7. پایش سلامت و ثبت وضعیت (`v13_monitor` → `v13_health.json`, `v13_monitor.json`)

مسیریاب هوش مصنوعی (`v13_ai_router`) بین چند مدل جابه‌جا می‌شود و مدل‌های خراب را موقتاً کنار می‌گذارد (`ai_model_health.json`).

نقطه‌ی ورود: `run_bot.py`

## ماژول‌های جانبی

- `market_prices.py` قیمت ارز و طلا
- `car_prices.py` قیمت خودرو
- `weather.py` آب‌وهوا
- `education.py` محتوای آموزشی
- `instagram_publisher.py` و `instagram_reel.py` انتشار روزانه در اینستاگرام

## خودکارسازی (GitHub Actions)

- `bot.yml` اجرای ربات به‌صورت دوره‌ای، با بررسی کامپایل، تست import، سلامت مدل‌ها و ذخیره‌ی وضعیت
- `market-prices.yml` به‌روزرسانی قیمت‌ها هر ۴ ساعت
- `instagram.yml` انتشار اینستاگرام
- `nllb-200-test.yml` تست ترجمه (دستی)

سکرت‌های اصلی: `BOT_TOKEN`، کلیدهای مدل‌های هوش مصنوعی، و در صورت نیاز سکرت‌های اینستاگرام.

## فایل‌های وضعیت

این فایل‌ها توسط ربات به‌روز و کامیت می‌شوند؛ دستی ویرایششان نکن:
`sent_news.txt`، `v13_health.json`، `v13_monitor.json`، `v13_rejected_news.json`، `ai_model_health.json`، `instagram_state.json`، فایل‌های `*_history.json`.

## اجرای محلی

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
python run_bot.py
```

فونت‌های Vazirmatn برای طراحی تصویر پست‌ها در ریشه‌ی پروژه قرار دارند.
