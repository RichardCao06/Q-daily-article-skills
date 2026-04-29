#!/usr/bin/env python3
"""Show recent execute_jobs.py runs and their hit rates.

Reads `<cache_dir>/run-stats.jsonl` (one record per run) and prints a small
table plus rolling averages over the last N runs.

Usage:
    python3 view_run_stats.py                       # default: .cache/run-stats.jsonl
    python3 view_run_stats.py --path /tmp/x.jsonl
    python3 view_run_stats.py --last 30
    python3 view_run_stats.py --by-source-type      # break down today's snapshot

Hit rate definition:
    jobs_with_hits / jobs_input

If no jobs in window have any source emitting an item, hit rate is 0. A run
with hit_rate ≥ 0.5 is a "good day"; ≥ 0.7 means the watchlist is hitting
well; < 0.3 usually means most fetchers were blocked or out of window.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


DEFAULT_STATS = Path(".cache/run-stats.jsonl")


def load_stats(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except Exception:
            continue
    return records


def by_source_type(snapshot_path: Path) -> dict[str, dict]:
    if not snapshot_path.exists():
        return {}
    snap = json.loads(snapshot_path.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for u in snap.get("updates", []):
        st = u.get("source_platform", "?")
        out.setdefault(st, {"items": 0, "entities": set()})
        out[st]["items"] += 1
        out[st]["entities"].add(u.get("entity_name", ""))
    for st, d in out.items():
        d["entity_count"] = len(d["entities"])
        del d["entities"]
    # also count manual_required
    for m in snap.get("manual_required", []):
        st = m.get("source_type", "?")
        if st not in out:
            out[st] = {"items": 0, "entity_count": 0, "manual": 0}
        out[st]["manual"] = out[st].get("manual", 0) + 1
    return out


def fmt_table(records: list[dict]) -> None:
    if not records:
        print("(no runs yet)")
        return
    print(f"{'run_at':<22} {'window':<24} {'jobs':>5} {'hits':>5} {'items':>6} {'manual':>6} {'err':>4} {'hit%':>6}")
    print("-" * 80)
    for r in records:
        win = f"{r.get('window_start','?')}..{r.get('window_end','?')}"
        rate = r.get("hit_rate", 0) * 100
        print(
            f"{r.get('run_at',''):<22} {win:<24} "
            f"{r.get('jobs_input',0):>5} {r.get('jobs_with_hits',0):>5} "
            f"{r.get('items_kept',0):>6} {r.get('manual',0):>6} "
            f"{r.get('errors',0):>4} {rate:>5.1f}%"
        )


def fmt_rolling(records: list[dict]) -> None:
    if len(records) < 2:
        return
    n = len(records)
    avg_hit = sum(r.get("hit_rate", 0) for r in records) / n * 100
    avg_items = sum(r.get("items_kept", 0) for r in records) / n
    avg_jobs = sum(r.get("jobs_input", 0) for r in records) / n
    print()
    print(f"-- rolling averages over last {n} runs --")
    print(f"  avg hit rate:     {avg_hit:5.1f}%")
    print(f"  avg items / run:  {avg_items:5.1f}")
    print(f"  avg jobs / run:   {avg_jobs:5.1f}")


def fmt_source_breakdown(latest: dict, snapshot_path: Path) -> None:
    bd = by_source_type(snapshot_path)
    if not bd:
        return
    print()
    print(f"-- latest run breakdown by source_type ({snapshot_path.name}) --")
    print(f"  {'source_type':<14} {'items':>6} {'entities':>9} {'manual':>7}")
    for st in sorted(bd.keys()):
        d = bd[st]
        print(f"  {st:<14} {d.get('items',0):>6} {d.get('entity_count',0):>9} {d.get('manual',0):>7}")


def fmt_reason_breakdown(latest: dict) -> None:
    """Show why fetchers came back empty. Reasons are coded `<fetcher>:<code>`."""
    reasons = latest.get("reason_counts") or {}
    if not reasons:
        return
    total = sum(reasons.values()) or 1
    print()
    print(f"-- latest run reason codes ({total} jobs total) --")
    # split successful vs unsuccessful
    ok_codes = {k: v for k, v in reasons.items() if k.endswith(":ok")}
    miss_codes = {k: v for k, v in reasons.items() if not k.endswith(":ok")}

    def _print_block(title: str, codes: dict[str, int]) -> None:
        if not codes:
            return
        print(f"  {title}:")
        for code, n in sorted(codes.items(), key=lambda kv: -kv[1]):
            pct = 100 * n / total
            print(f"    {code:<32} {n:>5} ({pct:4.1f}%)")

    _print_block("hits", ok_codes)
    _print_block("misses (why)", miss_codes)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--path", default=str(DEFAULT_STATS))
    p.add_argument("--last", type=int, default=10)
    p.add_argument("--by-source-type", action="store_true",
                   help="show source_type breakdown for the most recent snapshot")
    args = p.parse_args(argv)

    stats_path = Path(args.path)
    records = load_stats(stats_path)[-args.last:]
    fmt_table(records)
    fmt_rolling(records)

    if records:
        # Always show the latest run's reason breakdown — that's the new
        # observability we wanted from P1.
        fmt_reason_breakdown(records[-1])
    if args.by_source_type and records:
        snap = Path(records[-1].get("snapshot_path", ""))
        fmt_source_breakdown(records[-1], snap)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
