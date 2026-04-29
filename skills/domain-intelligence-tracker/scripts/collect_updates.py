#!/usr/bin/env python3
"""Generate a collection job file from an entity snapshot.

The actual fetching of web pages must be performed by Claude (or any agent
with web-access tools) — this script's job is to lay out the fan-out plan
deterministically so each collection run is reproducible:

    entity × source → one job with:
        - a window_start / window_end
        - a set of WebSearch / WebFetch queries derived from source_type
        - a template for the expected update record

Usage:
    python3 collect_updates.py <entity-snapshot.json>
        --window-start YYYY-MM-DD --window-end YYYY-MM-DD
        [--group <entity_group>]
        [--include-community]
        [--output FILE]

The output shape:

    {
      "domain": "ai",
      "window_start": "...",
      "window_end": "...",
      "jobs": [
        {
          "entity_group": "person",
          "entity_name": "Sam Altman",
          "source_type": "x",
          "url": "https://x.com/sama",
          "is_official": true,
          "suggested_queries": ["site:x.com/sama 2026 after:2026-04-22"],
          "fetch_hint": "Fetch recent posts; filter by window.",
          "expected_update_template": { ... }
        },
        ...
      ]
    }
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


# Map source_type → (fetch_hint, query_template)
SOURCE_FETCH_HINTS: dict[str, tuple[str, str]] = {
    "website": (
        "Fetch the homepage. Look for a 'blog', 'news', or 'updates' link.",
        "{url}",
    ),
    "blog": (
        "Fetch the blog index. Filter by date in the window.",
        "site:{domain} after:{window_start}",
    ),
    "newsroom": (
        "Fetch the newsroom/press index. Filter by date in the window.",
        "site:{domain} press after:{window_start}",
    ),
    "x": (
        "Pull recent posts. If the handle is @user, use the X profile URL.",
        "site:x.com {handle_or_url} after:{window_start}",
    ),
    "youtube": (
        "Pull recent uploads. Sort by date.",
        "site:youtube.com {handle_or_url} after:{window_start}",
    ),
    "docs": (
        "Check docs changelog / release notes pages.",
        "site:{domain} changelog after:{window_start}",
    ),
    "changelog": (
        "Fetch the changelog page; parse dated entries.",
        "{url}",
    ),
    "release-notes": (
        "Fetch the release notes page; parse dated entries.",
        "{url}",
    ),
    "github": (
        "Use GitHub's releases and activity endpoints.",
        "site:github.com {repo_path} releases",
    ),
    "discord": (
        "If announcement-channel, fetch via public mirror.",
        "site:discord.com {server_path} announcements",
    ),
    "reddit": (
        "Search the subreddit for official posts in the window.",
        "site:reddit.com {path} after:{window_start}",
    ),
    "forum": (
        "Pull recent threads from the official forum.",
        "site:{domain} announcements after:{window_start}",
    ),
    "linkedin": (
        "Pull recent posts from the official page.",
        "site:linkedin.com/company {slug} after:{window_start}",
    ),
    "podcast": (
        "Fetch the podcast feed; filter by date.",
        "{url}",
    ),
    "newsletter": (
        "Fetch the newsletter archive; parse dated issues.",
        "{url}",
    ),
    "press": (
        "Fetch the press center index.",
        "{url}",
    ),
}

DEFAULT_HINT = ("Check the URL for recent entries in the window.", "{url}")


def _domain_of(url: str) -> str:
    if not url:
        return ""
    stripped = url.split("://", 1)[-1]
    host = stripped.split("/", 1)[0]
    return host


def _make_query(template: str, url: str, window_start: str) -> str:
    return (
        template.replace("{url}", url)
        .replace("{domain}", _domain_of(url))
        .replace("{handle_or_url}", url)
        .replace("{repo_path}", _domain_of(url).replace("github.com", "").strip("/"))
        .replace("{server_path}", _domain_of(url))
        .replace("{path}", _domain_of(url))
        .replace("{slug}", _domain_of(url))
        .replace("{window_start}", window_start)
    )


def build_jobs(
    entity_doc: dict,
    window_start: str,
    window_end: str,
    group_filter: str | None,
    include_community: bool,
) -> list[dict]:
    jobs: list[dict] = []
    for entity in entity_doc.get("entities", []):
        if entity.get("status") == "retired":
            continue
        if group_filter and entity.get("entity_group") != group_filter:
            continue
        for source in entity.get("sources", []) or []:
            is_official = bool(source.get("is_official"))
            if not is_official and not include_community:
                continue
            source_type = source.get("source_type") or "website"
            url = source.get("url", "")
            hint, query_template = SOURCE_FETCH_HINTS.get(source_type, DEFAULT_HINT)
            query = _make_query(query_template, url, window_start)
            jobs.append(
                {
                    "entity_group": entity.get("entity_group"),
                    "entity_name": entity.get("name"),
                    "source_type": source_type,
                    "url": url,
                    "is_official": is_official,
                    "is_primary": bool(source.get("is_primary")),
                    "suggested_queries": [query],
                    "fetch_hint": hint,
                    "expected_update_template": {
                        "entity_group": entity.get("entity_group"),
                        "entity_name": entity.get("name"),
                        "source_url": "<fill when fetched>",
                        "source_platform": source_type,
                        "source_domain": _domain_of(url),
                        "title": "<fill>",
                        "summary": "<fill, 1-3 sentences, factual>",
                        "published_at": "<YYYY-MM-DDTHH:MM:SSZ>",
                        "content_type": "<post|blog|product|release-notes|...>",
                        "is_official": is_official,
                    },
                }
            )
    return jobs


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("entities", help="entity-snapshot JSON")
    parser.add_argument("--window-start", required=True)
    parser.add_argument("--window-end", required=True)
    parser.add_argument("--group", default=None)
    parser.add_argument("--include-community", action="store_true")
    parser.add_argument("--output", default=None)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    entity_path = Path(args.entities)
    if not entity_path.exists():
        print(f"No such file: {args.entities}", file=sys.stderr)
        return 2
    doc = json.loads(entity_path.read_text(encoding="utf-8"))
    jobs = build_jobs(
        doc,
        args.window_start,
        args.window_end,
        args.group,
        args.include_community,
    )
    payload = {
        "domain": doc.get("domain"),
        "window_start": args.window_start,
        "window_end": args.window_end,
        "job_count": len(jobs),
        "jobs": jobs,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
