import v13_standalone as main
import education

# V13 is the only news runtime. main.py, v12_engine.py,
# v13_engine.py and graphics_patch.py are not imported here.

if __name__ == "__main__":
    main.main()
    education.main.send_message = main.send_message
    education.post_daily_education()
