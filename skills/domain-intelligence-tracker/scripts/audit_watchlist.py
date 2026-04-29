#!/usr/bin/env python3
"""Pre-flight audit of every URL in an entity snapshot.

Existing `watchlist_hygiene.py` reads run-time `diagnostics[]` from an
updates snapshot. That works only AFTER an executor run, and only if the
diagnostics block survives downstream tooling.

This script is the complementary pre-flight: HEAD-check every URL in the
entities file BEFORE running an executor, and group findings by
source_type. Output is a Markdown report showing which URLs are likely
to return zero items, with suggested fixes.

Why this matters: in the 2026-04-28 baseline run, ~40 of 265 sources
returned `rss:feed_empty` or `rss:no_feed_discovered` because the URL
points at a landing page (e.g. `https://www.anthropic.com/`) instead of
the RSS endpoint (e.g. `https://www.anthropic.com/news/rss`). This is
silent — the executor moves on — so it never gets fixed.

Usage:
    audit_watchlist.py <entities.json>
        [--max-workers 8]
        [--per-job-timeout 6]
        [--output FILE]

Findings classes:
    - http_404 / http_403 / http_410 / dns_error / timeout
    - probable_landing_page    — URL is 200 but content-type is text/html
                                 and `<link rel="alternate" type="...rss">`
                                 is missing (likely a brand homepage, not a feed)
    - feed_ok                  — passes a minimal "looks like a feed" test
    - non_feed_platform        — known social platform (X / LinkedIn /
                                 Discord) where feeds aren't possible;
                                 these are expected and should be tagged
                                 manual-only in the watchlist

The script does NOT fix anything; it just produces a report. Authors
manually patch the entity file and re-run.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# --- known social platforms where programmatic fetching is impossible ----

NON_FEED_PLATFORMS = {
    "x.com",
    "twitter.com",
    "linkedin.com",
    "www.linkedin.com",
    "discord.com",
    "discord.gg",
}


# --- HTTP probe ----------------------------------------------------------

USER_AGENT = "QDailyWatchlistAuditor/1.0 (+editorial)"


def host(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc.lower()
    except Exception:
        return ""


def probe(url: str, timeout: float) -> tuple[int, str, bytes | None]:
    """Returns (status, content_type, body_or_none).

    status semantics:
      - 200..599 = real HTTP status
      - -1       = timeout
      -  0       = DNS / network failure
    """
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ct = resp.headers.get("Content-Type", "").split(";")[0].strip()
            body = resp.read(64 * 1024)  # 64 KB is enough for feed signature
            return resp.status, ct, body
    except urllib.error.HTTPError as e:
        return e.code, "", None
    except urllib.error.URLError as e:
        if isinstance(e.reason, TimeoutError):
            return -1, "", None
        return 0, "", None
    except TimeoutError:
        return -1, "", None
    except Exception:
        return 0, "", None


# --- classification ------------------------------------------------------

_RSS_LINK_RE = re.compile(
    rb'<link[^>]+rel=["\']alternate["\'][^>]+type=["\']application/(rss|atom)\+xml["\']',
    re.IGNORECASE,
)
_FEED_BODY_RE = re.compile(
    rb"<rss\b|<feed\b|<channel\b|<entry\b|<item\b",
    re.IGNORECASE,
)


@dataclass
class Finding:
    entity: str
    source_type: str
    url: str
    status: int
    content_type: str
    classification: str  # one of the codes documented in the docstring
    suggestion: str = ""


def classify(url: str, source_type: str, status: int, ct: str, body: bytes | None) -> tuple[str, str]:
    """Returns (classification_code, suggestion)."""
    h = host(url)

    # 1) social platforms — expected to fail programmatically
    if h in NON_FEED_PLATFORMS or any(h.endswith("." + p) for p in NON_FEED_PLATFORMS):
        return "non_feed_platform", "expected — mark `is_official: true` but rely on manual checks"

    # 2) HTTP errors
    if status == 404:
        return "http_404", "URL returns 404 — find the new endpoint or remove"
    if status == 403:
        return "http_403", "URL returns 403 — likely WAF; needs cookie/UA workaround or replacement"
    if status == 410:
        return "http_410", "URL returns 410 — endpoint permanently gone; replace"
    if status == -1:
        return "timeout", "request timed out — server may be down; retry later"
    if status == 0:
        return "dns_error", "DNS / TLS failed — verify the domain is correct"
    if status >= 500:
        return f"http_{status}", "server-side error — retry, or replace if persistent"
    if status >= 400:
        return f"http_{status}", "client-side error — verify URL is correct"

    # 3) status 200 but classify by source_type expectation
    if source_type in {"x", "linkedin", "discord"}:
        # Should have been caught above by host check, but redundant guard.
        return "non_feed_platform", "expected — manual-only source"

    if source_type in {"blog", "newsroom", "rss", "podcast", "youtube", "reddit"}:
        # Caller wants RSS — does the response look like a feed?
        if not body:
            return "probable_landing_page", "200 OK but no body to inspect"
        if _FEED_BODY_RE.search(body):
            return "feed_ok", ""
        if _RSS_LINK_RE.search(body):
            return "probable_landing_page", "page links to a feed via <link rel=alternate>; switch URL to that feed"
        if "html" in ct.lower():
            return "probable_landing_page", "URL points at HTML landing page, not a feed; find the actual feed URL"
        # Some platforms return JSON or other formats
        return "feed_ok", ""

    if source_type == "github":
        # We just want the URL to resolve; the github fetcher does its own thing.
        return "feed_ok", ""

    # Catch-all for `website` / `docs` / `changelog` etc — site fetcher will
    # try sitemap and then dated-html, both of which work even without RSS.
    if source_type in {"website", "docs", "changelog", "release-notes"}:
        return "feed_ok", ""

    return "feed_ok", ""


# --- audit driver --------------------------------------------------------

def audit(entities: list[dict[str, Any]], max_workers: int, timeout: float) -> list[Finding]:
    jobs: list[tuple[str, str, str]] = []  # (entity, source_type, url)
    for ent in entities:
        for src in ent.get("sources", []) or []:
            url = (src.get("url") or "").strip()
            if not url:
                continue
            jobs.append((ent.get("name", "(unknown)"), src.get("source_type", "?"), url))

    findings: list[Finding] = []

    def task(job: tuple[str, str, str]) -> Finding:
        ent, st, url = job
        status, ct, body = probe(url, timeout)
        klass, suggestion = classify(url, st, status, ct, body)
        return Finding(
            entity=ent,
            source_type=st,
            url=url,
            status=status,
            content_type=ct,
            classification=klass,
            suggestion=suggestion,
        )

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(task, j) for j in jobs]
        for fut in as_completed(futures):
            findings.append(fut.result())

    return findings


# --- rendering -----------------------------------------------------------

def render(findings: list[Finding]) -> str:
    grouped: dict[str, list[Finding]] = {}
    for f in findings:
        grouped.setdefault(f.classification, []).append(f)

    # Order classifications: errors first, then probable issues, then ok.
    order = [
        "http_404", "http_410", "http_403", "dns_error", "timeout",
        "probable_landing_page",
        "non_feed_platform", "feed_ok",
    ]
    keys = sorted(grouped.keys(), key=lambda k: (order.index(k) if k in order else 99, k))

    total = len(findings)
    issues = sum(len(grouped[k]) for k in grouped if k not in {"feed_ok", "non_feed_platform"})

    lines = [
        "# Watchlist audit",
        "",
        f"- Audited **{total}** sources",
        f"- **{issues}** sources have issues",
        f"- {len(grouped.get('feed_ok', []))} sources look healthy",
        f"- {len(grouped.get('non_feed_platform', []))} sources are platforms with no programmatic feed (manual-only)",
        "",
        "## Summary",
        "",
        "| classification | count | suggestion (most common) |",
        "|---|---:|---|",
    ]
    for k in keys:
        items = grouped[k]
        suggestion = items[0].suggestion or "—"
        lines.append(f"| `{k}` | {len(items)} | {suggestion} |")

    for k in keys:
        if k in {"feed_ok"}:
            continue
        items = grouped[k]
        if not items:
            continue
        lines.append("")
        lines.append(f"## `{k}` — {len(items)} source(s)")
        lines.append("")
        lines.append("| entity | source_type | URL | status | content-type |")
        lines.append("|---|---|---|---:|---|")
        # Sort by entity name for stable diffs
        items.sort(key=lambda f: (f.entity, f.source_type))
        for f in items:
            url_short = f.url if len(f.url) <= 80 else f.url[:77] + "…"
            ct = f.content_type or "—"
            lines.append(f"| {f.entity} | {f.source_type} | `{url_short}` | {f.status} | {ct} |")

    return "\n".join(lines) + "\n"


# --- main ----------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("entities", type=Path)
    ap.add_argument("--max-workers", type=int, default=8)
    ap.add_argument("--per-job-timeout", type=float, default=6.0)
    ap.add_argument("--output", type=Path, default=None)
    args = ap.parse_args()

    with args.entities.open(encoding="utf-8") as f:
        data = json.load(f)
    entities = data.get("entities", data) if isinstance(data, dict) else data

    print(f"auditing {sum(len(e.get('sources', [])) for e in entities)} sources from {len(entities)} entities…", file=sys.stderr)
    findings = audit(entities, args.max_workers, args.per_job_timeout)

    out = render(findings)
    if args.output:
        args.output.write_text(out, encoding="utf-8")
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(out)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
