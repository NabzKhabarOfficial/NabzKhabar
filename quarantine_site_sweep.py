"""Remove quarantined news pages from public indexes without deleting history."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "content" / "quarantine_manifest.json"
DOCS = ROOT / "docs"
ITEMS = DOCS / "items.json"


def run() -> int:
    try:
        ids = {str(x).strip() for x in json.loads(MANIFEST.read_text(encoding="utf-8")).get("ids", []) if str(x).strip()}
    except Exception as exc:
        raise RuntimeError(f"quarantine manifest unavailable: {type(exc).__name__}") from None
    if not ids:
        return 0
    changed = 0
    for item_id in ids:
        page = DOCS / "news" / f"{item_id}.html"
        if not page.exists():
            continue
        page.write_text("""<!doctype html><html lang=\"fa\" dir=\"rtl\"><head><meta charset=\"utf-8\"><meta name=\"robots\" content=\"noindex,nofollow\"><meta http-equiv=\"refresh\" content=\"0;url=../index.html\"></head><body><h1>این خبر برداشته شد</h1><p>این مطلب از نبض خبر حذف شده است.</p></body></html>""", encoding="utf-8")
        changed += 1
    if ITEMS.exists():
        try:
            data = json.loads(ITEMS.read_text(encoding="utf-8"))
            if isinstance(data, list):
                kept = [x for x in data if not isinstance(x, dict) or str(x.get("id") or "") not in ids]
                if len(kept) != len(data):
                    ITEMS.write_text(json.dumps(kept, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
                    changed += len(data) - len(kept)
        except Exception:
            pass
    return changed
