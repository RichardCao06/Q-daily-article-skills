"""HTML fallback fetcher.

Fetches a single URL's HTML and extracts a publication date from one of:

  - `<meta property="article:published_time" content="...">`
  - `<time datetime="..." pubdate>` or `<time datetime="...">`
  - `<meta itemprop="datePublished" content="...">`
  - JSON-LD `"datePublished"` field

Title comes from `<title>` or `<meta property="og:title">`.
Summary comes from `<meta property="og:description">` or first `<p>` text.

This fetcher emits AT MOST ONE FetchResult — the page itself, treated as a
single dated article. It's the lowest-quality fetcher in the chain, used
only when RSS / sitemap / API don't apply.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from datetime import datetime, timezone
from typing import Optional

from .base import Fetcher, FetchResult, http_get, in_window


_META_RE = re.compile(
    rb'<meta[^>]+(?:property|name|itemprop)=["\']([^"\']+)["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_META_REVERSE_RE = re.compile(
    rb'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name|itemprop)=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_TIME_RE = re.compile(
    rb'<time[^>]+datetime=["\']([^"\']+)["\']', re.IGNORECASE,
)
_TITLE_RE = re.compile(rb"<title>([^<]+)</title>", re.IGNORECASE | re.DOTALL)
_JSON_LD_RE = re.compile(
    rb'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)


def _all_metas(body: bytes) -> dict[str, str]:
    out: dict[str, str] = {}
    for prop, content in _META_RE.findall(body):
        out[prop.decode("utf-8", errors="ignore").lower()] = content.decode("utf-8", errors="ignore")
    for content, prop in _META_REVERSE_RE.findall(body):
        out.setdefault(prop.decode("utf-8", errors="ignore").lower(), content.decode("utf-8", errors="ignore"))
    return out


def _extract_iso_date(body: bytes, metas: dict[str, str]) -> Optional[str]:
    # 1. OpenGraph article:published_time
    for k in ("article:published_time", "og:article:published_time", "datepublished"):
        v = metas.get(k)
        if v:
            iso = _normalize(v)
            if iso:
                return iso
    # 2. JSON-LD
    for blob in _JSON_LD_RE.findall(body):
        try:
            obj = json.loads(blob.decode("utf-8", errors="ignore"))
        except Exception:
            continue
        cand = _find_json_field(obj, "datePublished")
        if cand:
            iso = _normalize(cand)
            if iso:
                return iso
    # 3. <time datetime="...">
    m = _TIME_RE.search(body)
    if m:
        iso = _normalize(m.group(1).decode("utf-8", errors="ignore"))
        if iso:
            return iso
    return None


def _find_json_field(obj, field: str):
    if isinstance(obj, dict):
        if field in obj:
            return obj[field]
        for v in obj.values():
            r = _find_json_field(v, field)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _find_json_field(v, field)
            if r:
                return r
    return None


def _normalize(s: str) -> Optional[str]:
    s = (s or "").strip()
    if not s:
        return None
    candidates = [s, s.replace("Z", "+00:00")]
    for c in candidates:
        try:
            dt = datetime.fromisoformat(c)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            pass
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s + "T00:00:00Z"
    return None


def _extract_title(body: bytes, metas: dict[str, str]) -> str:
    return (
        metas.get("og:title")
        or metas.get("twitter:title")
        or _decode_match(_TITLE_RE, body)
        or ""
    ).strip()


def _extract_summary(body: bytes, metas: dict[str, str]) -> str:
    s = (
        metas.get("og:description")
        or metas.get("description")
        or metas.get("twitter:description")
        or ""
    ).strip()
    if len(s) > 280:
        s = s[:279] + "…"
    return s


def _decode_match(rx: re.Pattern, body: bytes) -> str:
    m = rx.search(body)
    return m.group(1).decode("utf-8", errors="ignore") if m else ""


class HtmlDatedFetcher(Fetcher):
    """HTML fallback fetcher. Reason codes:

      html:ok            — page has a date in window
      html:fetch_error   — network / DNS / 4xx-5xx fetching the URL
      html:empty_body    — server replied 200 with empty body
      html:no_date       — couldn't extract any published date
      html:out_of_window — date extracted but outside the window
    """
    name = "html_dated"

    def fetch(
        self,
        url: str,
        window_start: str,
        window_end: str,
        cache_for_url: Optional[dict] = None,
        timeout: float = 4.0,
    ) -> tuple[list[FetchResult], dict, str]:
        cache = dict(cache_for_url or {})
        try:
            body, _ = http_get(url, timeout=timeout)
        except Exception:
            return ([], cache, "html:fetch_error")
        if not body:
            return ([], cache, "html:empty_body")

        metas = _all_metas(body)
        published = _extract_iso_date(body, metas)
        if not published:
            return ([], cache, "html:no_date")
        if not in_window(published, window_start, window_end):
            return ([], cache, "html:out_of_window")

        title = _extract_title(body, metas)
        summary = _extract_summary(body, metas)
        result = FetchResult(
            source_url=url,
            title=title or url,
            summary=summary,
            published_at=published,
            content_type="post",
            publisher=urllib.parse.urlparse(url).netloc,
            raw_label=published,
            item_guid=url,
        )
        return ([result], cache, "html:ok")
