import sys

import v13_standalone as main
import v13_media_branding
import v13_ai_router
import v13_argos_translate
import v13_content_enhancer
import v13_ad_filter
import v13_intelligence
import v13_freshness_rescue

# V13 is the only news runtime. Obsolete legacy engines and patches were removed.
# Branding/media fixes, the free AI router, and automatic content enrichment
# are installed on the V13 runtime before the engine starts.
v13_media_branding.install(main)
v13_ai_router.install(main)
v13_argos_translate.install(main)
v13_content_enhancer.install(main, v13_ai_router)
v13_ad_filter.install(main)
v13_intelligence.install(main)
v13_freshness_rescue.install(main)

import education
import car_prices
import weather


if __name__ == "__main__":
    news_failed = False

    try:
        main.main()
    except Exception as exc:
        news_failed = True
        print(f"NEWS RUNTIME ERROR: {exc}", flush=True)

    try:
        education.main.send_message = main.send_message
        education.post_daily_education()
    except Exception as exc:
        print(f"EDUCATION ERROR: {exc}", flush=True)

    try:
        # Car prices are an independent daily board, so they must use their
        # own Telegram sender rather than the V13 news language gate.
        car_prices.main()
    except Exception as exc:
        print(f"CAR PRICES ERROR: {exc}", flush=True)

    try:
        # Weather is an independent daily board, just like car prices.
        weather.main()
    except Exception as exc:
        print(f"WEATHER ERROR: {exc}", flush=True)

    if news_failed:
        sys.exit(1)
