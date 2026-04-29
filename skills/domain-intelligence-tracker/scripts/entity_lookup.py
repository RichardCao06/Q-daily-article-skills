#!/usr/bin/env python3
"""Quick cross-skill bridge: look up everything we know about one entity.

When you're writing an article and need to ground a claim, you should not
have to manually grep the tracker output. This tool answers, in one
command:

  - what are this entity's official source URLs?
  - what updates from this entity are inside the latest collection window?
  - which other entities published in the same window touched the same
    theme (cheap title-token overlap)?
  - has Q-daily already published an article about this entity in the
    history window? if so, what was the angle?

Output is Markdown — ready to paste into the topic card or the article
draft as research notes.

Usage:
    entity_lookup.py "Anthropic" \\
        --entities  examples/ai-watchlist/ai-entities-2026-04-20.json \\
        --updates   examples/ai-watchlist/ai-updates-2026-04-28.json \\
        --history   /tmp/qdaily-history.json

Entity name match is case-insensitive substring; if your query matches
multiple entities, all of them are listed and you re-run with a tighter
query.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_TOKEN_RE = re.compile(r"[\w一-鿿]+", re.UNICODE)


def tokens(s: str) -> set[str]:
    if not s:
        return set()
    out = set()
    for t in _TOKEN_RE.findall(s.lower()):
        if len(t) < 2:
            continue
        if t.isdigit() and len(t) < 4:
            continue
        out.add(t)
    return out


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def find_entities(entities: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    q = query.lower()
    return [e for e in entities if q in (e.get("name") or "").lower()]


def updates_for_entity(updates: list[dict[str, Any]], entity_name: str) -> list[dict[str, Any]]:
    return [
        u for u in updates
        if (u.get("person_name") or u.get("entity_name") or "").lower() == entity_name.lower()
    ]


def theme_neighbours(updates: list[dict[str, Any]], entity_name: str, k: int = 5) -> list[tuple[str, float]]:
    """For each OTHER entity in the window, compute a Jaccard between its
    title-bag and the target's title-bag. Returns top-k as (entity, score).
    """
    by_entity: dict[str, set[str]] = defaultdict(set)
    for u in updates:
        name = u.get("person_name") or u.get("entity_name") or ""
        for t in tokens(u.get("title", "")):
            by_entity[name].add(t)

    target_bag = by_entity.get(entity_name, set())
    if not target_bag:
        return []

    scored = []
    for name, bag in by_entity.items():
        if name.lower() == entity_name.lower():
            continue
        score = jaccard(target_bag, bag)
        if score > 0:
            scored.append((name, score))
    scored.sort(key=lambda p: p[1], reverse=True)
    return scored[:k]


def prior_coverage(history: list[dict[str, Any]], entity_name: str) -> list[dict[str, Any]]:
    q = entity_name.lower()
    qbag = tokens(entity_name)
    out = []
    for h in history:
        title = (h.get("title") or "").lower()
        if q in title:
            out.append(h)
            continue
        # Token-based fallback for Chinese / multi-word names
        if jaccard(qbag, tokens(h.get("title", ""))) >= 0.2:
            out.append(h)
    return out


def render(entity: dict[str, Any], updates: list[dict[str, Any]], neighbours: list[tuple[str, float]], prior: list[dict[str, Any]]) -> str:
    name = entity.get("name", "?")
    lines = [f"# {name}", ""]

    lines.append("## Official sources")
    lines.append("")
    sources = entity.get("sources", []) or []
    if sources:
        for src in sources:
            label = src.get("source_type", "?")
            url = src.get("url", "")
            primary = " (primary)" if src.get("is_primary") else ""
            lines.append(f"- **{label}**{primary}: {url}")
    else:
        lines.append("_(none recorded)_")
    lines.append("")

    lines.append(f"## Updates in latest window ({len(updates)} item(s))")
    lines.append("")
    if updates:
        for u in sorted(updates, key=lambda x: x.get("published_at", ""), reverse=True):
            title = (u.get("title") or "")[:120]
            ct = u.get("content_type", "?")
            sp = u.get("source_platform", "?")
            pa = (u.get("published_at") or "")[:10]
            url = u.get("source_url", "")
            lines.append(f"- [{ct}/{sp}/{pa}] {title}")
            lines.append(f"  {url}")
    else:
        lines.append("_(no updates in window — entity might be quiet, or feed broken)_")
    lines.append("")

    lines.append("## Theme neighbours in same window")
    lines.append("(other entities whose titles share vocabulary with this entity's)")
    lines.append("")
    if neighbours:
        for name_n, score in neighbours:
            lines.append(f"- {score:.2f} — {name_n}")
    else:
        lines.append("_(none — theme is unique to this entity in the window)_")
    lines.append("")

    lines.append(f"## Prior coverage on Q-daily ({len(prior)} article(s))")
    lines.append("")
    if prior:
        for h in sorted(prior, key=lambda x: x.get("published_at", ""), reverse=True):
            slug = h.get("slug", "?")
            title = h.get("title", "?")
            pa = (h.get("published_at") or "")[:10]
            lines.append(f"- `{slug}` — {title} ({pa})")
        lines.append("")
        lines.append("**Editorial note:** something is already published on this entity. ")
        lines.append("Either (a) frame the new piece as a follow-up that explicitly ")
        lines.append("references the prior coverage, or (b) pick a different angle. ")
        lines.append("Don't write a near-duplicate.")
    else:
        lines.append("_(no prior coverage — story is fresh for this domain)_")
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("entity_name")
    p.add_argument("--entities", required=True, type=Path)
    p.add_argument("--updates",  required=True, type=Path)
    p.add_argument("--history",  type=Path, default=None)
    p.add_argument("--output",   type=Path, default=None)
    return p.parse_args()


def main() -> int:
    args = parse_args()

    with args.entities.open(encoding="utf-8") as f:
        ent_data = json.load(f)
    entities = ent_data.get("entities", ent_data) if isinstance(ent_data, dict) else ent_data

    with args.updates.open(encoding="utf-8") as f:
        upd_data = json.load(f)
    updates = upd_data.get("updates", upd_data) if isinstance(upd_data, dict) else upd_data

    history: list[dict[str, Any]] = []
    if args.history:
        if args.history.exists():
            with args.history.open(encoding="utf-8") as f:
                history = json.load(f) or []
        else:
            print(f"[warn] history file {args.history} does not exist; prior-coverage section skipped", file=sys.stderr)

    matches = find_entities(entities, args.entity_name)
    if not matches:
        print(f"no entity matched query '{args.entity_name}'", file=sys.stderr)
        return 2
    if len(matches) > 1:
        print(f"query '{args.entity_name}' matched {len(matches)} entities:", file=sys.stderr)
        for m in matches:
            print(f"  - {m.get('name')}", file=sys.stderr)
        print("re-run with a tighter query.", file=sys.stderr)
        return 3

    entity = matches[0]
    name = entity.get("name", "")
    ent_updates = updates_for_entity(updates, name)
    neighbours = theme_neighbours(updates, name)
    prior = prior_coverage(history, name)

    out = render(entity, ent_updates, neighbours, prior)
    if args.output:
        args.output.write_text(out, encoding="utf-8")
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
