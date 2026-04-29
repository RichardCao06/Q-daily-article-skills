#!/usr/bin/env python3
"""Run a jobs.json (from collect_updates.py) end-to-end.

For each (entity, source) job, dispatches to the right fetcher and collects
items whose `published_at` falls inside the job's window. Output is a
ready-to-sync `update-snapshot.json`.

Usage:
    python3 execute_jobs.py <jobs.json> \\
        --output  ai-updates-YYYY-MM-DD.json \\
        --cache   .cache/executor-ai.json \\
        [--max-per-source 10]   # cap items emitted per source
        [--max-jobs 0]          # cap total jobs (0 = unlimited)
        [--source-types blog,newsroom,github,...]   # filter
        [--include-manual]      # also emit `manual_required` placeholder records

Coverage caveat: source types `x`, `linkedin`, `discord` have no programmatic
fetcher. They appear in the output's `manual_required` array so you can
fill them in by hand.

Exit code 0 even when some jobs fail — failures are recorded inline. The
final summary is printed to stderr.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import executor_cache  # noqa: E402
from fetchers import FetchResult, fetcher_chain_for  # noqa: E402


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fetchresult_to_update(
    fr: FetchResult,
    job: dict,
) -> dict[str, Any]:
    return {
        "entity_group":    job["entity_group"],
        "entity_name":     job["entity_name"],
        "published_at":    fr.published_at,
        "source_platform": job["source_type"],
        "source_url":      fr.source_url,
        "title":           fr.title,
        "summary":         fr.summary,
        "content_type":    fr.content_type,
        "source_domain":   fr.source_domain,
        "is_official":     bool(job.get("is_official")),
        "collected_at":    _now_iso(),
        "raw_source": {
            "publisher":       fr.publisher,
            "published_label": fr.raw_label,
            "feed_source":     job["url"],
        },
    }


def _walk_chain_for_job(job: dict, cache_for_url: dict, window_start: str, window_end: str):
    """Walk the fetcher chain for one job; return (items, new_cache_state,
    reasons_for_job, last_err). This runs on a worker thread.
    """
    items: list[FetchResult] = []
    new_cache_state: dict[str, Any] = {}
    reasons_for_job: list[str] = []
    last_err: str | None = None
    chain = fetcher_chain_for(job.get("source_type", ""))
    for FetcherCls in chain:
        try:
            fetcher = FetcherCls()
            items, new_cache_state, reason = fetcher.fetch(
                job.get("url", ""), window_start, window_end,
                cache_for_url=cache_for_url,
            )
            reasons_for_job.append(reason)
            if items:
                last_err = None
                break
        except Exception as e:  # noqa: BLE001
            last_err = f"{FetcherCls.__name__}: {type(e).__name__}: {str(e)[:160]}"
            reasons_for_job.append(f"{FetcherCls.name}:exception")
            continue
    return (items, new_cache_state, reasons_for_job, last_err)


def execute(
    jobs_doc: dict,
    cache: dict,
    *,
    max_per_source: int = 10,
    max_jobs: int = 0,
    allowed_source_types: set[str] | None = None,
    include_manual: bool = True,
    max_workers: int = 12,
    per_job_timeout: float = 15.0,
    overall_budget_s: float = 600.0,
) -> dict[str, Any]:
    """Run all jobs in parallel via ThreadPoolExecutor.

    Performance contract:
      - max_workers (default 12) sets concurrency. Each thread owns its own
        HTTP socket; cache mutations are serialized via lock.
      - per_job_timeout (default 15s) is a HARD ceiling on a single job's
        wall time. Hung TCP connections that survive socket-level timeout
        get killed by the future-level timeout, recorded as
        `executor:job_timeout` in diagnostics.
      - overall_budget_s (default 600s = 10 min) is a global wall-clock
        deadline. Once we cross it, all pending futures are cancelled and
        unfinished jobs are recorded as `executor:budget_exceeded`.
    """
    domain = jobs_doc.get("domain", "")
    window_start = jobs_doc.get("window_start", "")
    window_end = jobs_doc.get("window_end", "")
    jobs = jobs_doc.get("jobs", [])
    if max_jobs:
        jobs = jobs[:max_jobs]

    updates: list[dict] = []
    manual_required: list[dict] = []
    failures: list[dict] = []
    diagnostics: list[dict] = []
    seen_urls: set[str] = set()
    stats = {
        "total_jobs":       len(jobs),
        "fetched_jobs":     0,
        "skipped_no_chain": 0,
        "manual_required":  0,
        "errors":           0,
        "items_kept":       0,
        "reason_counts":    {},
        "max_workers":      max_workers,
        "per_job_timeout":  per_job_timeout,
    }
    cache_lock = threading.Lock()

    # Pre-pass: pull manual-required jobs off the queue (they don't need fetching)
    fetch_jobs: list[dict] = []
    for job in jobs:
        source_type = job.get("source_type", "")
        if allowed_source_types and source_type not in allowed_source_types:
            continue
        if not job.get("url"):
            continue
        chain = fetcher_chain_for(source_type)
        if not chain:
            stats["manual_required"] += 1
            if include_manual:
                manual_required.append({
                    "entity_group":  job.get("entity_group"),
                    "entity_name":   job.get("entity_name"),
                    "source_type":   source_type,
                    "url":           job.get("url"),
                    "reason":        f"no programmatic fetcher for source_type='{source_type}'",
                })
            continue
        fetch_jobs.append(job)

    deadline = datetime.now(timezone.utc).timestamp() + overall_budget_s

    def _record_diagnostic(job: dict, reason: str, all_reasons: list[str]) -> None:
        stats["reason_counts"][reason] = stats["reason_counts"].get(reason, 0) + 1
        diagnostics.append({
            "entity_name": job.get("entity_name"),
            "source_type": job.get("source_type", ""),
            "url":         job.get("url", ""),
            "last_reason": reason,
            "all_reasons": all_reasons,
        })

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_job = {}
        for job in fetch_jobs:
            with cache_lock:
                cache_for_url = executor_cache.entry_for(cache, job["url"])
            fut = pool.submit(
                _walk_chain_for_job, job, cache_for_url, window_start, window_end,
            )
            future_to_job[fut] = job

        for fut in list(future_to_job.keys()):
            job = future_to_job[fut]
            now = datetime.now(timezone.utc).timestamp()
            remaining = deadline - now
            if remaining <= 0:
                fut.cancel()
                _record_diagnostic(job, "executor:budget_exceeded", ["executor:budget_exceeded"])
                continue
            wait = min(per_job_timeout, max(remaining, 1.0))
            try:
                items, new_cache_state, reasons_for_job, last_err = fut.result(timeout=wait)
            except FutureTimeout:
                fut.cancel()
                _record_diagnostic(job, "executor:job_timeout", ["executor:job_timeout"])
                continue
            except Exception as e:  # noqa: BLE001
                _record_diagnostic(job, "executor:exception", [f"executor:{type(e).__name__}"])
                stats["errors"] += 1
                failures.append({
                    "entity_name": job.get("entity_name"),
                    "source_type": job.get("source_type", ""),
                    "url":         job.get("url", ""),
                    "error":       f"{type(e).__name__}: {str(e)[:160]}",
                })
                continue

            last_reason = reasons_for_job[-1] if reasons_for_job else "no_chain_walked"
            _record_diagnostic(job, last_reason, reasons_for_job)

            if last_err and not items:
                stats["errors"] += 1
                failures.append({
                    "entity_name": job.get("entity_name"),
                    "source_type": job.get("source_type", ""),
                    "url":         job.get("url", ""),
                    "error":       last_err,
                })

            if new_cache_state:
                with cache_lock:
                    executor_cache.update_entry(cache, job["url"], new_cache_state)

            kept_for_this_source = 0
            for fr in items:
                if fr.source_url in seen_urls:
                    continue
                seen_urls.add(fr.source_url)
                updates.append(_fetchresult_to_update(fr, job))
                kept_for_this_source += 1
                if kept_for_this_source >= max_per_source:
                    break

            if items:
                stats["fetched_jobs"] += 1
                stats["items_kept"] += kept_for_this_source

    snapshot: dict[str, Any] = {
        "domain":       domain,
        "window_start": window_start,
        "window_end":   window_end,
        "updates":      updates,
    }
    if include_manual and manual_required:
        snapshot["manual_required"] = manual_required
    if failures:
        snapshot["failures"] = failures
    if diagnostics:
        snapshot["diagnostics"] = diagnostics

    return {"snapshot": snapshot, "stats": stats}


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("jobs", help="jobs.json from collect_updates.py")
    p.add_argument("--output", required=True, help="path to write update-snapshot.json")
    p.add_argument("--cache", default=".cache/executor.json", help="executor cache path")
    p.add_argument("--max-per-source", type=int, default=10)
    p.add_argument("--max-jobs", type=int, default=0)
    p.add_argument("--source-types", default="", help="comma-separated source_type allowlist")
    p.add_argument("--include-manual", action="store_true",
                   help="also emit a manual_required[] block in the snapshot")
    p.add_argument("--max-workers", type=int, default=12,
                   help="concurrent fetcher threads (default 12)")
    p.add_argument("--per-job-timeout", type=float, default=15.0,
                   help="hard wall-clock ceiling per job in seconds (default 15)")
    p.add_argument("--budget", type=float, default=600.0,
                   help="overall wall-clock budget in seconds (default 600 = 10min)")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    jobs_path = Path(args.jobs)
    if not jobs_path.exists():
        print(f"missing jobs file: {args.jobs}", file=sys.stderr)
        return 2
    jobs_doc = json.loads(jobs_path.read_text(encoding="utf-8"))

    cache_path = Path(args.cache)
    cache = executor_cache.load(cache_path)
    cache["domain"] = jobs_doc.get("domain", "")

    allowed = None
    if args.source_types:
        allowed = {s.strip() for s in args.source_types.split(",") if s.strip()}

    result = execute(
        jobs_doc, cache,
        max_per_source=args.max_per_source,
        max_jobs=args.max_jobs,
        allowed_source_types=allowed,
        include_manual=args.include_manual,
        max_workers=args.max_workers,
        per_job_timeout=args.per_job_timeout,
        overall_budget_s=args.budget,
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(result["snapshot"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    executor_cache.save(cache_path, cache)

    # Append a one-line stats record so we can chart hit rate over time.
    s = result["stats"]
    stats_path = cache_path.parent / "run-stats.jsonl"
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    stats_record = {
        "run_at":         _now_iso(),
        "domain":         jobs_doc.get("domain", ""),
        "window_start":   jobs_doc.get("window_start", ""),
        "window_end":     jobs_doc.get("window_end", ""),
        "jobs_input":     s["total_jobs"],
        "jobs_with_hits": s["fetched_jobs"],
        "items_kept":     s["items_kept"],
        "manual":         s["manual_required"],
        "errors":         s["errors"],
        "hit_rate":       round(s["fetched_jobs"] / s["total_jobs"], 3) if s["total_jobs"] else 0,
        "reason_counts":  dict(s.get("reason_counts", {})),
        "snapshot_path":  str(out_path),
    }
    with stats_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(stats_record, ensure_ascii=False) + "\n")

    print(json.dumps(s, indent=2), file=sys.stderr)
    print(
        f"wrote {len(result['snapshot']['updates'])} updates → {out_path} "
        f"(cache: {cache_path}; stats: {stats_path})",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
