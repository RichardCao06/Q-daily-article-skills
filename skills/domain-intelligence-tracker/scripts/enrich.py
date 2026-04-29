#!/usr/bin/env python3
"""Enrich a snapshot's title-less / summary-less updates by fetching each
source URL and extracting `og:title` / `og:description` / `<title>`.

Background: `SitemapFetcher` only gives `(loc, lastmod)` pairs — it can't
extract a title from `<urlset>` because sitemaps don't carry titles. This
leaves `~129 of 140` items in a typical run with empty `title` / `summary`,
which makes the snapshot less useful for editorial routing. `enrich.py`
walks each such row and fills the two fields by fetching the URL's HTML.

Usage:
    python3 enrich.py <updates.json> \\
        [--output enriched.json]   # default: overwrite the input file
        [--max N]                  # cap total URLs to fetch
        [--sleep 0.3]              # politeness delay
        [--only-empty]             # only enrich rows with empty title AND summary

The script preserves all other fields and only mutates `title` / `summary`.
Adds an `enrichment` block to each row noting what was added.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# Reuse the html_dated extraction logic — it already knows og:title /
# og:description / <title> / JSON-LD shape.
from fetchers import html_dated as html_mod  # noqa: E402
from fetchers.base import HttpError, http_get  # noqa: E402


def needs_enrichment(row: dict, only_both_empty: bool) -> bool:
    title = (row.get("title") or "").strip()
    summary = (row.get("summary") or "").strip()
    if only_both_empty:
        return not title and not summary
    return not title or not summary


def enrich_row(row: dict, *, timeout: float = 10.0) -> dict:
    """Fetch row['source_url'], extract og:title + og:description, fill in.

    Adds row['enrichment'] = {at, status, fields_added}. Returns the row
    (mutated) so callers can re-serialize.
    """
    url = row.get("source_url", "")
    enrichment = {"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    if not url or not url.startswith(("http://", "https://")):
        enrichment["status"] = "skip:no_url"
        row["enrichment"] = enrichment
        return row
    try:
        body, _ = http_get(url, timeout=timeout)
    except HttpError as e:
        enrichment["status"] = f"fetch_error_{_status_label(e.status)}"
        row["enrichment"] = enrichment
        return row
    except Exception as e:  # noqa: BLE001
        enrichment["status"] = f"fetch_error_{type(e).__name__}"
        row["enrichment"] = enrichment
        return row
    if not body:
        enrichment["status"] = "empty_body"
        row["enrichment"] = enrichment
        return row

    metas = html_mod._all_metas(body)
    new_title = html_mod._extract_title(body, metas)
    new_summary = html_mod._extract_summary(body, metas)
    fields_added = []
    if not (row.get("title") or "").strip() and new_title:
        row["title"] = new_title
        fields_added.append("title")
    if not (row.get("summary") or "").strip() and new_summary:
        row["summary"] = new_summary
        fields_added.append("summary")
    if not fields_added:
        enrichment["status"] = "no_fields_extracted"
    else:
        enrichment["status"] = "ok"
        enrichment["fields_added"] = fields_added
    row["enrichment"] = enrichment
    return row


def _status_label(status: int) -> str:
    if status == -1:
        return "timeout"
    if status == 0:
        return "dns"
    return str(status)


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("snapshot", help="path to update-snapshot JSON")
    p.add_argument("--output", help="write enriched snapshot here (default: overwrite input)")
    p.add_argument("--max", type=int, default=0, help="cap total URLs to fetch (0 = unlimited)")
    p.add_argument("--sleep", type=float, default=0.3, help="seconds between fetches")
    p.add_argument(
        "--only-empty",
        action="store_true",
        help="only enrich rows where BOTH title and summary are empty (default enriches if either is)",
    )
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    src = Path(args.snapshot)
    if not src.exists():
        print(f"missing: {src}", file=sys.stderr)
        return 2
    doc = json.loads(src.read_text(encoding="utf-8"))
    updates = doc.get("updates", [])

    candidates = [u for u in updates if needs_enrichment(u, args.only_empty)]
    if args.max:
        candidates = candidates[: args.max]

    print(
        f"{len(updates)} updates total; {len(candidates)} need enrichment "
        f"(only_empty={args.only_empty})",
        file=sys.stderr,
    )

    counts = {"ok": 0, "no_fields_extracted": 0, "fetch_error": 0, "skip": 0, "empty_body": 0}
    for i, row in enumerate(candidates, start=1):
        enrich_row(row, timeout=10.0)
        st = row["enrichment"]["status"]
        if st == "ok":
            counts["ok"] += 1
        elif st == "no_fields_extracted":
            counts["no_fields_extracted"] += 1
        elif st.startswith("fetch_error"):
            counts["fetch_error"] += 1
        elif st.startswith("skip"):
            counts["skip"] += 1
        elif st == "empty_body":
            counts["empty_body"] += 1
        time.sleep(args.sleep)

    out_path = Path(args.output) if args.output else src
    out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(counts, indent=2), file=sys.stderr)
    print(f"wrote → {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
