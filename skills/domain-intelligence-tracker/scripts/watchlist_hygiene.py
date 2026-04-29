#!/usr/bin/env python3
"""Inspect a snapshot's `diagnostics` array and surface watchlist sources
that consistently return zero items — the URLs most likely to be stale.

Goes through `diagnostics[]` (set by execute_jobs.py since P1) and groups
sources by their `last_reason`. Useful for deciding which URLs in the
watchlist need to be replaced or marked `is_official: false`.

Categories of "probably stale":
  - rss:feed_empty                — URL is a real feed but has 0 items
  - rss:no_feed_discovered        — no <link rel="alternate"> + no common feed path
  - rss:fetch_error_403/404/410   — endpoint blocked or removed
  - rss:youtube_handle_unresolved — channel page didn't expose channelId
  - sitemap:not_found             — no sitemap.xml at any candidate path
  - github:not_a_repo_url         — URL was a non-repo path (and org fallback also failed)

Usage:
    python3 watchlist_hygiene.py <updates.json> [--reasons CODE,CODE,...]

If --reasons is omitted, all "miss" reasons (anything not ending in :ok) are
grouped. Output is grouped by reason for easy copy-paste into a fix-plan.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("snapshot", help="update-snapshot JSON with diagnostics[]")
    p.add_argument(
        "--reasons",
        default="",
        help="comma-separated reason codes to filter (default: all non-:ok reasons)",
    )
    p.add_argument(
        "--csv", action="store_true", help="emit machine-readable CSV instead of grouped text",
    )
    args = p.parse_args(argv)

    snap_path = Path(args.snapshot)
    if not snap_path.exists():
        print(f"missing: {snap_path}", file=sys.stderr)
        return 2

    doc = json.loads(snap_path.read_text(encoding="utf-8"))
    diagnostics = doc.get("diagnostics", [])
    if not diagnostics:
        print("snapshot has no `diagnostics[]` block — was it written by a post-P1 executor?", file=sys.stderr)
        return 1

    wanted: set[str] = set()
    if args.reasons:
        wanted = {r.strip() for r in args.reasons.split(",") if r.strip()}

    grouped: dict[str, list[dict]] = defaultdict(list)
    for d in diagnostics:
        reason = d.get("last_reason", "")
        if wanted and reason not in wanted:
            continue
        if not wanted and reason.endswith(":ok"):
            continue
        grouped[reason].append(d)

    if args.csv:
        print("reason,entity_name,source_type,url")
        for reason, rows in sorted(grouped.items()):
            for r in rows:
                print(
                    f'"{reason}","{r.get("entity_name","")}",'
                    f'"{r.get("source_type","")}","{r.get("url","")}"'
                )
        return 0

    total = sum(len(v) for v in grouped.values())
    print(f"=== watchlist hygiene report ({total} sources flagged) ===")
    print()
    for reason in sorted(grouped.keys(), key=lambda k: -len(grouped[k])):
        rows = grouped[reason]
        print(f"-- {reason}  ({len(rows)} sources) --")
        for r in rows:
            print(f"    [{r.get('source_type','?'):<10}] {r.get('entity_name',''):<22} {r.get('url','')}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
