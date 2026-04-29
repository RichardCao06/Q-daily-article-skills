#!/usr/bin/env python3
"""Validate that a snapshot JSON file matches the skill's data model.

Supports three snapshot kinds:

- entity   — matches `assets/entity-tracking-template.json`
- update   — matches `assets/update-snapshot-template.json`
- run      — matches `assets/collection-run-template.json`

The validator is intentionally lightweight (stdlib only) so the skill has no
external dependencies. It enforces only the contract documented in
`references/data-model.md` + the JSON templates.

Usage:
    python3 validate_snapshot.py <path> [--kind entity|update|run]
                                       [--check-urls]
                                       [--timeout SECONDS]

If --kind is omitted the script infers it from the top-level keys.

Exit codes:
    0  — valid
    1  — validation errors (printed to stderr as JSON)
    2  — usage / IO error
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ISO_DATE_FMT = "YYYY-MM-DD"  # documentation only

ALLOWED_ENTITY_GROUPS = (
    "person",
    "company",
    "product",
    "institution",
    "project",
    "lab",
    "brand",
    "creator",
    "standards body",
    "open-source project",
    "dataset",
    "method",
)

ALLOWED_SOURCE_TYPES = (
    "website",
    "blog",
    "newsroom",
    "x",
    "youtube",
    "docs",
    "github",
    "discord",
    "reddit",
    "forum",
    "linkedin",
    "changelog",
    "release-notes",
    "podcast",
    "newsletter",
    "press",
)

ALLOWED_STATUS = ("active", "inactive", "retired")

ALLOWED_CONTENT_TYPES = (
    "post",
    "blog",
    "video",
    "podcast",
    "docs",
    "release-notes",
    "changelog",
    "product",
    "interview",
    "paper",
    "talk",
    "press",
    "announcement",
    "engineering",
    "essay",
    "news",
    "policy",
    "research",
)


def _err(errors: list[dict], path: str, message: str) -> None:
    errors.append({"path": path, "error": message})


def _is_str(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _is_iso_date(value: Any) -> bool:
    """Quick check: YYYY-MM-DD, digits only, no validation of ranges."""
    if not isinstance(value, str) or len(value) != 10:
        return False
    return (
        value[4] == "-"
        and value[7] == "-"
        and value[:4].isdigit()
        and value[5:7].isdigit()
        and value[8:10].isdigit()
    )


def _is_iso_datetime(value: Any) -> bool:
    """Accept `YYYY-MM-DD` or `YYYY-MM-DDTHH:MM:SSZ`-style strings."""
    if not isinstance(value, str):
        return False
    if _is_iso_date(value):
        return True
    # Very loose: require `YYYY-MM-DDT` prefix.
    return len(value) >= 11 and value[:10] and _is_iso_date(value[:10]) and value[10] == "T"


def _is_url(value: Any) -> bool:
    return isinstance(value, str) and (
        value.startswith("http://") or value.startswith("https://")
    )


# ---------------------------------------------------------------------------
# Kind inference
# ---------------------------------------------------------------------------

def infer_kind(doc: dict) -> str:
    """Return `entity`, `update`, or `run` based on the document's top keys."""
    if not isinstance(doc, dict):
        return "unknown"
    if "entities" in doc:
        return "entity"
    if "updates" in doc:
        return "update"
    if "goal" in doc or "output_targets" in doc or "source_policy" in doc:
        return "run"
    return "unknown"


# ---------------------------------------------------------------------------
# Per-kind validators
# ---------------------------------------------------------------------------

