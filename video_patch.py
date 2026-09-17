"""Minimal Telegram video metadata guard.

Keeps the existing v11 video-first/fallback flow intact while making sure
Telegram receives a real duration for videos that can be inspected locally.
Invalid/zero-duration files are rejected so the existing photo fallback can
run instead of publishing a broken video.
"""

import json
import os
import subprocess

import main


_ORIGINAL_SEND_VIDEO = main.send_video


def _probe_video(path):
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=duration,width,height",
                "-show_entries", "format=duration",
                "-of", "json",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

        if result.returncode != 0:
            print(f"Video probe failed: {result.stderr[:300]}")
            return None

        data = json.loads(result.stdout or "{}")
        streams = data.get("streams") or []
        stream = streams[0] if streams else {}
        fmt = data.get("format") or {}

        raw_duration = stream.get("duration") or fmt.get("duration")
        duration = float(raw_duration) if raw_duration else 0.0

        width = int(stream.get("width") or 0)
        height = int(stream.get("height") or 0)

        return {
            "duration": duration,
            "width": width,
            "height": height,
        }

    except Exception as exc:
        print(f"Video probe error: {exc}")
        return None


def send_video(path, caption):
    if not path or not os.path.exists(path):
        return False

    info = _probe_video(path)

    if not info or info["duration"] <= 0:
        print("VIDEO REJECTED: zero/unknown duration; using existing fallback")
        return False

    duration = max(1, int(round(info["duration"])))

    try:
        with open(path, "rb") as video:
            response = main.SESSION.post(
                main.telegram_api("sendVideo"),
                data={
                    "chat_id": main.CHANNEL_ID,
                    "caption": caption,
                    "supports_streaming": "true",
                    "duration": str(duration),
                    "width": str(info["width"]) if info["width"] else "",
                    "height": str(info["height"]) if info["height"] else "",
                },
                files={"video": video},
                timeout=120,
            )

        if response.ok:
            print(f"VIDEO PUBLISHED ({duration}s)")
            return True

        print(
            f"sendVideo failed: {response.status_code} "
            f"{response.text[:500]}"
        )

    except Exception as exc:
        print(f"sendVideo error: {exc}")

    return False


main.send_video = send_video
