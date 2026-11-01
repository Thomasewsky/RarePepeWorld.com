#!/usr/bin/env python3
"""Download already-verified TokenScan artwork into the persistent local cache."""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import tools.artwork_audit as audit  # noqa: E402

PROGRESS = audit.CACHE_ROOT / "tokenscan-cache-progress.jsonl"
LOGGER = logging.getLogger("tokenscan_cache")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_progress() -> dict[str, dict]:
    completed = {}
    if not PROGRESS.exists():
        return completed
    for line in PROGRESS.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
            if item.get("cache_status") == "VERIFIED" and item.get("asset"):
                path = audit.STATIC_ROOT / item.get("local_filename", "")
                decoded = audit.verify_local(path)
                if decoded and decoded["sha256"] == item.get("sha256"):
                    completed[item["asset"]] = item
        except (json.JSONDecodeError, OSError, TypeError):
            continue
    return completed


def append_progress(record: dict) -> None:
    PROGRESS.parent.mkdir(parents=True, exist_ok=True)
    with PROGRESS.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def refresh_reports(records: dict[str, dict]) -> dict:
    old = json.loads((audit.REPORT_ROOT / "artwork-audit.json").read_text(encoding="utf-8"))
    rows = [{"asset": item["asset"], "series": item.get("series"),
             "image_file_name": item.get("legacy_local_filename", ""),
             "_official": item.get("classification") == "official"} for item in old["assets"]]
    return audit.build_reports(rows, records, old["summary"]["sitemap"],
                               old["summary"].get("assets_completed_this_run", 0), 0, "complete")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    old = json.loads((audit.MANIFEST_PATH).read_text(encoding="utf-8"))
    records = old.get("assets", {})
    sitemap = old.get("sitemap", {})
    resumed = read_progress()
    for asset, cached in resumed.items():
        if asset in records and records[asset].get("source_provider", "").startswith("tokenscan_"):
            records[asset].update({k: cached[k] for k in
                                   ("local_filename", "sha256", "image_format", "mime_type", "width", "height",
                                    "byte_length", "cache_status", "cached_at") if k in cached})

    pending = [asset for asset, record in sorted(records.items())
               if record.get("classification") == "official"
               and record.get("verification_status") == "VERIFIED"
               and record.get("source_provider", "").startswith("tokenscan_")]
    session = __import__("requests").Session()
    session.headers.update({"User-Agent": audit.USER_AGENT})
    allowed, policy = audit.robots_allowed(session, audit.TOKENSCAN, audit.TOKENSCAN + "/img/cards/")
    if not allowed:
        LOGGER.error("TokenScan policy does not allow the image path: %s", policy)
        return 2

    completed = 0
    paused = False
    try:
        for index, asset in enumerate(pending, 1):
            record = records[asset]
            cached_path = audit.STATIC_ROOT / record.get("local_filename", "") if record.get("local_filename") else None
            if cached_path and (decoded := audit.verify_local(cached_path)):
                if decoded["sha256"] == record.get("sha256"):
                    record["cache_status"] = "VERIFIED"
                    continue
            if not cached_path and record.get("sha256") and record.get("image_format") in audit.ALLOWED_FORMATS:
                expected_relative = audit.safe_cache_filename(asset, record["image_format"], record["sha256"])
                expected_path = audit.STATIC_ROOT / expected_relative
                expected = audit.verify_local(expected_path)
                if expected and expected["sha256"] == record["sha256"]:
                    record.update(local_filename=expected_relative, cache_status="VERIFIED", cached_at=now())
                    append_progress({k: record[k] for k in
                                     ("asset", "local_filename", "image_format", "mime_type", "width", "height",
                                      "byte_length", "sha256", "cache_status", "cached_at")})
                    continue
            if record.get("cache_status") == "VERIFIED" and record.get("local_filename"):
                # A missing or changed file is re-fetched below; never trust only a manifest flag.
                record.pop("cache_status", None)

            url = record.get("source_url", "")
            if not url.startswith(audit.TOKENSCAN + "/img/cards/"):
                record["cache_status"] = "UNKNOWN"
                record["cache_error"] = "No verified TokenScan source URL in audit manifest"
                append_progress({"asset": asset, "cache_status": "UNKNOWN", "cache_error": record["cache_error"]})
                continue
            try:
                response = None
                for attempt in range(audit.RETRIES):
                    response = audit.get_response(url, session, "tokenscan.io")
                    if response.status_code < 500 or attempt + 1 == audit.RETRIES:
                        break
                    response.close()
                    time.sleep(min(2 ** attempt, 20))
            except audit.SourcePaused as exc:
                record["cache_status"] = "UNKNOWN"
                record["cache_error"] = str(exc)
                append_progress({"asset": asset, "cache_status": "UNKNOWN", "cache_error": str(exc)})
                paused = True
                LOGGER.error("Paused by TokenScan access/rate limit: %s", exc)
                break
            except Exception as exc:
                record["cache_status"] = "UNKNOWN"
                record["cache_error"] = f"{type(exc).__name__}: {exc}"
                append_progress({"asset": asset, "cache_status": "UNKNOWN", "cache_error": record["cache_error"]})
                LOGGER.warning("Cache request failed for %s: %s", asset, exc)
                continue

            try:
                checked = audit.checked_image(response)
                status = response.status_code
                content_type = response.headers.get("Content-Type", "")
            finally:
                response.close()
            if not checked:
                record["cache_status"] = "UNAVAILABLE" if status in (404, 410, 451) else "INVALID_OR_UNKNOWN"
                record["cache_error"] = f"HTTP {status}; Content-Type {content_type}"
                append_progress({"asset": asset, "cache_status": record["cache_status"],
                                 "cache_error": record["cache_error"]})
                LOGGER.warning("Did not cache %s: %s", asset, record["cache_error"])
                continue

            prior_hash = record.get("sha256", "")
            filename = audit.persist_cached_original(asset, checked)
            record.update(local_filename=filename, image_format=checked["format"],
                          mime_type=checked["mime_type"], width=checked["width"],
                          height=checked["height"], byte_length=checked["byte_length"],
                          sha256=checked["sha256"], cache_status="VERIFIED", cached_at=now(),
                          cache_error="")
            if prior_hash and prior_hash != checked["sha256"]:
                record["previous_audit_sha256"] = prior_hash
            append_progress({k: record[k] for k in
                             ("asset", "local_filename", "image_format", "mime_type", "width", "height",
                              "byte_length", "sha256", "cache_status", "cached_at")})
            completed += 1
            if completed % 20 == 0:
                audit.write_manifest(records, sitemap)
                LOGGER.info("Cached %d/%d pending TokenScan images", completed, len(pending))
    finally:
        audit.write_manifest(records, sitemap)
        session.close()

    summary = refresh_reports(records)
    LOGGER.info("Local archive: %d/%d official; %d missing DB images; %d unknown; %.2f GiB image bytes",
                summary["locally_cached_official_artwork"], summary["database_assets_matching_official_sitemap"],
                summary["missing_from_all_checked_sources"], summary["unknown_due_to_network_or_access_errors"],
                summary["local_cache_image_bytes"] / (1024 ** 3))
    return 1 if paused else 0


if __name__ == "__main__":
    raise SystemExit(main())