def validate_entity_snapshot(doc: dict) -> list[dict]:
    errors: list[dict] = []

    if not isinstance(doc, dict):
        _err(errors, "/", "top-level must be a JSON object")
        return errors

    if not _is_str(doc.get("domain")):
        _err(errors, "/domain", "missing or empty string")
    if not _is_iso_date(doc.get("snapshot_date", "")):
        _err(errors, "/snapshot_date", "missing or not YYYY-MM-DD")

    entities = doc.get("entities")
    if not isinstance(entities, list):
        _err(errors, "/entities", "missing or not a list")
        return errors

    seen_names: dict[tuple[str, str], int] = {}
    for i, entity in enumerate(entities):
        p = f"/entities[{i}]"
        if not isinstance(entity, dict):
            _err(errors, p, "entry must be an object")
            continue

        if not _is_str(entity.get("name")):
            _err(errors, f"{p}/name", "missing or empty")
        if not _is_str(entity.get("entity_group")):
            _err(errors, f"{p}/entity_group", "missing or empty")
        elif entity["entity_group"] not in ALLOWED_ENTITY_GROUPS:
            _err(
                errors,
                f"{p}/entity_group",
                f"value '{entity['entity_group']}' not in allowed set",
            )

        rank = entity.get("rank")
        if not isinstance(rank, int) or rank < 1:
            _err(errors, f"{p}/rank", "missing or not a positive integer")

        status = entity.get("status", "active")
        if status not in ALLOWED_STATUS:
            _err(
                errors,
                f"{p}/status",
                f"value '{status}' not in {ALLOWED_STATUS}",
            )

        if status == "retired" and not _is_iso_date(entity.get("retired_at", "")):
            _err(errors, f"{p}/retired_at", "required when status='retired' (YYYY-MM-DD)")

        official_url = entity.get("official_url")
        if official_url is not None and not _is_url(official_url):
            _err(errors, f"{p}/official_url", "must be an http(s) URL if present")

        # duplicate detection
        key = (entity.get("entity_group", ""), entity.get("name", ""))
        if key in seen_names:
            _err(
                errors,
                p,
                f"duplicate (entity_group, name) — first seen at /entities[{seen_names[key]}]",
            )
        else:
            seen_names[key] = i

        # sources
        sources = entity.get("sources", [])
        if sources and not isinstance(sources, list):
            _err(errors, f"{p}/sources", "if present, must be a list")
            continue

        primary_count = 0
        for j, source in enumerate(sources or []):
            sp = f"{p}/sources[{j}]"
            if not isinstance(source, dict):
                _err(errors, sp, "entry must be an object")
                continue
            stype = source.get("source_type")
            if not _is_str(stype):
                _err(errors, f"{sp}/source_type", "missing or empty")
            elif stype not in ALLOWED_SOURCE_TYPES:
                _err(errors, f"{sp}/source_type", f"value '{stype}' not in allowed set")
            if not _is_url(source.get("url", "")):
                _err(errors, f"{sp}/url", "must be an http(s) URL")
            if source.get("is_primary") is True:
                primary_count += 1

        if primary_count > 1:
            _err(errors, f"{p}/sources", f"more than one source marked is_primary=true ({primary_count})")

    return errors


def validate_update_snapshot(doc: dict) -> list[dict]:
    errors: list[dict] = []

    if not isinstance(doc, dict):
        _err(errors, "/", "top-level must be a JSON object")
        return errors

    if not _is_str(doc.get("domain")):
        _err(errors, "/domain", "missing or empty string")
    if not _is_iso_date(doc.get("window_start", "")):
        _err(errors, "/window_start", "missing or not YYYY-MM-DD")
    if not _is_iso_date(doc.get("window_end", "")):
        _err(errors, "/window_end", "missing or not YYYY-MM-DD")
    if _is_iso_date(doc.get("window_start", "")) and _is_iso_date(doc.get("window_end", "")):
        if doc["window_start"] > doc["window_end"]:
            _err(errors, "/window_start", "must be <= window_end")

    updates = doc.get("updates")
    if not isinstance(updates, list):
        _err(errors, "/updates", "missing or not a list")
        return errors

    seen_urls: dict[str, int] = {}
    for i, upd in enumerate(updates):
        p = f"/updates[{i}]"
        if not isinstance(upd, dict):
            _err(errors, p, "entry must be an object")
            continue

        # `summary` is optional — many real-world feeds (especially sitemap-
        # derived rows that only had og:title, not og:description) legitimately
        # have no summary. Title is required as the minimum identifier.
        for field in ("entity_name", "entity_group", "title", "source_url"):
            if not _is_str(upd.get(field)):
                _err(errors, f"{p}/{field}", "missing or empty")

        if not _is_url(upd.get("source_url", "")):
            _err(errors, f"{p}/source_url", "must be an http(s) URL")

        if not _is_iso_datetime(upd.get("published_at", "")):
            _err(errors, f"{p}/published_at", "missing or not ISO-8601 (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ)")
        else:
            # if dates both present, verify window containment
            pub_date = upd["published_at"][:10]
            if _is_iso_date(doc.get("window_start", "")) and _is_iso_date(doc.get("window_end", "")):
                if not (doc["window_start"] <= pub_date <= doc["window_end"]):
                    _err(
                        errors,
                        f"{p}/published_at",
                        f"date {pub_date} falls outside window {doc['window_start']}..{doc['window_end']}",
                    )

        content_type = upd.get("content_type")
        if content_type is not None and content_type not in ALLOWED_CONTENT_TYPES:
            _err(
                errors,
                f"{p}/content_type",
                f"value '{content_type}' not in allowed set",
            )

        is_official = upd.get("is_official")
        if is_official is not None and not isinstance(is_official, bool):
            _err(errors, f"{p}/is_official", "must be a boolean")

        url = upd.get("source_url", "")
        if url in seen_urls:
            _err(
                errors,
                p,
                f"duplicate source_url — first seen at /updates[{seen_urls[url]}]",
            )
        else:
            seen_urls[url] = i

    return errors


