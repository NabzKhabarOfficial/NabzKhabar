"""Validate and select the two-month Story calendar without publishing by default."""
from __future__ import annotations
import argparse, json
from datetime import date
from pathlib import Path
from .content import build_caption, validate_caption
from .dedupe import content_key

ROOT = Path(__file__).parent
CALENDAR = ROOT / "story_calendar.json"

def load_calendar():
    data = json.loads(CALENDAR.read_text(encoding="utf-8"))
    stories = data.get("stories", [])
    assert data.get("days") == len(stories), "calendar day count mismatch"
    assert len(stories) == len({x["slot_id"] for x in stories}), "duplicate slot_id"
    assert len(stories) == len({x["event_key"] for x in stories}), "duplicate event_key"
    assert all(len(x.get("frames", [])) == 3 for x in stories), "every Story needs three frames"
    keys = [content_key(x["frames"][0]["text"], event_key=x["event_key"]) for x in stories]
    assert len(keys) == len(set(keys)), "duplicate content key"
    return data

def check():
    data = load_calendar()
    for item in data["stories"]:
        caption = build_caption(item["frames"][0]["text"], item["frames"][1]["text"], "NABZ")
        ok, reason = validate_caption(caption)
        assert ok, f"{item['slot_id']}: {reason}"
    print(f"Instagram Stories calendar: OK ({data['days']} days, {data['days'] * 3} frames)")

def due():
    data = load_calendar()
    today = date.today().isoformat()
    matches = [x for x in data["stories"] if x["publish_date"] == today and x.get("status") == "planned"]
    print(json.dumps({"date": today, "due": matches}, ensure_ascii=False))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--due", action="store_true")
    args = parser.parse_args()
    if args.due: due()
    else: check()
