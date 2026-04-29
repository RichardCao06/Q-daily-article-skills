#!/usr/bin/env python3
"""Compute a diff between two domain-tracker snapshot JSON files.

Supports two snapshot kinds:

- entity snapshots   (keys: domain, snapshot_date, entities)
  Reports: added / removed / rank_changed / status_changed / sources_added /
           sources_removed / renamed (same (group, official_url) but new name).

- update snapshots   (keys: domain, window_start, window_end, updates)
  Reports: added / removed / kept — keyed on source_url (per research-rules.md
  rule #6, URL is the uniqueness handle).

Usage:
    python3 diff_snapshots.py <before.json> <after.json>

The script prints a JSON diff report. Exit 0 regardless of diff content (a
non-empty diff is informational, not an error).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _infer_kind(doc: dict) -> str:
    if "entities" in doc:
        return "entity"
    if "updates" in doc:
        return "update"
    return "unknown"


def _entity_key(entity: dict) -> tuple[str, str]:
    return (entity.get("entity_group", ""), entity.get("name", ""))


def _source_set(entity: dict) -> set[str]:
    return {
        s.get("url", "")
        for s in (entity.get("sources") or [])
        if s.get("url")
    }


def diff_entity_snapshots(before: dict, after: dict) -> dict:
    before_index: dict[tuple[str, str], dict] = {
        _entity_key(e): e for e in before.get("entities", [])
    }
    after_index: dict[tuple[str, str], dict] = {
        _entity_key(e): e for e in after.get("entities", [])
    }

    before_keys = set(before_index.keys())
    after_keys = set(after_index.keys())

    added_keys = sorted(after_keys - before_keys)
    removed_keys = sorted(before_keys - after_keys)
    kept_keys = sorted(before_keys & after_keys)

    rank_changed: list[dict] = []
    status_changed: list[dict] = []
    sources_added_records: list[dict] = []
    sources_removed_records: list[dict] = []

    for key in kept_keys:
        b = before_index[key]
        a = after_index[key]

        if b.get("rank") != a.get("rank"):
            rank_changed.append(
                {
                    "entity_group": key[0],
                    "name": key[1],
                    "before_rank": b.get("rank"),
                    "after_rank": a.get("rank"),
                }
            )

        if b.get("status", "active") != a.get("status", "active"):
            status_changed.append(
                {
                    "entity_group": key[0],
                    "name": key[1],
                    "before_status": b.get("status", "active"),
                    "after_status": a.get("status", "active"),
                }
            )

        b_sources = _source_set(b)
        a_sources = _source_set(a)
        added_urls = sorted(a_sources - b_sources)
        removed_urls = sorted(b_sources - a_sources)
        if added_urls:
            sources_added_records.append(
                {"entity_group": key[0], "name": key[1], "urls": added_urls}
            )
        if removed_urls:
            sources_removed_records.append(
                {"entity_group": key[0], "name": key[1], "urls": removed_urls}
            )

    # Rename heuristic: same (group, official_url) but different name.
    rename_candidates: list[dict] = []
    before_by_official = {
        (e.get("entity_group", ""), e.get("official_url")): e
        for e in before.get("entities", [])
        if e.get("official_url")
    }
    after_by_official = {
        (e.get("entity_group", ""), e.get("official_url")): e
        for e in after.get("entities", [])
        if e.get("official_url")
    }
    shared_officials = set(before_by_official.keys()) & set(after_by_official.keys())
    for shared_key in shared_officials:
        b = before_by_official[shared_key]
        a = after_by_official[shared_key]
        if b.get("name") != a.get("name"):
            rename_candidates.append(
                {
                    "entity_group": shared_key[0],
                    "official_url": shared_key[1],
                    "before_name": b.get("name"),
                    "after_name": a.get("name"),
                }
            )

    return {
        "kind": "entity",
        "before": {
            "snapshot_date": before.get("snapshot_date"),
            "count": len(before.get("entities", [])),
        },
        "after": {
            "snapshot_date": after.get("snapshot_date"),
            "count": len(after.get("entities", [])),
        },
        "added": [{"entity_group": k[0], "name": k[1]} for k in added_keys],
        "removed": [{"entity_group": k[0], "name": k[1]} for k in removed_keys],
        "rank_changed": rank_changed,
        "status_changed": status_changed,
        "sources_added": sources_added_records,
        "sources_removed": sources_removed_records,
        "rename_candidates": rename_candidates,
    }


def diff_update_snapshots(before: dict, after: dict) -> dict:
    before_index: dict[str, dict] = {
        u.get("source_url", ""): u for u in before.get("updates", []) if u.get("source_url")
    }
    after_index: dict[str, dict] = {
        u.get("source_url", ""): u for u in after.get("updates", []) if u.get("source_url")
    }

    before_urls = set(before_index.keys())
    after_urls = set(after_index.keys())

    added_urls = sorted(after_urls - before_urls)
    removed_urls = sorted(before_urls - after_urls)
    kept_urls = sorted(before_urls & after_urls)

    return {
        "kind": "update",
        "before": {
            "window_start": before.get("window_start"),
            "window_end": before.get("window_end"),
            "count": len(before.get("updates", [])),
        },
        "after": {
            "window_start": after.get("window_start"),
            "window_end": after.get("window_end"),
            "count": len(after.get("updates", [])),
        },
        "added": [
            {
                "source_url": url,
                "entity_name": after_index[url].get("entity_name"),
                "title": after_index[url].get("title"),
                "published_at": after_index[url].get("published_at"),
            }
            for url in added_urls
        ],
        "removed": [
            {
                "source_url": url,
                "entity_name": before_index[url].get("entity_name"),
                "title": before_index[url].get("title"),
                "published_at": before_index[url].get("published_at"),
            }
            for url in removed_urls
        ],
        "kept_count": len(kept_urls),
    }


def diff(before: dict, after: dict) -> dict:
    bk = _infer_kind(before)
    ak = _infer_kind(after)
    if bk != ak or bk == "unknown":
        return {
            "kind": "mismatch",
            "error": f"snapshot kinds differ or unknown: before={bk} after={ak}",
        }
    if bk == "entity":
        return diff_entity_snapshots(before, after)
    return diff_update_snapshots(before, after)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("before", help="Earlier snapshot JSON")
    parser.add_argument("after", help="Later snapshot JSON")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    before_path = Path(args.before)
    after_path = Path(args.after)
    if not before_path.exists() or not after_path.exists():
        print("missing file(s)", file=sys.stderr)
        return 2
    report = diff(_load(before_path), _load(after_path))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
