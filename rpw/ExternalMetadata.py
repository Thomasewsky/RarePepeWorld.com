from collections import OrderedDict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import http.client
import ipaddress
import json
import re
import socket
import ssl
import threading
import time
from urllib.parse import quote, urljoin, urlsplit


_CACHE_LOCK = threading.RLock()
_DESCRIPTION_CACHE = OrderedDict()
_PRICE_CACHE = OrderedDict()
_DESCRIPTION_TTL = 24 * 60 * 60
_FAILURE_TTL = 5 * 60
_PRICE_TTL = 45 * 60
_CACHE_LIMIT = 2048
_MAX_METADATA_BYTES = 64 * 1024
_MAX_PRICE_BYTES = 256 * 1024
_ASSET_RE = re.compile(r"^[A-Z0-9._-]{1,32}$")


def _now():
    return time.time()


def _timestamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _remember(cache, key, value):
    cache[key] = value
    cache.move_to_end(key)
    while len(cache) > _CACHE_LIMIT:
        cache.popitem(last=False)


def _resolve_public(host, port):
    if not host or host.lower() == "localhost" or host.lower().endswith((".localhost", ".local", ".internal")):
        raise ValueError("non-public host")
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    ips = []
    for item in addresses:
        ip = ipaddress.ip_address(item[4][0].split("%", 1)[0])
        if not ip.is_global:
            raise ValueError("non-public address")
        if str(ip) not in ips:
            ips.append(str(ip))
    if not ips:
        raise ValueError("host did not resolve")
    return ips


class _PinnedHTTP(http.client.HTTPConnection):
    def __init__(self, host, port, ip, timeout):
        super().__init__(host, port, timeout=timeout)
        self._ip = ip

    def connect(self):
        self.sock = socket.create_connection((self._ip, self.port), self.timeout)


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, port, ip, timeout):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self._ip = ip

    def connect(self):
        raw = socket.create_connection((self._ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


def _fetch_public_json(url, max_bytes):
    current = url
    for redirect_count in range(3):
        parts = urlsplit(current)
        scheme = parts.scheme.lower()
        if scheme not in ("http", "https") or parts.username or parts.password:
            raise ValueError("unsupported URL")
        port = parts.port or (443 if scheme == "https" else 80)
        if port != (443 if scheme == "https" else 80):
            raise ValueError("unsupported port")
        host = parts.hostname
        ips = _resolve_public(host, port)
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        connection_class = _PinnedHTTPS if scheme == "https" else _PinnedHTTP
        connection = connection_class(host, port, ips[0], timeout=2.5)
        try:
            connection.request("GET", path, headers={"Host": host, "Accept": "application/json", "User-Agent": "RarePepeWorld/1.0 metadata resolver"})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader("Location")
                response.read(1024)
                if not location or redirect_count >= 2:
                    raise ValueError("redirect limit")
                current = urljoin(current, location)
                continue
            if response.status != 200:
                raise ValueError("upstream status")
            content_type = (response.getheader("Content-Type") or "").lower()
            if not ("json" in content_type or "text/plain" in content_type or not content_type):
                raise ValueError("not JSON content type")
            length = response.getheader("Content-Length")
            if length and int(length) > max_bytes:
                raise ValueError("response too large")
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise ValueError("response too large")
            parsed = json.loads(body.decode("utf-8-sig"))
            if not isinstance(parsed, dict):
                raise ValueError("JSON root is not an object")
            return parsed
        finally:
            connection.close()
    raise ValueError("redirect limit")


def _description_url(description):
    candidate = (description or "").strip()
    if not candidate or len(candidate) > 2048:
        return None
    if not re.match(r"^https?://", candidate, re.I):
        if not re.match(r"^[a-z0-9.-]+\.[a-z]{2,}/", candidate, re.I):
            return None
        candidate = "https://" + candidate
    parts = urlsplit(candidate)
    if not parts.hostname or not parts.path.lower().endswith((".json", ".json/")):
        return None
    if parts.scheme.lower() not in ("http", "https"):
        return None
    return candidate


def _useful_plain_description(description):
    text = (description or "").strip()
    if not text or len(text) > 4096 or _description_url(text):
        return ""
    if re.fullmatch(r"[0-9a-fA-F]{32,128}", text):
        return ""
    if text.lower().startswith(("javascript:", "data:")):
        return ""
    return text


def resolve_description(asset, raw_description):
    fallback = _useful_plain_description(raw_description)
    asset = str(asset or "")
    source_url = _description_url(raw_description)
    if not source_url or not _ASSET_RE.fullmatch(asset):
        return fallback
    now = _now()
    with _CACHE_LOCK:
        cached = _DESCRIPTION_CACHE.get(asset)
        if cached and cached[0] > now:
            return cached[1] or fallback
    result = ""
    try:
        payload = _fetch_public_json(source_url, _MAX_METADATA_BYTES)
        if payload.get("asset") == asset:
            description = payload.get("description")
            if isinstance(description, str):
                result = description.strip()[:4096]
    except Exception:
        result = ""
    with _CACHE_LOCK:
        _remember(_DESCRIPTION_CACHE, asset, (now + (_DESCRIPTION_TTL if result else _FAILURE_TTL), result))
    return result or fallback


def _valid_values(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("estimated_value"), dict):
        return {}
    values = {}
    for currency in ("btc", "usd", "xcp"):
        raw = payload["estimated_value"].get(currency)
        if isinstance(raw, (str, int, float)) and not isinstance(raw, bool):
            try:
                amount = Decimal(str(raw))
            except (InvalidOperation, ValueError):
                continue
            if amount.is_finite() and amount > 0:
                values[currency] = str(raw)
    return values


def get_estimated_value(asset):
    asset = str(asset or "")
    unavailable = {"available": False, "values": {}, "fetched_at": None, "stale": False}
    if not _ASSET_RE.fullmatch(asset):
        return unavailable
    now = _now()
    with _CACHE_LOCK:
        cached = _PRICE_CACHE.get(asset)
        if cached and cached[0] > now:
            return dict(cached[1])
        stale = dict(cached[1]) if cached and cached[1].get("available") else None
        if cached and not cached[1].get("available") and cached[0] > now:
            return dict(cached[1])
    try:
        url = "https://tokenscan.io/api/asset/" + quote(asset, safe="")
        payload = _fetch_public_json(url, _MAX_PRICE_BYTES)
        if payload.get("asset") != asset:
            raise ValueError("asset identifier mismatch")
        values = _valid_values(payload)
        if not values:
            result = dict(stale) if stale else unavailable
            if stale:
                result["stale"] = True
            ttl = _FAILURE_TTL
        else:
            result = {"available": True, "values": values, "fetched_at": _timestamp(now), "stale": False}
            ttl = _PRICE_TTL
    except Exception:
        result = stale if stale else unavailable
        if stale:
            result["stale"] = True
        ttl = _FAILURE_TTL
    with _CACHE_LOCK:
        _remember(_PRICE_CACHE, asset, (now + ttl, result))
    return dict(result)


def verified_directory_url(candidate):
    candidate = (candidate or "").strip()
    if candidate:
        try:
            parts = urlsplit(candidate)
            if (parts.scheme.lower() in ("http", "https") and
                    parts.hostname and parts.hostname.lower() in ("rarepepedirectory.com", "www.rarepepedirectory.com") and
                    not parts.username and not parts.password):
                return candidate
        except ValueError:
            pass
    return "https://rarepepedirectory.com/"
