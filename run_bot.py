import v13_standalone as main
import v13_media_branding

# V13 is the only news runtime. main.py, v12_engine.py,
# v13_engine.py and graphics_patch.py are not imported here.
# Branding/media fixes are installed before the engine starts.
v13_media_branding.install(main)

import education

if __name__ == "__main__":
    main.main()
    education.main.send_message = main.send_message
    education.post_daily_education()
