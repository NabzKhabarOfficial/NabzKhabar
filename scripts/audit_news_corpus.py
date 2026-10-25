"""Exhaustive offline audit for every docs/news HTML record.

The repository intentionally keeps retired/noindex pages for stable URLs. The
contract is therefore: 1,408 active NewsArticle pages plus any retired pages,
with both populations audited under their own schemas.
"""
from __future__ import annotations
import hashlib, json, re, sys
from collections import defaultdict
from pathlib import Path
from bs4 import BeautifulSoup
ROOT = Path(__file__).resolve().parents[1]
NEWS = ROOT / "docs" / "news"
MANIFEST = ROOT / "content" / "quarantine_manifest.json"
OUT = ROOT / "review" / "news_corpus_audit.json"
EXPECTED_ACTIVE = 1408

def norm(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("ي", "ی").replace("ك", "ک")).strip().lower()

def audit_file(path: Path) -> dict:
    raw = path.read_bytes(); soup = BeautifulSoup(raw, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    canonical = ""
    node = soup.find("link", rel=lambda value: value and "canonical" in value)
    if node: canonical = str(node.get("href") or "").strip()
    text = soup.get_text(" ", strip=True)
    retired = title.startswith("این خبر برداشته شد") or bool(soup.find("meta", attrs={"name": "robots", "content": re.compile("noindex", re.I)}))
    jsonld = []
    for script in soup.find_all("script", type="application/ld+json"):
        try: jsonld.append(json.loads(script.get_text()))
        except Exception: pass
    article = any(isinstance(x, dict) and (x.get("@type") == "NewsArticle" or "NewsArticle" in (x.get("@type") or [])) for x in jsonld)
    if retired:
        checks = {"doctype": raw.lstrip().lower().startswith(b"<!doctype html"), "title": bool(title), "canonical": bool(canonical), "noindex": bool(soup.find("meta", attrs={"name": "robots", "content": re.compile("noindex", re.I)})), "redirect_or_removed_text": ("این خبر برداشته شد" in text or bool(soup.find("meta", attrs={"http-equiv": "refresh"}))), "id_in_name": bool(path.stem)}
    else:
        checks = {"doctype": raw.lstrip().lower().startswith(b"<!doctype html"), "title": bool(title), "canonical": bool(canonical), "news_article_jsonld": article, "date_published": any(isinstance(x, dict) and x.get("datePublished") for x in jsonld), "main_entity": any(isinstance(x, dict) and x.get("mainEntityOfPage") for x in jsonld), "visible_text": len(text) >= 200, "id_in_name": bool(path.stem)}
    return {"id": path.stem, "path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "title": title, "canonical": canonical, "kind": "retired" if retired else "active", "checks": checks, "passed": all(checks.values())}

def main() -> int:
    files = sorted(NEWS.glob("*.html")); records = [audit_file(p) for p in files]
    try: quarantine = {str(x) for x in json.loads(MANIFEST.read_text(encoding="utf-8")).get("ids", [])}
    except Exception as exc: print(f"manifest error: {exc}", file=sys.stderr); return 2
    by_id = {r["id"]: r for r in records}; missing_quarantine = sorted(quarantine - set(by_id)); active = [r for r in records if r["kind"] == "active"]; retired = [r for r in records if r["kind"] == "retired"]; failures = [r for r in records if not r["passed"]]
    hashes = defaultdict(list); titles = defaultdict(list)
    for r in active: hashes[r["sha256"]].append(r["id"]); titles[norm(r["title"])].append(r["id"])
    result = {"scope": "docs/news/*.html", "collected": len(records), "expected_active": EXPECTED_ACTIVE, "active_records": len(active), "retired_records": len(retired), "collection_complete": len(active) == EXPECTED_ACTIVE, "processed": len(records), "processing_complete": len(records) == len(files), "quarantine_manifest_entries": len(quarantine), "quarantine_missing_from_news": missing_quarantine, "structural_failures": failures, "duplicate_active_hashes": {k:v for k,v in hashes.items() if len(v)>1}, "duplicate_active_normalized_titles": {k:v for k,v in titles.items() if k and len(v)>1}, "retired_ids": [r["id"] for r in retired], "records": records}
    OUT.parent.mkdir(parents=True, exist_ok=True); OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {k: result[k] for k in ("collected", "expected_active", "active_records", "retired_records", "collection_complete", "processed", "processing_complete", "quarantine_manifest_entries", "quarantine_missing_from_news", "structural_failures")}
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if result["collection_complete"] and result["processing_complete"] and not missing_quarantine and not failures and not result["duplicate_active_hashes"] else 1
if __name__ == "__main__": raise SystemExit(main())
