import v13_standalone as main
import v13_media_branding
import v13_ai_router

# V13 is the only news runtime. main.py, v12_engine.py,
# v13_engine.py and graphics_patch.py are not imported here.
# Branding/media fixes and the free AI router are installed before the engine starts.
v13_media_branding.install(main)
v13_ai_router.install(main)

import education

if __name__ == "__main__":
    main.main()
    education.main.send_message = main.send_message
    education.post_daily_education()
