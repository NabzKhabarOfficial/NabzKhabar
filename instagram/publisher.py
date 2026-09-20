"""Safe Instagram publisher for NABZ.

Publishing is intentionally disabled unless dry_run is false and the required
environment variables are present. Uses Meta's official Graph API.
"""

from __future__ import annotations

import os
import time
from typing import Any

import requests

GRAPH_BASE = "https://graph.facebook.com"


class InstagramPublishError(RuntimeError):
    pass


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise InstagramPublishError(f"Missing required environment variable: {name}")
    return value


def create_media(image_url: str, caption: str, api_version: str = "v23.0") -> str:
    user_id = _require("INSTAGRAM_USER_ID")
    token = _require("INSTAGRAM_ACCESS_TOKEN")

    response = requests.post(
        f"{GRAPH_BASE}/{api_version}/{user_id}/media",
        data={"image_url": image_url, "caption": caption, "access_token": token},
        timeout=30,
    )
    response.raise_for_status()
    data: dict[str, Any] = response.json()
    creation_id = data.get("id")
    if not creation_id:
        raise InstagramPublishError(f"Instagram did not return a creation id: {data}")
    return creation_id


def wait_until_ready(creation_id: str, api_version: str = "v23.0", attempts: int = 12) -> None:
    token = _require("INSTAGRAM_ACCESS_TOKEN")

    for _ in range(attempts):
        response = requests.get(
            f"{GRAPH_BASE}/{api_version}/{creation_id}",
            params={"fields": "status_code,status", "access_token": token},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        status = data.get("status_code")
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise InstagramPublishError(data.get("status") or "Instagram media processing failed")
        time.sleep(5)

    raise InstagramPublishError("Instagram media container did not become ready in time")


def publish(creation_id: str, api_version: str = "v23.0") -> str:
    user_id = _require("INSTAGRAM_USER_ID")
    token = _require("INSTAGRAM_ACCESS_TOKEN")

    response = requests.post(
        f"{GRAPH_BASE}/{api_version}/{user_id}/media_publish",
        data={"creation_id": creation_id, "access_token": token},
        timeout=30,
    )
    response.raise_for_status()
    data: dict[str, Any] = response.json()
    media_id = data.get("id")
    if not media_id:
        raise InstagramPublishError(f"Instagram did not return a media id: {data}")
    return media_id


def publish_image(image_url: str, caption: str, dry_run: bool = True) -> dict[str, Any]:
    if dry_run:
        return {"published": False, "dry_run": True, "image_url": image_url}

    creation_id = create_media(image_url, caption)
    wait_until_ready(creation_id)
    media_id = publish(creation_id)
    return {"published": True, "media_id": media_id}
