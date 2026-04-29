"""Fetcher base interface + shared helpers."""

from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Optional


USER_AGENT = (
    "QDailyTracker/1.0 (https://qdaily.com; +editorial@qdaily.com) "
    "python-urllib"
)

# Browser-like fallback. Used ONLY when the polite identifying UA is rejected
# (HTTP 403 or 429 — usually Cloudflare or rate-limit gates that don't trust
# bot UAs). Sites that explicitly require an identifying UA — like Wikimedia
# — succeed with the primary UA and never trigger this fallback.
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)


@dataclass
class FetchResult:
    """One item produced by a fetcher.

    Fields map onto the entity_updates schema. The executor fills in
    entity_name / entity_group / is_official / collected_at and writes the
    final update-snapshot row.
    """
    source_url: str
    title: str
    published_at: str          # ISO-8601 (Z) or YYYY-MM-DD
    summary: str = ""
    content_type: str = "post"
    source_domain: str = ""
    publisher: str = ""
    raw_label: str = ""
    item_guid: str = ""        # used for cache de-dupe across runs

    def __post_init__(self) -> None:
        if not self.source_domain:
            try:
                self.source_domain = urllib.parse.urlparse(self.source_url).netloc
            except Exception:
                pass


class ManualFetchRequired(Exception):
    """Raised when a source-type cannot be fetched programmatically.

    The executor records the source under a `manual_required` list so the
    human operator can fill in updates by hand.
    """


class Fetcher:
    """Base class. Subclasses implement `fetch`."""

    name: str = "base"

    def fetch(
        self,
        url: str,
        window_start: str,
        window_end: str,
        cache_for_url: Optional[dict] = None,
        timeout: float = 4.0,
    ) -> tuple[list[FetchResult], dict, str]:
        """Return (results, new_cache_state, reason).

        `cache_for_url` carries last-run state (etag, last_seen_guids); the
        returned dict replaces it for this URL on the next run.

        `reason` is a short code (e.g. ``"rss:ok"``, ``"rss:no_feed_discovered"``)
        explaining what happened on this fetch. The executor aggregates these
        across a run so we can see WHY a source returned 0 items, which is
        invisible from the count alone. Reason format: ``"<fetcher>:<code>"``.

        Standard codes per fetcher are documented at the top of each module.
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Shared HTTP helpers
# ---------------------------------------------------------------------------


class HttpError(Exception):
    """Wraps urllib's HTTPError + URLError + TimeoutError into a single class
    that always carries an integer-ish `status` attribute. Fetchers can map
    `status` to a richer reason code (e.g. `rss:fetch_error_403`).

    `status` values:
      - actual HTTP status (e.g. 403, 404, 503) for HTTPError
      - 0 for connection errors / DNS / refused
      - -1 for timeouts
      - -2 for other URLError causes
    """

    def __init__(self, status: int, message: str = ""):
        super().__init__(f"HTTP {status}: {message}" if message else f"HTTP {status}")
        self.status = status


def _do_get(url: str, headers: dict, timeout: float) -> tuple[bytes, dict]:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), {k.lower(): v for k, v in r.headers.items()}


def http_get(
    url: str,
    timeout: float = 4.0,
    extra_headers: Optional[dict] = None,
    follow_redirects: bool = True,
    retry_on_block: bool = True,
) -> tuple[bytes, dict]:
    """GET a URL with the project User-Agent. Returns (body_bytes, headers).

    304 Not Modified is surfaced as an empty body (the cache layer treats it
    as "nothing new"). All other failure modes raise `HttpError` with a
    populated `status` attribute.

    When the polite identifying UA gets a 403 or 429 (Cloudflare-style block
    or rate-limit), we retry ONCE with a browser-like UA. This handles
    sites that 403 anything that isn't browser-shaped, without lying to
    sites that actually want to identify the bot. Pass
    `retry_on_block=False` to disable.
    """
    base_headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if extra_headers:
        base_headers.update(extra_headers)
    try:
        return _do_get(url, base_headers, timeout)
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return b"", {k.lower(): v for k, v in e.headers.items()}
        if retry_on_block and e.code in (403, 429):
            retry_headers = dict(base_headers)
            retry_headers["User-Agent"] = BROWSER_USER_AGENT
            try:
                return _do_get(url, retry_headers, timeout)
            except urllib.error.HTTPError as e2:
                if e2.code == 304:
                    return b"", {k.lower(): v for k, v in e2.headers.items()}
                raise HttpError(e2.code, str(e2)) from e2
            except TimeoutError as e2:
                raise HttpError(-1, "timeout") from e2
            except urllib.error.URLError as e2:
                reason = getattr(e2, "reason", None)
                if isinstance(reason, TimeoutError):
                    raise HttpError(-1, "timeout") from e2
                raise HttpError(0, f"url_error: {reason}") from e2
        raise HttpError(e.code, str(e)) from e
    except TimeoutError as e:
        raise HttpError(-1, "timeout") from e
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", None)
        if isinstance(reason, TimeoutError):
            raise HttpError(-1, "timeout") from e
        raise HttpError(0, f"url_error: {reason}") from e


def in_window(published_at: str, window_start: str, window_end: str) -> bool:
    """Inclusive YYYY-MM-DD comparison on the date prefix of the timestamp."""
    if not published_at or len(published_at) < 10:
        return False
    return window_start <= published_at[:10] <= window_end
