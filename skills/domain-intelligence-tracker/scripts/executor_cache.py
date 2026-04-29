"""Per-URL cache for execute_jobs.py.

Schema:
    {
        "version": 1,
        "domain": "ai",
        "saved_at": "2026-04-24T10:00:00Z",
        "entries": {
            "<source_url>": {
                "etag": "<HTTP ETag>",
                "last_seen_guids": [...],
                "last_publisher": "...",
                "last_feed_url": "...",
                "last_checked_at": "2026-04-24T10:00:00Z"
            }
        }
    }
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CACHE_VERSION = 1


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": CACHE_VERSION, "domain": "", "saved_at": "", "entries": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": CACHE_VERSION, "domain": "", "saved_at": "", "entries": {}}
    if data.get("version") != CACHE_VERSION:
        # Drop incompatible older caches; collection just reseeds.
        return {"version": CACHE_VERSION, "domain": data.get("domain", ""), "saved_at": "", "entries": {}}
    data.setdefault("entries", {})
    return data


def save(path: Path, cache: dict[str, Any]) -> None:
    cache["saved_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def entry_for(cache: dict[str, Any], url: str) -> dict[str, Any]:
    return dict(cache["entries"].get(url, {}))


def update_entry(cache: dict[str, Any], url: str, new_state: dict[str, Any]) -> None:
    new_state["last_checked_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cache["entries"][url] = new_state
