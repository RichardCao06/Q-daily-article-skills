#!/usr/bin/env python3
"""Deduplicate an update snapshot by `source_url`.

Research-rules.md #6 ("preserve attribution") and data-model.md recommend
`source_url` as the uniqueness handle for entity_updates. This script enforces
that rule: if the same URL appears more than once in `updates[]`, keep the
earliest `collected_at` (or, when `collected_at` is missing, the earliest
`published_at`; or, when both are missing, the first-seen entry).

Usage:
    python3 dedupe_updates.py <input.json> [--output OUT.json] [--in-place]

If neither --output nor --in-place is given, the deduped document is printed
to stdout.

Also prints a human-readable summary to stderr:

    input count: 12
    duplicate groups: 2
    removed: 3
    output count: 9
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _sort_key(upd: dict) -> tuple[int, str]:
    """Priority ordering used to pick the 'canonical' record in a dup group."""
    collected = upd.get("collected_at")
    if isinstance(collected, str) and collected:
        return (0, collected)
    published = upd.get("published_at")
    if isinstance(published, str) and published:
        return (1, published)
    return (2, "")


def dedupe(doc: dict) -> tuple[dict, dict]:
    """Return (deduped_doc, summary)."""
    updates = doc.get("updates")
    if not isinstance(updates, list):
        return doc, {
            "input_count": 0,
            "duplicate_groups": 0,
            "removed": 0,
            "output_count": 0,
            "note": "no updates[] array; nothing to do",
        }

    # Preserve first-seen order while bucketing by source_url
    groups: dict[str, list[dict]] = {}
    null_url_bucket: list[dict] = []
    order: list[str] = []
    for upd in updates:
        url = upd.get("source_url")
        if not isinstance(url, str) or not url:
            null_url_bucket.append(upd)
            continue
        if url not in groups:
            groups[url] = []
            order.append(url)
        groups[url].append(upd)

    deduped: list[dict] = []
    duplicate_groups = 0
    removed = 0
    for url in order:
        bucket = groups[url]
        if len(bucket) > 1:
            duplicate_groups += 1
            removed += len(bucket) - 1
            # pick earliest by the sort key
            bucket.sort(key=_sort_key)
        deduped.append(bucket[0])

    # Entries without a source_url are preserved untouched and at the end;
    # we cannot dedupe them without the uniqueness handle.
    deduped.extend(null_url_bucket)

    new_doc = dict(doc)
    new_doc["updates"] = deduped

    summary = {
        "input_count": len(updates),
        "duplicate_groups": duplicate_groups,
        "removed": removed,
        "output_count": len(deduped),
        "without_source_url": len(null_url_bucket),
    }
    return new_doc, summary


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", help="Input update-snapshot JSON")
    parser.add_argument("--output", help="Write deduped JSON here")
    parser.add_argument(
        "--in-place", action="store_true", help="Overwrite the input file"
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"No such file: {args.input}", file=sys.stderr)
        return 2

    doc = json.loads(input_path.read_text(encoding="utf-8"))
    deduped, summary = dedupe(doc)

    # Summary to stderr regardless of output mode
    print(
        f"input count: {summary['input_count']}\n"
        f"duplicate groups: {summary['duplicate_groups']}\n"
        f"removed: {summary['removed']}\n"
        f"output count: {summary['output_count']}",
        file=sys.stderr,
    )

    payload = json.dumps(deduped, ensure_ascii=False, indent=2)
    if args.in_place:
        input_path.write_text(payload + "\n", encoding="utf-8")
    elif args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
