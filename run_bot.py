import re

import main
import graphics_patch
import v13_engine

# Final presentation layer: use the channel handle consistently.
_original_send_message = main.send_message
_original_send_photo = main.send_photo
_original_send_video = main.send_video

def _caption(text):
    if not text:
        return text
    return str(text).replace("#نبض_خبر", "@NabzKhabarOfficial")

def send_message(text):
    return _original_send_message(_caption(text))

def send_photo(path, caption):
    return _original_send_photo(path, _caption(caption))

def send_video(path, caption):
    return _original_send_video(path, _caption(caption))

main.send_message = send_message
main.send_photo = send_photo
main.send_video = send_video

if __name__ == "__main__":
    main.main()
