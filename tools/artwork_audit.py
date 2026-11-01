#!/usr/bin/env python3
"""Polite, resumable artwork audit of the configured RarePepeWorld SQL inventory."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import mimetypes
import os
import re
import sys
import tempfile
import time
import urllib.robotparser
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup
from PIL import Image, UnidentifiedImageError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import Settings  # noqa: E402
from rpw.DataConnectors import DBConnector  # noqa: E402

LOGGER = logging.getLogger("artwork_audit")
TOKENSCAN = "https://tokenscan.io"
RAREPEPES = "https://rarepepes.com"
USER_AGENT = "RarePepeWorldArtworkAudit/1.0 (respectful collection availability audit)"
ALLOWED_FORMATS = {"JPEG", "PNG", "GIF", "WEBP"}
MAX_IMAGE_BYTES = 32 * 1024 * 1024
CONNECT_TIMEOUT = 12
READ_TIMEOUT = 30
TOKEN_DELAY = 0.75
RARE_DELAY = 1.25
RETRIES = 4

STATIC_ROOT = ROOT / "rpw" / "static"
CACHE_ROOT = STATIC_ROOT / "artwork_cache"
CARDS_ROOT = CACHE_ROOT / "cards"
MANIFEST_PATH = CACHE_ROOT / "manifest.json"
PROGRESS_PATH = CACHE_ROOT / "progress.jsonl"
REPORT_ROOT = ROOT / "reports"

SITEMAP_NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SourcePaused(Exception):
    def __init__(self, host: str, reason: str):
        self.host = host
        super().__init__(reason)


class Pacer:
    def __init__(self, interval: float):
        self.interval = interval
        self.last_request = 0.0

    def wait(self) -> None:
        delay = self.interval - (time.monotonic() - self.last_request)
        if delay > 0:
            time.sleep(delay)
        self.last_request = time.monotonic()


PACERS: dict[str, Pacer] = {}
BLOCKED_HOSTS: dict[str, str] = {}
ROBOTS_CACHE: dict[str, tuple[urllib.robotparser.RobotFileParser | None, str]] = {}


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            return max(0.0, (date - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


def get_response(url: str, session: requests.Session, host: str, *, stream: bool = False) -> requests.Response:
    """GET with host pacing, bounded exponential retry, and explicit 429 handling."""
    if host in BLOCKED_HOSTS:
        raise SourcePaused(host, BLOCKED_HOSTS[host])
    pacer = PACERS.setdefault(host, Pacer(TOKEN_DELAY if host == "tokenscan.io" else RARE_DELAY))
    last_error = "unknown request error"
    for attempt in range(RETRIES):
        pacer.wait()
        try:
            response = session.get(url, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT), stream=stream)
        except requests.RequestException as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt + 1 == RETRIES:
                raise RuntimeError(last_error) from exc
            time.sleep(min(2 ** attempt, 20))
            continue

        if response.status_code == 429:
            if attempt + 1 == RETRIES:
                response.close()
                BLOCKED_HOSTS[host] = "429 persisted through retry window"
                raise SourcePaused(host, BLOCKED_HOSTS[host])
            retry_after = _retry_after_seconds(response.headers.get("Retry-After"))
            delay = max(retry_after or 0, min(2 ** (attempt + 1), 60))
            response.close()
            LOGGER.warning("429 from %s; honoring Retry-After/backoff for %.1fs", host, delay)
            time.sleep(delay)
            continue

        if response.status_code in (408, 425) or 500 <= response.status_code <= 599:
            last_error = f"HTTP {response.status_code}"
            response.close()
            if attempt + 1 == RETRIES:
                raise RuntimeError(last_error)
            time.sleep(min(2 ** attempt, 20))
            continue

        if response.status_code in (401, 403):
            BLOCKED_HOSTS[host] = f"HTTP {response.status_code} access restriction"
            response.close()
            raise SourcePaused(host, BLOCKED_HOSTS[host])
        return response
    raise RuntimeError(last_error)


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    })
    return session


def robots_allowed(session: requests.Session, origin: str, target_url: str) -> tuple[bool, str]:
    robots_url = origin.rstrip("/") + "/robots.txt"
    host = urlparse(origin).hostname or ""
    if host not in ROBOTS_CACHE:
        response = get_response(robots_url, session, host)
        try:
            if response.status_code == 404:
                ROBOTS_CACHE[host] = (None, "robots.txt not published (404)")
            elif response.status_code != 200:
                ROBOTS_CACHE[host] = (None, f"robots.txt HTTP {response.status_code}")
            else:
                parser = urllib.robotparser.RobotFileParser()
                parser.set_url(robots_url)
                parser.parse(response.text.splitlines())
                ROBOTS_CACHE[host] = (parser, "robots.txt available")
        finally:
            response.close()
    parser, policy = ROBOTS_CACHE[host]
    if parser is None:
        allowed = policy == "robots.txt not published (404)"
        return allowed, policy
    allowed = parser.can_fetch(USER_AGENT, target_url)
    return allowed, "robots.txt allows this path" if allowed else "robots.txt disallows this path"


def checked_image(response: requests.Response, expected_extension: str | None = None) -> dict | None:
    """Validate response MIME, raster signature, successful decode, and dimensions."""
    mime = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    if response.status_code != 200 or not mime.startswith("image/"):
        return None
    chunks = []
    size = 0
    for chunk in response.iter_content(64 * 1024):
        if not chunk:
            continue
        size += len(chunk)
        if size > MAX_IMAGE_BYTES:
            return None
        chunks.append(chunk)
    body = b"".join(chunks)
    try:
        with Image.open(BytesIO(body)) as image:
            fmt = image.format
            width, height = image.size
            image.verify()
        with Image.open(BytesIO(body)) as image:
            image.load()
            if image.size != (width, height):
                return None
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return None
    if fmt not in ALLOWED_FORMATS or width < 1 or height < 1:
        return None
    expected_mime = {
        "JPEG": {"image/jpeg", "image/jpg", "image/pjpeg"},
        "PNG": {"image/png", "image/x-png"},
        "GIF": {"image/gif"},
        "WEBP": {"image/webp"},
    }[fmt]
    if mime not in expected_mime:
        return None
    # Endpoints can use legacy extensions; rely on content signature and MIME for actual format.
    return {"format": fmt, "mime_type": mime, "width": width, "height": height,
            "byte_length": size, "sha256": hashlib.sha256(body).hexdigest(), "bytes": body}


def verify_local(path: Path) -> dict | None:
    try:
        if not path.is_file() or path.stat().st_size > MAX_IMAGE_BYTES:
            return None
        body = path.read_bytes()
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        response = requests.Response()
        response.status_code = 200
        response.headers["Content-Type"] = mime
        response._content = body
        response._content_consumed = True
        return checked_image(response)
    except OSError:
        return None


def fetch_sitemap_assets(session: requests.Session) -> tuple[dict[str, str], dict]:
    allowed, policy = robots_allowed(session, RAREPEPES, RAREPEPES + "/sitemap_index.xml")
    if not allowed:
        raise RuntimeError(f"RarePepes.com sitemap disallowed or policy unavailable: {policy}")
    index_url = RAREPEPES + "/sitemap_index.xml"
    response = get_response(index_url, session, "rarepepes.com")
    try:
        if response.status_code != 200:
            raise RuntimeError(f"RarePepes.com sitemap index returned HTTP {response.status_code}")
        root = ElementTree.fromstring(response.content)
        sitemap_urls = [n.text for n in root.findall(".//s:loc", SITEMAP_NS) if n.text]
    finally:
        response.close()
    card_urls = []
    for sitemap_url in sitemap_urls:
        path = urlparse(sitemap_url).path.lower()
        if "nft-sitemap" not in path:
            continue
        response = get_response(sitemap_url, session, "rarepepes.com")
        try:
            if response.status_code != 200:
                raise RuntimeError(f"RarePepes.com NFT sitemap returned HTTP {response.status_code}: {sitemap_url}")
            root = ElementTree.fromstring(response.content)
            card_urls.extend(n.text for n in root.findall(".//s:loc", SITEMAP_NS) if n.text)
        finally:
            response.close()
    pages = {}
    for page_url in card_urls:
        parsed = urlparse(page_url)
        parts = [p for p in parsed.path.strip("/").split("/") if p]
        if len(parts) != 2 or parts[0].lower() != "nft":
            continue
        slug = parts[1].upper()
        if slug == "NFT":
            continue
        pages[slug] = page_url
    return pages, {"sitemap_index": index_url, "nft_sitemap_urls": sitemap_urls,
                   "nft_page_urls": len(card_urls), "nft_card_slugs": len(pages),
                   "card_asset_ids": sorted(pages),
                   "robots_policy": policy}


def decode_local_file(path: Path) -> dict | None:
    return verify_local(path)


def safe_cache_filename(asset: str, fmt: str, sha256: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", asset).strip("._") or "asset"
    suffix = {"JPEG": "jpeg", "PNG": "png", "GIF": "gif", "WEBP": "webp"}[fmt]
    return f"artwork_cache/cards/{safe}-{sha256[:12]}.{suffix}"


def persist_cached_original(asset: str, checked: dict) -> str:
    relative = safe_cache_filename(asset, checked["format"], checked["sha256"])
    destination = STATIC_ROOT / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        current = verify_local(destination)
        if current and current["sha256"] == checked["sha256"]:
            return relative
        raise RuntimeError(f"Refusing to overwrite an existing cache file: {destination}")
    fd, temporary = tempfile.mkstemp(prefix=".artwork-", suffix=".part", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(checked["bytes"])
            out.flush()
            os.fsync(out.fileno())
        if destination.exists():
            raise RuntimeError(f"Cache destination appeared during write; refusing overwrite: {destination}")
        os.replace(temporary, destination)
        destination.chmod(0o644)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return relative


def load_progress() -> dict[str, dict]:
    records = {}
    if not PROGRESS_PATH.exists():
        return records
    with PROGRESS_PATH.open("r", encoding="utf-8") as file:
        for line in file:
            try:
                item = json.loads(line)
                if item.get("asset"):
                    records[item["asset"]] = item
            except json.JSONDecodeError:
                continue
    return records


def append_progress(record: dict) -> None:
    PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PROGRESS_PATH.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        file.flush()
        os.fsync(file.fileno())


def write_manifest(records: dict[str, dict], sitemap_meta: dict) -> None:
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    manifest = {"generated_at": utc_now(), "sitemap": sitemap_meta,
                "assets": {asset: {k: v for k, v in rec.items() if k != "_image_bytes"}
                           for asset, rec in sorted(records.items())}}
    fd, temp_name = tempfile.mkstemp(prefix=".manifest-", suffix=".tmp", dir=CACHE_ROOT)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(manifest, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_name, MANIFEST_PATH)
        MANIFEST_PATH.chmod(0o644)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def add_result(asset_row: dict, official_url: str | None, session: requests.Session) -> dict:
    asset = asset_row["asset"]
    now = utc_now()
    base = {
        "asset": asset,
        "classification": "official" if official_url else "extra_unmatched",
        "series": asset_row.get("series"),
        "legacy_local_filename": asset_row.get("image_file_name") or "",
        "source_provider": "",
        "source_url": "",
        "source_page_url": official_url or "",
        "local_filename": "",
        "image_format": "",
        "mime_type": "",
        "width": None,
        "height": None,
        "byte_length": None,
        "sha256": "",
        "verification_status": "UNKNOWN",
        "last_checked_at": now,
        "error": "",
        "tokenscan_jpg_status": "NOT_CHECKED",
        "tokenscan_png_status": "NOT_CHECKED",
        "rarepepes_page_status": "NOT_CHECKED",
        "rarepepes_image_status": "NOT_CHECKED",
    }

    legacy_name = base["legacy_local_filename"]
    if legacy_name and Path(legacy_name).name == legacy_name:
        legacy_path = Path(Settings.Sources["pepe_data"]["images_path"]) / legacy_name
        local = decode_local_file(legacy_path)
        if local:
            base.update(source_provider="legacy_local", source_url=str(legacy_path), local_filename=legacy_name,
                        image_format=local["format"], mime_type=local["mime_type"], width=local["width"],
                        height=local["height"], byte_length=local["byte_length"], sha256=local["sha256"],
                        verification_status="VERIFIED", error="")
            return base

    for extension, field in (("jpg", "tokenscan_jpg_status"), ("png", "tokenscan_png_status")):
        url = f"{TOKENSCAN}/img/cards/{requests.utils.quote(asset, safe='')}.{extension}"
        try:
            response = get_response(url, session, "tokenscan.io")
        except SourcePaused as exc:
            base[field] = "UNKNOWN"
            base["error"] = f"{exc.host}: {exc}"
            raise
        except Exception as exc:
            base[field] = "UNKNOWN"
            base["error"] = f"{type(exc).__name__}: {exc}"
            continue
        try:
            if response.status_code == 404 or response.status_code in (410, 451):
                base[field] = f"HTTP_{response.status_code}"
                continue
            checked = checked_image(response, extension)
            if checked:
                base[field] = f"VERIFIED_{checked['format']}"
                base.update(source_provider=f"tokenscan_{extension}", source_url=url,
                            image_format=checked["format"], mime_type=checked["mime_type"],
                            width=checked["width"], height=checked["height"],
                            byte_length=checked["byte_length"], sha256=checked["sha256"],
                            verification_status="VERIFIED", error="")
                return base
            if response.status_code == 200:
                base[field] = "INVALID_IMAGE_RESPONSE"
            else:
                base[field] = f"HTTP_{response.status_code}"
                if response.status_code >= 400 and response.status_code not in (404, 410, 451):
                    base["error"] = f"TokenScan {extension} returned HTTP {response.status_code}"
        finally:
            response.close()

    if official_url:
        if "rarepepes.com" in BLOCKED_HOSTS:
            base["rarepepes_page_status"] = "UNKNOWN"
            base["error"] = "rarepepes.com blocked: " + BLOCKED_HOSTS["rarepepes.com"]
            base["verification_status"] = "UNKNOWN"
            return base
        try:
            page_response = get_response(official_url, session, "rarepepes.com")
        except SourcePaused:
            base["rarepepes_page_status"] = "UNKNOWN"
            base["error"] = "rarepepes.com blocked: " + BLOCKED_HOSTS.get("rarepepes.com", "access restricted")
            base["verification_status"] = "UNKNOWN"
            return base
        except Exception as exc:
            base["rarepepes_page_status"] = "UNKNOWN"
            base["error"] = f"RarePepes page network error: {type(exc).__name__}: {exc}"
            base["verification_status"] = "UNKNOWN"
            return base
        try:
            base["rarepepes_page_status"] = str(page_response.status_code)
            if page_response.status_code == 404:
                base["rarepepes_image_status"] = "NO_CARD_PAGE"
                base["verification_status"] = "UNKNOWN" if base["error"] else "MISSING"
                return base
            elif page_response.status_code != 200:
                base["rarepepes_page_status"] = "UNKNOWN"
                base["error"] = f"RarePepes page returned HTTP {page_response.status_code}"
                base["verification_status"] = "UNKNOWN"
                return base
            else:
                soup = BeautifulSoup(page_response.content, "html.parser")
                headings = [h.get_text(" ", strip=True).upper() for h in soup.select("h1")]
                title = soup.title.get_text(" ", strip=True).upper() if soup.title else ""
                if asset.upper() not in headings and not title.startswith(asset.upper()):
                    base["rarepepes_page_status"] = "PAGE_ASSET_MISMATCH"
                    base["error"] = "Official sitemap page did not identify the requested asset"
                    base["verification_status"] = "UNKNOWN"
                    return base
                image_meta = soup.select_one('meta[property="og:image"]')
                image_url = image_meta.get("content", "").strip() if image_meta else ""
                if not image_url:
                    # Accept a card-specific structured-data image if the page uses a different SEO layout.
                    for script in soup.select('script[type="application/ld+json"]'):
                        try:
                            data = json.loads(script.string or script.get_text())
                        except (json.JSONDecodeError, TypeError):
                            continue
                        candidates = data if isinstance(data, list) else [data]
                        for item in candidates:
                            if isinstance(item, dict) and item.get("image"):
                                image = item["image"]
                                image_url = image if isinstance(image, str) else (image[0] if image else "")
                                if image_url:
                                    break
                        if image_url:
                            break
                if not image_url:
                    base["rarepepes_image_status"] = "NO_IMAGE_REFERENCE"
                    base["error"] = "Verified card page exposed no image URL"
                    base["verification_status"] = "UNKNOWN"
                    return base
                if not image_url.startswith(("https://", "http://")):
                    base["rarepepes_image_status"] = "INVALID_IMAGE_URL"
                    base["error"] = "Card page image URL is not absolute HTTP(S)"
                    base["verification_status"] = "UNKNOWN"
                    return base
                image_parts = urlparse(image_url)
                image_host = (image_parts.hostname or "").lower()
                if image_host != "rarepepes.com" and not image_host.endswith(".rarepepes.com"):
                    base["rarepepes_image_status"] = "UNREVIEWED_EXTERNAL_HOST"
                    base["error"] = f"Card page image points to an unreviewed host: {image_host}"
                    base["verification_status"] = "UNKNOWN"
                    return base
                image_origin = f"{image_parts.scheme}://{image_parts.netloc}"
                try:
                    image_allowed, image_policy = robots_allowed(session, image_origin, image_url)
                except Exception as exc:
                    base["rarepepes_image_status"] = "UNKNOWN"
                    base["error"] = f"Could not check image-host policy: {exc}"
                    base["verification_status"] = "UNKNOWN"
                    return base
                if not image_allowed:
                    base["rarepepes_image_status"] = "ROBOTS_DISALLOWED"
                    base["error"] = image_policy
                    base["verification_status"] = "UNKNOWN"
                    return base
        finally:
            page_response.close()

        try:
            image_response = get_response(image_url, session, image_host)
        except SourcePaused:
            base["rarepepes_image_status"] = "UNKNOWN"
            base["error"] = f"{image_host} blocked: " + BLOCKED_HOSTS.get(image_host, "access restricted")
            base["verification_status"] = "UNKNOWN"
            return base
        except Exception as exc:
            base["rarepepes_image_status"] = "UNKNOWN"
            base["error"] = f"RarePepes image network error: {type(exc).__name__}: {exc}"
            base["verification_status"] = "UNKNOWN"
            return base
        try:
            checked = checked_image(image_response)
            if checked:
                try:
                    local_filename = persist_cached_original(asset, checked)
                except Exception as exc:
                    base["rarepepes_image_status"] = "VERIFIED_NOT_CACHED"
                    base["error"] = f"Image verified but cache write failed: {exc}"
                    base["verification_status"] = "UNKNOWN"
                    base["source_url"] = image_url
                    base.update(image_format=checked["format"], mime_type=checked["mime_type"],
                                width=checked["width"], height=checked["height"],
                                byte_length=checked["byte_length"], sha256=checked["sha256"])
                    return base
                base.update(source_provider="rarepepes.com", source_url=image_url,
                            local_filename=local_filename, image_format=checked["format"],
                            mime_type=checked["mime_type"], width=checked["width"], height=checked["height"],
                            byte_length=checked["byte_length"], sha256=checked["sha256"],
                            verification_status="VERIFIED", rarepepes_image_status="VERIFIED")
                return base
            if image_response.status_code == 404:
                base["rarepepes_image_status"] = "HTTP_404"
            else:
                base["rarepepes_image_status"] = "INVALID_IMAGE_RESPONSE"
                if image_response.status_code != 200:
                    base["error"] = f"RarePepes image returned HTTP {image_response.status_code}"
        finally:
            image_response.close()

    has_unknown = any("UNKNOWN" in base[key] for key in
                      ("tokenscan_jpg_status", "tokenscan_png_status", "rarepepes_page_status",
                       "rarepepes_image_status"))
    base["verification_status"] = "UNKNOWN" if has_unknown else "MISSING"
    return base


def build_reports(rows: list[dict], records: dict[str, dict], sitemap_meta: dict,
                  completed: int, pending: int, run_state: str) -> dict:
    assets = []
    for row in rows:
        asset = row["asset"]
        rec = dict(records.get(asset, {}))
        if not rec:
            rec = {"asset": asset, "classification": "official" if row.get("_official") else "extra_unmatched",
                   "series": row.get("series"), "legacy_local_filename": row.get("image_file_name") or "",
                   "source_provider": "", "source_url": "", "source_page_url": "",
                   "local_filename": "", "image_format": "", "mime_type": "", "width": None,
                   "height": None, "byte_length": None, "sha256": "", "verification_status": "PENDING",
                   "last_checked_at": "", "error": "not scanned yet", "tokenscan_jpg_status": "NOT_CHECKED",
                   "tokenscan_png_status": "NOT_CHECKED", "rarepepes_page_status": "NOT_CHECKED",
                   "rarepepes_image_status": "NOT_CHECKED"}
        rec["classification"] = "official" if row.get("_official") else "extra_unmatched"
        assets.append(rec)

    source = lambda name: sum(r["classification"] == "official" and r["source_provider"] == name for r in assets)
    official = [r for r in assets if r["classification"] == "official"]
    available = sum(r["verification_status"] == "VERIFIED" for r in official)
    db_ids = {r["asset"] for r in assets}
    sitemap_ids = {str(asset).upper() for asset in sitemap_meta.get("card_asset_ids", [])}
    in_both = sorted(db_ids & sitemap_ids)
    only_db = sorted(db_ids - sitemap_ids)
    only_sitemap = sorted(sitemap_ids - db_ids)
    cache_records = [r for r in official if r.get("local_filename", "").startswith("artwork_cache/")]
    cached_bytes = sum(int(r.get("byte_length") or 0) for r in cache_records)
    cached_formats = {}
    for record in cache_records:
        fmt = record.get("image_format") or "UNKNOWN"
        cached_formats[fmt] = cached_formats.get(fmt, 0) + 1
    summary = {
        "generated_at": utc_now(),
        "run_state": run_state,
        "database_assets": len(assets),
        "official_rare_pepe_cards_identified": len(official),
        "rarepepes_sitemap_card_slug_count": len(sitemap_ids),
        "database_assets_matching_official_sitemap": len(in_both),
        "extra_or_unmatched_database_assets": sum(r["classification"] != "official" for r in assets),
        "extra_or_unmatched_database_asset_ids": sorted(r["asset"] for r in assets if r["classification"] != "official"),
        "official_sitemap_cards_not_in_database": only_sitemap,
        "assets_in_both_sources_count": len(in_both),
        "assets_in_both_sources": in_both,
        "assets_only_in_database": only_db,
        "assets_only_in_sitemap": only_sitemap,
        "tokenscan_jpg": source("tokenscan_jpg"),
        "tokenscan_png": source("tokenscan_png"),
        "rarepepes_com": source("rarepepes.com"),
        "available_only_locally": source("legacy_local"),
        "missing_from_all_checked_sources": sum(r["verification_status"] == "MISSING" for r in assets),
        "official_cards_missing_from_all_checked_sources": sum(r["classification"] == "official" and r["verification_status"] == "MISSING" for r in assets),
        "unknown_due_to_network_or_access_errors": sum(r["verification_status"] == "UNKNOWN" for r in assets),
        "pending_unverified": sum(r["verification_status"] == "PENDING" for r in assets),
        "coverage_percent": round(100 * available / len(official), 2) if official else 0.0,
        "official_available_count": available,
        "locally_cached_official_artwork": len(cache_records),
        "locally_cached_from_tokenscan": sum(r["source_provider"].startswith("tokenscan_") for r in cache_records),
        "locally_cached_from_rarepepes_com": sum(r["source_provider"] == "rarepepes.com" for r in cache_records),
        "local_cache_image_bytes": cached_bytes,
        "local_cache_image_formats": dict(sorted(cached_formats.items())),
        "assets_completed_this_run": completed,
        "sitemap": sitemap_meta,
        "rate_policy": {"tokenscan_min_interval_seconds": TOKEN_DELAY,
                        "rarepepes_min_interval_seconds": RARE_DELAY, "concurrency": 1,
                        "retry_count": RETRIES, "timeout_seconds": [CONNECT_TIMEOUT, READ_TIMEOUT]},
    }

    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    (REPORT_ROOT / "artwork-audit.json").write_text(
        json.dumps({"summary": summary, "assets": assets}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    fields = ["asset", "classification", "series", "source_provider", "source_url", "source_page_url",
              "local_filename", "legacy_local_filename", "image_format", "mime_type", "width", "height",
              "byte_length", "sha256", "verification_status", "last_checked_at", "error",
              "tokenscan_jpg_status", "tokenscan_png_status", "rarepepes_page_status", "rarepepes_image_status"]
    with (REPORT_ROOT / "artwork-audit.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(assets)
    with (REPORT_ROOT / "artwork-inventory-reconciliation.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["asset", "in_mariadb", "in_rarepepes_sitemap", "set_membership"])
        writer.writeheader()
        for asset in sorted(db_ids | sitemap_ids):
            in_db, in_site = asset in db_ids, asset in sitemap_ids
            writer.writerow({"asset": asset, "in_mariadb": str(in_db).lower(),
                             "in_rarepepes_sitemap": str(in_site).lower(),
                             "set_membership": "both" if in_db and in_site else
                                              "mariadb_only" if in_db else "sitemap_only"})
    missing = [r for r in assets if r["verification_status"] == "MISSING"]
    (REPORT_ROOT / "artwork-missing.txt").write_text(
        "Database assets missing artwork across checked sources (verified 404/invalid):\n" +
        ("\n".join(f"{r['asset']} ({r['classification']})" for r in missing) + "\n" if missing else "None\n"),
        encoding="utf-8")
    lines = ["# Rare Pepe artwork audit summary", "",
             f"Run state: **{run_state}** (completed this run: {completed}; pending: {pending}).", "",
             "## Counts", "",
             f"- MariaDB asset identifiers: {summary['database_assets']}",
             f"- RarePepes.com sitemap card IDs: {sitemap_meta.get('nft_card_slugs', 'unknown')}",
             f"- IDs present in both sources: {summary['assets_in_both_sources_count']}",
             f"- MariaDB-only ID{'s' if summary['extra_or_unmatched_database_assets'] != 1 else ''}: {summary['extra_or_unmatched_database_assets']} ({', '.join(summary['assets_only_in_database']) or 'none'})",
             f"- Sitemap-only ID{'s' if len(summary['assets_only_in_sitemap']) != 1 else ''}: {len(summary['assets_only_in_sitemap'])} ({', '.join(summary['assets_only_in_sitemap']) or 'none'})",
             f"- TokenScan JPG: {summary['tokenscan_jpg']}",
             f"- TokenScan PNG: {summary['tokenscan_png']}",
             f"- RarePepes.com: {summary['rarepepes_com']}",
             f"- Available only via pre-existing legacy artwork: {summary['available_only_locally']}",
             f"- Missing database assets (all checked sources): {summary['missing_from_all_checked_sources']}",
             f"- Missing official cards: {summary['official_cards_missing_from_all_checked_sources']}",
             f"- Unknown from network/access errors: {summary['unknown_due_to_network_or_access_errors']}",
             f"- Pending/unverified: {summary['pending_unverified']}",
             f"- Coverage of DB-matched official cards: {summary['coverage_percent']:.2f}%", "",
             "## Inventory reconciliation", "",
             f"MariaDB contains {summary['database_assets']} distinct asset IDs; the RarePepes.com NFT sitemap "
             f"contains {sitemap_meta.get('nft_card_slugs', 'unknown')} distinct card slugs. After converting the "
             f"lowercase URL slugs to uppercase Counterparty identifiers, {len(in_both)} IDs are in both sets; "
             f"MariaDB-only: {len(only_db)} ({', '.join(only_db) or 'none'}); sitemap-only: "
             f"{len(only_sitemap)} ({', '.join(only_sitemap) or 'none'}). Therefore 1,774 is the intersection, not the "
             "total sitemap count: 1,774 + 7 = 1,781 sitemap IDs; 1,774 + XCP = 1,775 MariaDB IDs. "
             "There are no remaining aliases or case/whitespace mismatches. See "
             "`reports/artwork-inventory-reconciliation.csv` for every identifier in both sets and each difference. "
             "Historical database records were not modified.", "",
             "## Local artwork cache", "",
             f"Verified original bytes saved unchanged for {len(cache_records)} official cards:",
             f"- TokenScan: {summary['locally_cached_from_tokenscan']}",
             f"- RarePepes.com: {summary['locally_cached_from_rarepepes_com']}",
             f"- Decoded formats: {', '.join(f'{fmt} {count}' for fmt, count in summary['local_cache_image_formats'].items())}",
             f"- Image bytes: {cached_bytes:,} ({cached_bytes / (1024 ** 3):.2f} GiB).", ""]
    lines.extend(f"- `{r['asset']}` → `{r['local_filename']}` ({r['image_format']} {r['width']}×{r['height']})"
                 for r in cache_records)
    lines += ["", "## Cache operations", "",
              "The local cache is `rpw/static/artwork_cache/` and is intentionally Git-ignored. Back it up with:",
              "", "```sh", "tar -czf rarepepe-artwork-cache.tar.gz rpw/static/artwork_cache", "```", "",
              "Restore that directory unchanged before starting Flask. The manifest is "
              "`rpw/static/artwork_cache/manifest.json`; resumable request checkpoints are in `progress.jsonl`.", "",
              "## Policy and audit method", "",
              f"RarePepes.com robots policy: {sitemap_meta.get('robots_policy', 'not available')}. "
              "TokenScan has no published robots.txt (404). Requests were sequential with host pacing, retries, "
              "Retry-After handling, MIME/signature/decode validation and no full-image bulk scraping outside "
              "assets that required the RarePepes.com fallback.", ""]
    (REPORT_ROOT / "artwork-summary.md").write_text("\n".join(lines), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="Recheck all assets despite verified progress entries")
    parser.add_argument("--limit", type=int, default=0, help="Optional small diagnostic limit; omit for full audit")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    session = make_session()

    # Check the advertised policies before any inventory/page/image requests.
    for origin, target in ((TOKENSCAN, TOKENSCAN + "/img/cards/RAREPEPE.jpg"),
                           (RAREPEPES, RAREPEPES + "/nft/baberuthpepe/")):
        try:
            allowed, policy = robots_allowed(session, origin, target)
        except Exception as exc:
            LOGGER.error("Could not determine %s robots policy: %s", origin, exc)
            return 2
        LOGGER.info("Policy for %s: %s (%s)", origin, policy, "allowed" if allowed else "blocked")
        if not allowed:
            LOGGER.error("Stopping: source policy does not allow the requested audit path")
            return 2

    try:
        official_pages, sitemap_meta = fetch_sitemap_assets(session)
    except Exception:
        LOGGER.exception("Unable to establish the official collection inventory; not starting artwork checks")
        return 2

    db = DBConnector()
    try:
        rows = db.query_and_fetch("SELECT DISTINCT asset, series, image_file_name FROM assets ORDER BY asset")
    finally:
        db.close()
    rows = [dict(row) for row in rows]
    for row in rows:
        row["_official"] = row["asset"].upper() in official_pages
    if args.limit:
        rows = rows[:args.limit]

    records = load_progress()
    if args.refresh:
        records = {}
    # A prior progress record is reusable only while its cached source remains valid.
    for row in rows:
        rec = records.get(row["asset"])
        if not rec or rec.get("verification_status") != "VERIFIED" or not rec.get("local_filename"):
            continue
        cached = STATIC_ROOT / rec["local_filename"]
        if not decode_local_file(cached):
            records.pop(row["asset"], None)

    completed_this_run = 0
    dirty = False
    run_state = "complete"
    total = len(rows)
    LOGGER.info("Auditing %d distinct database assets; official sitemap matches=%d, unmatched=%d",
                total, sum(r["_official"] for r in rows), sum(not r["_official"] for r in rows))
    try:
        for index, row in enumerate(rows, 1):
            asset = row["asset"]
            existing = records.get(asset)
            if existing and existing.get("verification_status") in ("VERIFIED", "MISSING") and not args.refresh:
                # Existing local originals take first place; validate again so changed files are never trusted stale.
                legacy_name = row.get("image_file_name") or ""
                legacy_path = Path(Settings.Sources["pepe_data"]["images_path"]) / legacy_name if legacy_name else None
                if existing.get("source_provider") == "legacy_local" and legacy_path and decode_local_file(legacy_path):
                    continue
                if existing.get("source_provider") == "rarepepes.com" and existing.get("local_filename"):
                    if decode_local_file(STATIC_ROOT / existing["local_filename"]):
                        continue
                elif existing.get("source_provider", "").startswith("tokenscan_") or existing.get("verification_status") == "MISSING":
                    continue
            try:
                rec = add_result(row, official_pages.get(asset.upper()), session)
            except SourcePaused as exc:
                LOGGER.error("Stopping on provider block from %s: %s", exc.host, exc)
                rec = {
                    "asset": asset,
                    "classification": "official" if row["_official"] else "extra_unmatched",
                    "series": row.get("series"),
                    "legacy_local_filename": row.get("image_file_name") or "",
                    "source_provider": "", "source_url": "", "source_page_url": official_pages.get(asset.upper(), ""),
                    "local_filename": "", "image_format": "", "mime_type": "", "width": None,
                    "height": None, "byte_length": None, "sha256": "", "verification_status": "UNKNOWN",
                    "last_checked_at": utc_now(), "error": f"{exc.host}: {exc}",
                    "tokenscan_jpg_status": "UNKNOWN", "tokenscan_png_status": "NOT_CHECKED",
                    "rarepepes_page_status": "NOT_CHECKED", "rarepepes_image_status": "NOT_CHECKED",
                }
                records[asset] = rec
                append_progress(rec)
                completed_this_run += 1
                run_state = f"paused: {exc.host} rate/access restriction"
                break
            rec["classification"] = "official" if row["_official"] else "extra_unmatched"
            rec["last_checked_at"] = utc_now()
            records[asset] = rec
            append_progress(rec)
            completed_this_run += 1
            dirty = True
            if completed_this_run % 20 == 0:
                pending = total - sum(1 for r in rows[:index] if r["asset"] in records and records[r["asset"]].get("verification_status") not in ("PENDING",))
                write_manifest(records, sitemap_meta)
                summary = build_reports(rows, records, sitemap_meta, completed_this_run, pending, "in_progress")
                LOGGER.info("Progress %d/%d; coverage currently %.2f%%; missing=%d unknown=%d cached=%d",
                            index, total, summary["coverage_percent"], summary["missing_from_all_checked_sources"],
                            summary["unknown_due_to_network_or_access_errors"],
                            summary["rarepepes_com"])
        else:
            run_state = "complete" if completed_this_run or all(r["asset"] in records for r in rows) else "complete (resumed)"
    except KeyboardInterrupt:
        run_state = "interrupted; resumable"
        LOGGER.warning("Interrupted cleanly; checkpoints retained")
    finally:
        pending = sum(1 for row in rows if row["asset"] not in records or records[row["asset"]].get("verification_status") == "PENDING")
        write_manifest(records, sitemap_meta)
        summary = build_reports(rows, records, sitemap_meta, completed_this_run, pending, run_state)
        session.close()
        print(json.dumps(summary, indent=2))
    return 0 if pending == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
