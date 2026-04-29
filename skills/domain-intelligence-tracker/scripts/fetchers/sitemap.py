"""Sitemap.xml fetcher.

Fetches `<root>/sitemap.xml` (and follows sitemap-index files), filters
URLs by `<lastmod>` falling inside the time window, and emits one
`FetchResult` per matching URL.

Note: a sitemap entry doesn't carry a title or summary — only the URL and
last-modified date. We emit `title=""` / `summary=""` and rely on the
executor to mark these as `needs_enrichment: true` so the human (or a
follow-up `enrich.py` step) can fill them in.
"""

from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Optional

from .base import Fetcher, FetchResult, http_get, in_window


_NS_RE = re.compile(r"\s?xmlns(:[\w-]+)?=\"[^\"]+\"")


def _strip_ns(text: str) -> str:
    return _NS_RE.sub("", text)


def _candidate_sitemap_urls(url: str) -> list[str]:
    parsed = urllib.parse.urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    out = [
        f"{base}/sitemap.xml",
        f"{base}/sitemap_index.xml",
        f"{base}/sitemap.xml.gz",
        f"{base}/wp-sitemap.xml",
    ]
    # If user passed a sitemap URL directly, try it first
    if url.lower().endswith((".xml", ".xml.gz")):
        out.insert(0, url)
    return out


def _parse_sitemap(body: bytes) -> tuple[list[str], list[tuple[str, str]]]:
    """Return (sub_sitemap_urls, [(url, lastmod), ...])."""
    text = _strip_ns(body.decode("utf-8", errors="replace"))
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return ([], [])

    if root.tag == "sitemapindex":
        subs = [el.findtext("loc", "").strip() for el in root.findall("sitemap")]
        return ([s for s in subs if s], [])
    if root.tag == "urlset":
        urls: list[tuple[str, str]] = []
        for url_el in root.findall("url"):
            loc = (url_el.findtext("loc") or "").strip()
            lastmod = (url_el.findtext("lastmod") or "").strip()
            if loc:
                urls.append((loc, lastmod))
        return ([], urls)
    return ([], [])


class SitemapFetcher(Fetcher):
    """Sitemap.xml fetcher. Reason codes:

      sitemap:ok                  — items returned
      sitemap:not_found           — no sitemap.xml at any candidate path
      sitemap:empty               — sitemap parsed but contains 0 URLs
      sitemap:no_lastmod          — entries exist but none carry <lastmod>
      sitemap:no_items_in_window  — entries with lastmod exist but none in window
      sitemap:all_already_seen    — in-window URLs all in cache
    """
    name = "sitemap"

    def fetch(
        self,
        url: str,
        window_start: str,
        window_end: str,
        cache_for_url: Optional[dict] = None,
        # Sitemap fetcher tries 4 candidate URLs per host. With timeout=8 each,
        # a hung host costs 32s, which exceeds the executor's 15s per-job cap.
        # Keep this at 4s so a hung host is rejected fast and the chain falls
        # through to the next fetcher within budget.
        timeout: float = 4.0,
    ) -> tuple[list[FetchResult], dict, str]:
        cache = dict(cache_for_url or {})

        body: Optional[bytes] = None
        sitemap_url = ""
        host_timed_out = False
        for candidate in _candidate_sitemap_urls(url):
            # Circuit breaker: if the host's first candidate timed out, give up
            # on remaining candidates immediately — the host is unreachable
            # from us and trying 3 more candidates will just burn budget.
            if host_timed_out:
                break
            try:
                body, _ = http_get(candidate, timeout=timeout)
                if body:
                    sitemap_url = candidate
                    break
            except Exception as e:  # noqa: BLE001
                # Detect timeout (HttpError.status == -1) to trigger early-exit
                if hasattr(e, "status") and getattr(e, "status", 0) == -1:
                    host_timed_out = True
                continue
        if not body:
            return ([], cache, "sitemap:not_found")

        sub_urls, leaf_urls = _parse_sitemap(body)
        for sub in sub_urls[:10]:
            try:
                sub_body, _ = http_get(sub, timeout=timeout)
                _, sub_leaves = _parse_sitemap(sub_body)
                leaf_urls.extend(sub_leaves)
            except Exception:
                continue
        if not leaf_urls:
            return ([], cache, "sitemap:empty")

        kept: list[FetchResult] = []
        last_seen = set(cache.get("last_seen_guids", []))
        new_guids: list[str] = []
        any_lastmod = False
        any_in_window = False
        for loc, lastmod in leaf_urls:
            if not lastmod:
                continue
            any_lastmod = True
            if not in_window(lastmod, window_start, window_end):
                continue
            any_in_window = True
            if loc in last_seen:
                continue
            kept.append(FetchResult(
                source_url=loc,
                title="",
                summary="",
                published_at=lastmod[:10] + "T00:00:00Z" if len(lastmod) == 10 else lastmod,
                content_type="post",
                publisher="",
                raw_label=lastmod,
                item_guid=loc,
            ))
            new_guids.append(loc)

        cache["last_seen_guids"] = (new_guids + list(last_seen))[:200]
        cache["last_sitemap_url"] = sitemap_url

        if kept:
            return (kept, cache, "sitemap:ok")
        if not any_lastmod:
            return ([], cache, "sitemap:no_lastmod")
        if not any_in_window:
            return ([], cache, "sitemap:no_items_in_window")
        return ([], cache, "sitemap:all_already_seen")
