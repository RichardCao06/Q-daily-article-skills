#!/usr/bin/env python3
"""Sync all enabled domain snapshots from a shared config file into Supabase."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path("/Users/shujudagongren/Documents/learnspace/qdaily-backup")
DEFAULT_CONFIG_PATH = ROOT / "skills" / "domain-intelligence-tracker" / "config" / "domains.json"
SUPABASE_SYNC_PATH = ROOT / "tools" / "supabase_sync.py"


def load_supabase_sync_module():
    spec = importlib.util.spec_from_file_location("supabase_sync", SUPABASE_SYNC_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {SUPABASE_SYNC_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_domain_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path).expanduser().resolve()
    return json.loads(config_path.read_text(encoding="utf-8"))


def get_enabled_domains(config: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in config.get("domains", []) if item.get("enabled", False)]


def resolve_domain_files(config_path: str | Path, domain_config: dict[str, Any]) -> dict[str, Path]:
    base_dir = Path(config_path).expanduser().resolve().parent
    return {
        "entity_snapshot": (base_dir / domain_config["entity_snapshot"]).resolve(),
        "update_snapshot": (base_dir / domain_config["update_snapshot"]).resolve(),
        "collection_run": (base_dir / domain_config["collection_run"]).resolve(),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to the domain tracker config JSON file.",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Direct PostgreSQL connection URL used for syncing.",
    )
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Print enabled domains and resolved files without syncing.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    config = load_domain_config(args.config)
    enabled_domains = get_enabled_domains(config)

    resolved = []
    for item in enabled_domains:
        files = resolve_domain_files(args.config, item)
        resolved.append(
            {
                "domain": item["domain"],
                "entity_snapshot": str(files["entity_snapshot"]),
                "update_snapshot": str(files["update_snapshot"]),
                "collection_run": str(files["collection_run"]),
            }
        )

    if args.print_only:
        print(json.dumps({"domains": resolved}, ensure_ascii=False, indent=2))
        return 0

    if not args.database_url:
        print("DATABASE_URL is required unless --print-only is used.", file=sys.stderr)
        return 2

    supabase_sync = load_supabase_sync_module()
    results = []
    for item, files in zip(enabled_domains, [resolve_domain_files(args.config, d) for d in enabled_domains]):
        entity_snapshot = supabase_sync.load_json_document(files["entity_snapshot"])
        update_snapshot = supabase_sync.load_json_document(files["update_snapshot"])
        collection_run = supabase_sync.load_json_document(files["collection_run"])
        sql = supabase_sync.build_generic_domain_sync_sql(
            entity_snapshot=entity_snapshot,
            update_snapshot=update_snapshot,
            collection_run=collection_run,
        )
        response = supabase_sync.run_postgres_query(args.database_url, sql)
        results.append(
            {
                "domain": item["domain"],
                "entities": len(entity_snapshot.get("entities", [])),
                "updates": len(update_snapshot.get("updates", [])),
                "response": response,
            }
        )

    print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
