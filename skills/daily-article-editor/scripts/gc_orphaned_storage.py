#!/usr/bin/env python3
"""Garbage-collect orphaned Storage objects in the daily project's article-media bucket.

An object is "orphaned" if its slug subdirectory under `articles/<slug>/...`
no longer corresponds to a row in `public.articles`. This happens when an
article gets deleted from the DB without manually cleaning up Storage.

Default mode is dry-run: it lists what WOULD be deleted, prints the count,
and exits 0. Pass `--execute` to actually delete the orphan objects.

Required env vars (loaded via `set -a; source .env.local; set +a`):
    DAILY_DATABASE_URL          direct Postgres URL for the daily project
    DAILY_SERVICE_ROLE_KEY      Supabase service_role JWT — needed for the
                                permanent "Service role deletes article media"
                                RLS policy

Required Q-daily env file (defaults to ../../../Q-daily/.env.local):
    NEXT_PUBLIC_SUPABASE_URL    project URL for Storage API

Usage:
    python3 gc_orphaned_storage.py                 # dry-run
    python3 gc_orphaned_storage.py --execute       # actually delete
    python3 gc_orphaned_storage.py --bucket foo    # different bucket
    python3 gc_orphaned_storage.py --max-delete 5  # cap deletions
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import psycopg2
import requests


DEFAULT_BUCKET = "article-media"
DEFAULT_PREFIX = "articles/"
DEFAULT_QDAILY_ENV = Path(
    "/Users/shujudagongren/Documents/learnspace/Q-daily/.env.local"
)


def load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def list_storage_subdirs(project_url: str, key: str, bucket: str, prefix: str) -> list[str]:
    """List immediate subdirectories under `prefix` in `bucket`."""
    r = requests.post(
        f"{project_url}/storage/v1/object/list/{bucket}",
        headers={
            "Authorization": f"Bearer {key}",
            "apikey": key,
            "Content-Type": "application/json",
        },
        data=json.dumps({"prefix": prefix, "limit": 1000}),
        timeout=15,
    )
    r.raise_for_status()
    return [item["name"] for item in r.json() if item.get("id") is None]


def list_storage_files_under_slug(
    project_url: str, key: str, bucket: str, prefix: str, slug: str
) -> list[str]:
    """Return full object paths (relative to bucket root) under `articles/<slug>/`."""
    paths: list[str] = []
    for kind in ("hero", "inline"):
        r = requests.post(
            f"{project_url}/storage/v1/object/list/{bucket}",
            headers={
                "Authorization": f"Bearer {key}",
                "apikey": key,
                "Content-Type": "application/json",
            },
            data=json.dumps({"prefix": f"{prefix}{slug}/{kind}/", "limit": 1000}),
            timeout=15,
        )
        r.raise_for_status()
        for item in r.json():
            # listing under .../<kind>/ returns leaf names; build full path
            if item.get("id") is not None:
                paths.append(f"{prefix}{slug}/{kind}/{item['name']}")
    return paths


def delete_objects(project_url: str, key: str, bucket: str, paths: list[str]) -> int:
    """Bulk-delete objects. Returns number deleted."""
    if not paths:
        return 0
    r = requests.delete(
        f"{project_url}/storage/v1/bucket/{bucket}/objects",
        headers={
            "Authorization": f"Bearer {key}",
            "apikey": key,
            "Content-Type": "application/json",
        },
        data=json.dumps({"prefixes": paths}),
        timeout=30,
    )
    if r.status_code in (200, 204):
        return len(paths)
    # Fallback: single-delete loop
    n = 0
    for p in paths:
        rr = requests.delete(
            f"{project_url}/storage/v1/object/{bucket}/{p}",
            headers={"Authorization": f"Bearer {key}", "apikey": key},
            timeout=15,
        )
        if rr.status_code == 200:
            n += 1
    return n


def collect_orphans(
    db_url: str, project_url: str, key: str, bucket: str, prefix: str
) -> tuple[set[str], set[str], list[str]]:
    """Return (live_slugs, orphan_slugs, orphan_object_paths)."""
    conn = psycopg2.connect(db_url, connect_timeout=8)
    cur = conn.cursor()
    cur.execute("select slug from public.articles")
    live_slugs = {row[0] for row in cur.fetchall()}
    conn.close()

    storage_slugs = set(list_storage_subdirs(project_url, key, bucket, prefix))
    orphan_slugs = storage_slugs - live_slugs

    orphan_paths: list[str] = []
    for slug in sorted(orphan_slugs):
        orphan_paths.extend(
            list_storage_files_under_slug(project_url, key, bucket, prefix, slug)
        )
    return live_slugs, orphan_slugs, orphan_paths


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--bucket", default=DEFAULT_BUCKET)
    p.add_argument("--prefix", default=DEFAULT_PREFIX)
    p.add_argument("--env-file", default=str(DEFAULT_QDAILY_ENV))
    p.add_argument("--execute", action="store_true", help="Actually delete (default: dry-run)")
    p.add_argument("--max-delete", type=int, default=0, help="Cap deletions at N objects (0 = unlimited)")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    env = load_env_file(Path(args.env_file))
    project_url = env["NEXT_PUBLIC_SUPABASE_URL"]
    key = os.environ.get("DAILY_SERVICE_ROLE_KEY")
    if not key:
        print("DAILY_SERVICE_ROLE_KEY is required (load .env.local first).", file=sys.stderr)
        return 2
    db_url = os.environ["DAILY_DATABASE_URL"]

    live_slugs, orphan_slugs, orphan_paths = collect_orphans(
        db_url, project_url, key, args.bucket, args.prefix
    )

    print(f"bucket:           {args.bucket}")
    print(f"prefix scanned:   {args.prefix}")
    print(f"live articles:    {len(live_slugs)}")
    print(f"storage slugs:    {len(live_slugs) + len(orphan_slugs) - len(live_slugs & orphan_slugs)}")
    print(f"orphan slugs:     {len(orphan_slugs)}")
    print(f"orphan objects:   {len(orphan_paths)}")
    if orphan_slugs:
        print()
        print("orphan slug list:")
        for s in sorted(orphan_slugs):
            print(f"  {s}")
        print()
        print("first 10 paths:")
        for p in orphan_paths[:10]:
            print(f"  {p}")
        if len(orphan_paths) > 10:
            print(f"  …(+{len(orphan_paths) - 10} more)")

    if not args.execute:
        print("\n[dry-run] pass --execute to delete the orphan objects.")
        return 0

    if not orphan_paths:
        print("\nnothing to delete.")
        return 0

    targets = orphan_paths[: args.max_delete] if args.max_delete else orphan_paths
    n = delete_objects(project_url, key, args.bucket, targets)
    print(f"\n[deleted] {n} of {len(targets)} target objects")
    return 0 if n == len(targets) else 3


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