def validate_collection_run(doc: dict) -> list[dict]:
    errors: list[dict] = []

    if not isinstance(doc, dict):
        _err(errors, "/", "top-level must be a JSON object")
        return errors

    if not _is_str(doc.get("domain")):
        _err(errors, "/domain", "missing or empty string")
    if not _is_iso_date(doc.get("window_start", "")):
        _err(errors, "/window_start", "missing or not YYYY-MM-DD")
    if not _is_iso_date(doc.get("window_end", "")):
        _err(errors, "/window_end", "missing or not YYYY-MM-DD")
    if _is_iso_date(doc.get("window_start", "")) and _is_iso_date(doc.get("window_end", "")):
        if doc["window_start"] > doc["window_end"]:
            _err(errors, "/window_start", "must be <= window_end")

    if "entity_scope" in doc and not isinstance(doc["entity_scope"], list):
        _err(errors, "/entity_scope", "if present, must be a list")

    sp = doc.get("source_policy")
    if sp is not None and not isinstance(sp, dict):
        _err(errors, "/source_policy", "if present, must be an object")
    if isinstance(sp, dict):
        if "include_media" in sp and not isinstance(sp["include_media"], bool):
            _err(errors, "/source_policy/include_media", "must be a boolean")
        if "include_community" in sp and not isinstance(sp["include_community"], bool):
            _err(errors, "/source_policy/include_community", "must be a boolean")

    return errors


VALIDATORS = {
    "entity": validate_entity_snapshot,
    "update": validate_update_snapshot,
    "run": validate_collection_run,
}


# ---------------------------------------------------------------------------
# URL checker
# ---------------------------------------------------------------------------

def _check_url(url: str, timeout: float) -> dict:
    """Perform a HEAD request and return a diagnostic record."""
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "dit-validator/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return {"url": url, "ok": True, "status": response.status}
    except urllib.error.HTTPError as exc:
        ok = 200 <= exc.code < 400
        return {"url": url, "ok": ok, "status": exc.code}
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        return {"url": url, "ok": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"url": url, "ok": False, "error": f"{type(exc).__name__}: {exc}"}


def collect_urls(doc: dict, kind: str) -> list[str]:
    urls: list[str] = []
    if kind == "entity":
        for e in doc.get("entities", []):
            if _is_url(e.get("official_url", "")):
                urls.append(e["official_url"])
            for s in e.get("sources", []) or []:
                if _is_url(s.get("url", "")):
                    urls.append(s["url"])
    elif kind == "update":
        for u in doc.get("updates", []):
            if _is_url(u.get("source_url", "")):
                urls.append(u["source_url"])
    return urls


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", help="Path to snapshot JSON file")
    parser.add_argument(
        "--kind",
        choices=["entity", "update", "run"],
        help="Snapshot kind. Inferred from top-level keys if omitted.",
    )
    parser.add_argument(
        "--check-urls",
        action="store_true",
        help="Also perform HEAD requests against every URL (slow).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Per-URL timeout in seconds (default 5).",
    )
    return parser.parse_args(argv)


def run(path: Path, kind: str | None, check_urls: bool, timeout: float) -> dict:
    text = path.read_text(encoding="utf-8")
    doc = json.loads(text)

    kind = kind or infer_kind(doc)
    if kind not in VALIDATORS:
        return {
            "path": str(path),
            "kind": kind,
            "errors": [{"path": "/", "error": f"unable to infer kind; pass --kind"}],
            "url_checks": [],
        }

    errors = VALIDATORS[kind](doc)
    url_checks: list[dict] = []
    if check_urls:
        for url in collect_urls(doc, kind):
            url_checks.append(_check_url(url, timeout))

    return {"path": str(path), "kind": kind, "errors": errors, "url_checks": url_checks}


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    path = Path(args.path)
    if not path.exists():
        print(f"No such file: {args.path}", file=sys.stderr)
        return 2

    report = run(path, args.kind, args.check_urls, args.timeout)

    ok = not report["errors"] and all(c.get("ok") for c in report["url_checks"])
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
