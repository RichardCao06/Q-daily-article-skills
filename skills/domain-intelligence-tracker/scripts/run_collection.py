#!/usr/bin/env python3
"""Orchestration wrapper: validate → dedupe → (optional diff) → sync to Supabase.

Runs the single-domain end-of-week cycle in one command. Chains the existing
scripts in the correct order and halts on the first failure — so a snapshot
that does not pass validation never reaches the database.

Usage:
    python3 run_collection.py \
        --entities <entity-snapshot.json> \
        --updates <update-snapshot.json> \
        --run <collection-run.json> \
        [--diff-against <previous-update.json>] \
        [--database-url $DATABASE_URL] \
        [--no-dedupe] \
        [--skip-validate-urls]

Without --database-url the wrapper is effectively a dry-run: it validates,
dedupes, and (optionally) diffs, but does not write to Supabase. This is
intentional — Supabase writes require an explicit credential.

Exit codes:
    0  — validation + dedupe passed; sync either ran or was skipped cleanly
    1  — validation errors (sync did NOT run)
    2  — I/O / usage error
    3  — sync error (validation passed, but Supabase write failed)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
REPO_ROOT = SKILL_ROOT.parent.parent  # skills/<name>/ → skills/ → repo root
SUPABASE_SYNC_PATH = REPO_ROOT / "tools" / "supabase_sync.py"


def _load_local(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_DIR / f"{name}.py")
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_supabase_sync():
    if not SUPABASE_SYNC_PATH.exists():
        return None
    spec = importlib.util.spec_from_file_location("supabase_sync", SUPABASE_SYNC_PATH)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATE = _load_local("validate_snapshot")
DEDUPE = _load_local("dedupe_updates")
DIFF = _load_local("diff_snapshots")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, doc: dict) -> None:
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _run_validation(path: Path, kind: str, check_urls: bool) -> list[dict]:
    doc = _read_json(path)
    return VALIDATE.VALIDATORS[kind](doc)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--entities", required=True, help="entity-snapshot JSON")
    parser.add_argument("--updates", required=True, help="update-snapshot JSON")
    parser.add_argument("--run", required=True, help="collection-run JSON")
    parser.add_argument("--diff-against", default=None, help="previous update-snapshot to diff against")
    parser.add_argument("--database-url", default=None, help="if omitted, sync is skipped (dry-run)")
    parser.add_argument("--no-dedupe", action="store_true", help="skip the dedupe step")
    parser.add_argument("--skip-validate-urls", action="store_true", help="skip URL HEAD checks (faster)")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> tuple[int, dict]:
    """Core logic — returns (exit_code, report_dict)."""
    report: dict[str, Any] = {
        "steps": {},
    }

    entities_path = Path(args.entities)
    updates_path = Path(args.updates)
    run_path = Path(args.run)
    for p in (entities_path, updates_path, run_path):
        if not p.exists():
            return 2, {"error": f"missing file: {p}"}

    # 1. Validate
    validation_errors: dict[str, list[dict]] = {}
    for label, path, kind in (
        ("entities", entities_path, "entity"),
        ("updates", updates_path, "update"),
        ("run", run_path, "run"),
    ):
        errors = _run_validation(path, kind, check_urls=not args.skip_validate_urls)
        validation_errors[label] = errors
    report["steps"]["validate"] = {
        "entity_errors": len(validation_errors["entities"]),
        "update_errors": len(validation_errors["updates"]),
        "run_errors": len(validation_errors["run"]),
    }
    if any(validation_errors.values()):
        report["validation_errors"] = validation_errors
        return 1, report

    # 2. Dedupe (in-place on updates snapshot)
    if not args.no_dedupe:
        update_doc = _read_json(updates_path)
        deduped, summary = DEDUPE.dedupe(update_doc)
        _write_json(updates_path, deduped)
        report["steps"]["dedupe"] = summary
    else:
        report["steps"]["dedupe"] = {"skipped": True}

    # 3. Diff (optional)
    if args.diff_against:
        prev_path = Path(args.diff_against)
        if not prev_path.exists():
            return 2, {"error": f"missing --diff-against file: {prev_path}"}
        diff_report = DIFF.diff(_read_json(prev_path), _read_json(updates_path))
        report["steps"]["diff"] = {
            "added": len(diff_report.get("added", [])),
            "removed": len(diff_report.get("removed", [])),
            "kept": diff_report.get("kept_count"),
        }
        report["diff"] = diff_report

    # 4. Sync (requires --database-url)
    if not args.database_url:
        report["steps"]["sync"] = {"skipped": True, "reason": "no --database-url; dry-run"}
        return 0, report

    supabase_sync = _load_supabase_sync()
    if supabase_sync is None:
        report["steps"]["sync"] = {
            "skipped": True,
            "reason": f"supabase_sync module not found at {SUPABASE_SYNC_PATH}",
        }
        return 3, report

    try:
        entity_doc = _read_json(entities_path)
        update_doc = _read_json(updates_path)
        run_doc = _read_json(run_path)
        sql = supabase_sync.build_generic_domain_sync_sql(
            entity_snapshot=entity_doc,
            update_snapshot=update_doc,
            collection_run=run_doc,
        )
        response = supabase_sync.run_postgres_query(args.database_url, sql)
        report["steps"]["sync"] = {
            "ok": True,
            "entity_count": len(entity_doc.get("entities", [])),
            "update_count": len(update_doc.get("updates", [])),
            "response_preview": str(response)[:200],
        }
        return 0, report
    except Exception as exc:  # noqa: BLE001
        report["steps"]["sync"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        return 3, report


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    exit_code, report = run(args)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
