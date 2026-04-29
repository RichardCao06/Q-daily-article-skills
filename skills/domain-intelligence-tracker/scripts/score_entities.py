#!/usr/bin/env python3
"""Score entities along the dimensions in research-rules.md.

research-rules.md #1 defines four-plus ranking criteria:

    - signal     (first-party information generation)
    - influence  (field direction influence)
    - output     (products / research / policy signals shipped)
    - ecosystem  (adjacent-ecosystem impact)
    - near_term  (near-term importance)

This script turns those prose criteria into a 0–3 scorecard per entity and
produces a re-ranked list. Scores can come from:

    - inline scores on each entity:
          "scores": {"signal": 3, "influence": 2, "output": 2, "ecosystem": 1, "near_term": 2}
    - or the current `rank` field (inverted to a 0–3 scale) as a fallback

The weight of each dimension is configurable. Defaults:
    signal=3, influence=2, output=2, ecosystem=1, near_term=2

Total score = sum(score_i * weight_i). New rank = descending order on total.

Usage:
    python3 score_entities.py <entity-snapshot.json>
        [--weights key=value,key=value,...]
        [--group <entity_group>]     # limit to one group; default: all groups
        [--output FILE]              # defaults to stdout

The script does NOT rewrite the input file. Authors decide which re-ranks to
accept by hand — scoring is an aid, not an oracle.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


DIMENSIONS = ("signal", "influence", "output", "ecosystem", "near_term")
DEFAULT_WEIGHTS: dict[str, float] = {
    "signal": 3.0,
    "influence": 2.0,
    "output": 2.0,
    "ecosystem": 1.0,
    "near_term": 2.0,
}


def parse_weights(spec: str | None) -> dict[str, float]:
    weights = dict(DEFAULT_WEIGHTS)
    if not spec:
        return weights
    for part in spec.split(","):
        if not part.strip():
            continue
        if "=" not in part:
            raise ValueError(f"bad weight spec: '{part}'")
        k, v = part.split("=", 1)
        k = k.strip()
        if k not in DIMENSIONS:
            raise ValueError(f"unknown dimension '{k}'; allowed: {DIMENSIONS}")
        weights[k] = float(v.strip())
    return weights


def _fallback_score_from_rank(rank: int, group_size: int) -> int:
    """Map legacy rank → 0–3 bucket (higher = better)."""
    if group_size <= 0:
        return 0
    pct = (rank - 1) / group_size
    if pct < 0.25:
        return 3
    if pct < 0.5:
        return 2
    if pct < 0.75:
        return 1
    return 0


def score_entity(entity: dict, group_size: int) -> dict[str, int]:
    """Return a dict of per-dimension 0–3 scores for one entity."""
    scores = entity.get("scores") or {}
    out: dict[str, int] = {}
    for dim in DIMENSIONS:
        raw = scores.get(dim)
        if isinstance(raw, (int, float)):
            val = int(max(0, min(3, round(raw))))
        else:
            # Fall back to rank-derived score for every dimension.
            val = _fallback_score_from_rank(int(entity.get("rank", group_size)), group_size)
        out[dim] = val
    return out


def total(scores: dict[str, int], weights: dict[str, float]) -> float:
    return sum(scores[dim] * weights[dim] for dim in DIMENSIONS)


def build_scoreboard(doc: dict, weights: dict[str, float], group_filter: str | None) -> list[dict]:
    entities = doc.get("entities", [])
    # group sizes (used for rank-based fallback normalization)
    sizes: dict[str, int] = {}
    for e in entities:
        g = e.get("entity_group", "")
        sizes[g] = sizes.get(g, 0) + 1

    scored: list[dict] = []
    for e in entities:
        if group_filter and e.get("entity_group") != group_filter:
            continue
        g = e.get("entity_group", "")
        per_dim = score_entity(e, sizes.get(g, 1))
        t = total(per_dim, weights)
        scored.append(
            {
                "entity_group": g,
                "name": e.get("name"),
                "current_rank": e.get("rank"),
                "status": e.get("status", "active"),
                "scores": per_dim,
                "total": round(t, 3),
            }
        )

    # group-wise re-rank: order within each group, then concatenate
    by_group: dict[str, list[dict]] = {}
    for row in scored:
        by_group.setdefault(row["entity_group"], []).append(row)

    out: list[dict] = []
    for g, rows in by_group.items():
        rows.sort(key=lambda r: r["total"], reverse=True)
        for new_rank, row in enumerate(rows, start=1):
            row["proposed_rank"] = new_rank
            row["rank_delta"] = (
                (row["current_rank"] - new_rank)
                if isinstance(row["current_rank"], int)
                else None
            )
            out.append(row)
    return out


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("entities", help="entity-snapshot JSON")
    parser.add_argument("--weights", default=None, help="comma-separated key=value overrides")
    parser.add_argument("--group", default=None, help="limit to one entity_group")
    parser.add_argument("--output", default=None)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    entity_path = Path(args.entities)
    if not entity_path.exists():
        print(f"No such file: {args.entities}", file=sys.stderr)
        return 2
    try:
        weights = parse_weights(args.weights)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    doc = json.loads(entity_path.read_text(encoding="utf-8"))
    rows = build_scoreboard(doc, weights, args.group)

    payload = {
        "domain": doc.get("domain"),
        "snapshot_date": doc.get("snapshot_date"),
        "weights": weights,
        "rows": rows,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
