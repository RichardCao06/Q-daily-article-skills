"""RSS 2.0 / Atom feed fetcher.

Strategy:
1. If `url` ends in a known feed extension (.xml, .rss, .atom) or contains
   `/feed` / `/rss`, fetch directly.
2. Otherwise fetch the URL as HTML and look for `<link rel="alternate"
   type="application/rss+xml">` or `application/atom+xml`.
3. Common platform-specific shortcuts (YouTube channel URL → feeds URL,
   Reddit subreddit URL → .rss) are applied when detected.

Items are emitted in chronological order with `published_at` ISO-8601 in UTC.
"""

from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

from .base import Fetcher, FetchResult, HttpError, http_get, in_window


# Common feed paths to probe when HTML <link rel="alternate"> isn't declared.
# Capped at 4 high-yield entries — historically /feed catches WordPress, Hugo,
# Ghost, Medium-style; /rss.xml catches custom blogs; /atom.xml catches Jekyll;
# /index.xml catches some static-site generators. More candidates have
# rapidly diminishing returns and large worst-case time cost.
COMMON_FEED_PATHS = (
    "/feed",
    "/rss.xml",
    "/atom.xml",
    "/index.xml",
)


_CHANNEL_ID_RE = re.compile(rb'"channelId":"([A-Za-z0-9_-]+)"')
_CHANNEL_ID_META_RE = re.compile(
    rb'<meta\s+itemprop=["\']channelId["\']\s+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)


_FEED_LINK_RE = re.compile(
    rb'<link[^>]+rel=["\']alternate["\'][^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]*>',
    re.IGNORECASE,
)
_HREF_RE = re.compile(rb'href=["\']([^"\']+)["\']', re.IGNORECASE)


def _likely_feed_url(url: str) -> bool:
    lower = url.lower()
    return (
        lower.endswith((".xml", ".rss", ".atom"))
        or "/feed" in lower
        or "/rss" in lower
        or "atom" in lower
    )


def _resolve_platform_feed(url: str) -> str:
    """Map well-known platform URLs to their RSS endpoint synchronously.

    For YouTube /c/<name> and /@handle URLs that need extra discovery, this
    function returns the original URL — the discovery happens in
    `_resolve_youtube_handle` which makes its own HTTP call.
    """
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/")

    if host.endswith("youtube.com"):
        m = re.match(r"/channel/([A-Za-z0-9_-]+)", path)
        if m:
            return f"https://www.youtube.com/feeds/videos.xml?channel_id={m.group(1)}"

    if host.endswith("reddit.com") and not lower_url_has_rss(url):
        # Reddit RSS lives at <subreddit-or-user>.rss — strip trailing slash
        # so we don't generate ".../sub/.rss" which 404s.
        clean = url.rstrip("/")
        return f"{clean}.rss"

    return url


def _resolve_youtube_handle(url: str, *, timeout: float = 4.0) -> Optional[str]:
    """Resolve a YouTube `/c/<name>` or `/@handle` URL to its channel-ID feed.

    Fetches the channel page HTML and extracts `channelId` from either:
      - `<meta itemprop="channelId" content="UC...">`
      - the inline JSON blob (`"channelId":"UC..."`)

    Returns the feeds URL or None if extraction fails. Uses the module-level
    `http_get` so test mocks on `rss_mod.http_get` take effect.
    """
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path
    if not host.endswith("youtube.com"):
        return None
    if not (path.startswith("/c/") or path.startswith("/@") or path.startswith("/user/")):
        return None
    try:
        body, _ = http_get(url, timeout=timeout)
    except Exception:
        return None
    if not body:
        return None
    m = _CHANNEL_ID_META_RE.search(body)
    if m:
        cid = m.group(1).decode("utf-8", errors="ignore")
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
    m = _CHANNEL_ID_RE.search(body)
    if m:
        cid = m.group(1).decode("utf-8", errors="ignore")
        if cid.startswith("UC"):
            return f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
    return None


def _try_common_feed_paths(seed_url: str, *, per_probe_timeout: float = 3.0) -> Optional[bytes]:
    """Probe common feed paths with a SHORT timeout per candidate.

    Long timeouts here are catastrophic — the watchlist has ~44 jobs that hit
    this path, and 16 candidates × 12s timeout × 44 = ~140 minutes worst case.
    A real feed responds in <1s; if a candidate doesn't resolve in 4s it's
    not a feed.

    Circuit breaker: if the FIRST candidate times out (likely the host itself
    is unreachable from this network or blocked), abandon the whole probe
    instead of running all 16. Sites that 404 specific paths fast still get
    the full sweep.
    """
    parsed = urllib.parse.urlparse(seed_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    base_with_path = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"
    candidates: list[str] = []
    for p in COMMON_FEED_PATHS:
        candidates.append(base_with_path + p)
        candidates.append(base + p)

    seen: set[str] = set()
    timeout_count = 0
    for i, u in enumerate(candidates):
        if u in seen:
            continue
        seen.add(u)
        try:
            body, _ = http_get(u, timeout=per_probe_timeout, retry_on_block=False)
        except HttpError as e:
            # Circuit breaker: if the host is timing out (status -1) on first
            # 2 candidates, give up — host isn't reachable from us.
            if e.status == -1:
                timeout_count += 1
                if timeout_count >= 2:
                    return None
            continue
        except Exception:
            continue
        if not body:
            continue
        head = body[:200].lstrip()
        if head.startswith(b"<?xml") or b"<rss" in head[:100] or b"<feed" in head[:200]:
            return body
    return None


def lower_url_has_rss(url: str) -> bool:
    lower = url.lower()
    return lower.endswith(".rss") or "/feed" in lower


def _discover_feed_in_html(html: bytes, base_url: str) -> Optional[str]:
    m = _FEED_LINK_RE.search(html)
    if not m:
        return None
    href_match = _HREF_RE.search(m.group(0))
    if not href_match:
        return None
    href = href_match.group(1).decode("utf-8", errors="ignore")
    return urllib.parse.urljoin(base_url, href)


def _parse_iso(ts: str) -> Optional[str]:
    """Parse a feed timestamp string and return ISO-8601 UTC (Z-suffixed)."""
    if not ts:
        return None
    ts = ts.strip()
    # RFC 822 (RSS standard)
    try:
        dt = parsedate_to_datetime(ts)
        if dt is not None:
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        pass
    # ISO-8601 (Atom standard) — handle a few common variants
    candidates = [
        ts,
        ts.replace("Z", "+00:00"),
    ]
    for c in candidates:
        try:
            dt = datetime.fromisoformat(c)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            continue
    return None


# Strip XML namespaces so ET.find works without namespace gymnastics.
_NS_RE = re.compile(r"\s?xmlns(:[\w-]+)?=\"[^\"]+\"")


def _parse_feed(body: bytes) -> tuple[str, list[FetchResult]]:
    """Return (publisher_title, items)."""
    text = body.decode("utf-8", errors="replace")
    text = _NS_RE.sub("", text)
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return ("", [])

    items: list[FetchResult] = []
    publisher = ""

    # RSS 2.0
    if root.tag == "rss":
        chan = root.find("channel")
        if chan is None:
            return ("", [])
        publisher = (chan.findtext("title") or "").strip()
        for it in chan.findall("item"):
            link = (it.findtext("link") or "").strip()
            title = (it.findtext("title") or "").strip()
            desc = (it.findtext("description") or "").strip()
            pub = _parse_iso(it.findtext("pubDate") or it.findtext("dc:date") or "")
            guid = (it.findtext("guid") or link).strip()
            if link and pub:
                items.append(FetchResult(
                    source_url=link, title=title, summary=_clean_text(desc),
                    published_at=pub, content_type="post",
                    publisher=publisher, raw_label=(it.findtext("pubDate") or "").strip(),
                    item_guid=guid,
                ))

    # Atom
    elif root.tag == "feed":
        publisher = (root.findtext("title") or "").strip()
        for entry in root.findall("entry"):
            title = (entry.findtext("title") or "").strip()
            content = (entry.findtext("content") or entry.findtext("summary") or "").strip()
            pub = _parse_iso(entry.findtext("published") or entry.findtext("updated") or "")
            guid = (entry.findtext("id") or "").strip()
            link_el = entry.find("link")
            link = link_el.get("href", "").strip() if link_el is not None else ""
            if link and pub:
                items.append(FetchResult(
                    source_url=link, title=title, summary=_clean_text(content),
                    published_at=pub, content_type="post",
                    publisher=publisher,
                    raw_label=(entry.findtext("published") or entry.findtext("updated") or "").strip(),
                    item_guid=guid or link,
                ))

    return (publisher, items)


def _clean_text(html_or_text: str) -> str:
    """Strip HTML tags, normalize whitespace, cap to ~280 chars."""
    txt = re.sub(r"<[^>]+>", " ", html_or_text or "")
    txt = re.sub(r"\s+", " ", txt).strip()
    if len(txt) > 280:
        txt = txt[:277] + "…"
    return txt


# ---------------------------------------------------------------------------


def _looks_like_feed_body(body: bytes) -> bool:
    head = body[:200].lstrip()
    return head.startswith(b"<?xml") or b"<rss" in head[:100] or b"<feed" in head[:200]


class RssFetcher(Fetcher):
    """RSS / Atom fetcher. Reason codes:

      rss:ok                       — items returned
      rss:not_modified             — server replied 304
      rss:no_feed_discovered       — HTML had no <link rel="alternate"> AND no
                                     common feed path returned a parseable body
      rss:fetch_error_<status>     — network / HTTP error fetching seed URL,
                                     status appended (e.g. rss:fetch_error_403,
                                     rss:fetch_error_timeout, rss:fetch_error_dns)
      rss:feed_fetch_error_<status>— discovered feed URL unreachable
      rss:not_a_feed               — body returned but isn't RSS/Atom XML
      rss:feed_empty               — XML parsed but contains 0 items
      rss:no_items_in_window       — items exist but none in window
      rss:all_already_seen         — in-window items all already cached
      rss:youtube_handle_unresolved — could not extract channelId from /c|@/<name> page
    """
    name = "rss"

    def fetch(
        self,
        url: str,
        window_start: str,
        window_end: str,
        cache_for_url: Optional[dict] = None,
        timeout: float = 4.0,
    ) -> tuple[list[FetchResult], dict, str]:
        cache = dict(cache_for_url or {})
        last_seen = set(cache.get("last_seen_guids", []))

        feed_url = _resolve_platform_feed(url)
        body: Optional[bytes] = None
        headers: dict = {}

        # YouTube /c/<name> and /@handle: do an extra HTTP step to resolve
        # the channel ID, then map to feeds endpoint.
        if "youtube.com" in feed_url and "/feeds/" not in feed_url:
            resolved = _resolve_youtube_handle(feed_url, timeout=timeout)
            if resolved:
                feed_url = resolved
            elif _is_youtube_handle_url(feed_url):
                return ([], cache, "rss:youtube_handle_unresolved")

        # Path 1: URL already looks like a feed → fetch directly
        if _likely_feed_url(feed_url):
            try:
                extra = {}
                if cache.get("etag"):
                    extra["If-None-Match"] = cache["etag"]
                body, headers = http_get(feed_url, timeout=timeout, extra_headers=extra)
            except HttpError as e:
                return ([], cache, f"rss:fetch_error_{_status_label(e.status)}")
            except Exception:
                return ([], cache, "rss:fetch_error_unknown")
        else:
            # Path 2: try HTML discovery
            try:
                seed_body, _ = http_get(feed_url, timeout=timeout)
            except HttpError as e:
                return ([], cache, f"rss:fetch_error_{_status_label(e.status)}")
            except Exception:
                return ([], cache, "rss:fetch_error_unknown")
            discovered = _discover_feed_in_html(seed_body, feed_url)
            if discovered:
                try:
                    body, headers = http_get(discovered, timeout=timeout)
                    feed_url = discovered
                except HttpError as e:
                    return ([], cache, f"rss:feed_fetch_error_{_status_label(e.status)}")
                except Exception:
                    return ([], cache, "rss:feed_fetch_error_unknown")
            else:
                # Path 3: probe common feed paths (short timeout per candidate)
                probe_body = _try_common_feed_paths(feed_url)
                if probe_body is None:
                    return ([], cache, "rss:no_feed_discovered")
                body = probe_body

        if not body:
            return ([], cache, "rss:not_modified")
        if not _looks_like_feed_body(body):
            return ([], cache, "rss:not_a_feed")

        new_etag = headers.get("etag", "")
        publisher, all_items = _parse_feed(body)
        if not all_items:
            return ([], cache, "rss:feed_empty")

        kept: list[FetchResult] = []
        new_guids: list[str] = []
        any_in_window = False
        for it in all_items:
            if not in_window(it.published_at, window_start, window_end):
                continue
            any_in_window = True
            if it.item_guid and it.item_guid in last_seen:
                continue
            kept.append(it)
            if it.item_guid:
                new_guids.append(it.item_guid)

        merged_guids = (new_guids + list(last_seen))[:200]
        cache["last_seen_guids"] = merged_guids
        cache["etag"] = new_etag
        cache["last_publisher"] = publisher
        cache["last_feed_url"] = feed_url

        if kept:
            return (kept, cache, "rss:ok")
        if not any_in_window:
            return ([], cache, "rss:no_items_in_window")
        return ([], cache, "rss:all_already_seen")


def _is_youtube_handle_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    return parsed.netloc.endswith("youtube.com") and (
        parsed.path.startswith("/c/")
        or parsed.path.startswith("/@")
        or parsed.path.startswith("/user/")
    )


def _status_label(status: int) -> str:
    """Map HttpError.status to a short, log-friendly suffix."""
    if status == -1:
        return "timeout"
    if status == 0:
        return "dns"
    if status == -2:
        return "url"
    return str(status)
