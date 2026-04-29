---
name: domain-intelligence-tracker
description: Use when building or maintaining a watchlist for a specific domain, collecting official source links for people or organizations, tracking recent updates over time, or syncing structured monitoring results into Supabase. Includes scripts for snapshot validation, diffing, deduplication, scoring, collection job generation, and a bridge to the daily-article-editor skill's news-brief type.
---

# Domain Intelligence Tracker

## Overview

This skill is for repeatable domain monitoring.

Use it to move from a vague topic like `AI`, `robotics`, `biotech`, `climate`, or `consumer apps`
to a structured tracking system with:

1. a ranked entity list
2. a verified source directory
3. a time-bounded update snapshot
4. a database-ready sync output
5. a publish-ready news-brief draft (optional, via the editor-skill bridge)

The core rule is simple:

**track by source quality, not by noise**

## When to Use

Use this skill when:
- the user wants a watchlist for a field, market, technology, or ecosystem
- the task includes people, companies, products, labs, institutions, or projects to monitor
- the user wants official links such as websites, blogs, X, YouTube, Discord, Reddit, LinkedIn, GitHub, or docs
- the user wants recent updates over a fixed time window such as `last 7 days` or `last 30 days`
- the result should be stored in a structured file, table, or Supabase database
- the user wants to turn a weekly tracker run into a daily-brief article

Do not use this skill when:
- the user only wants a one-off recommendation with no tracking system
- the task is purely community sentiment tracking with no need for official-source validation
- the user already provided the exact source dataset and only wants summarization

## Workflow

### 1. Define the Tracking Frame

Lock these choices first:
- domain
- entity types
- ranking logic
- geography or language scope
- time window
- source-quality standard

Typical entity groups: `person` / `company` / `product` / `institution` / `project`. See `references/domain-adaptation.md` for more.

### 2. Build the Watchlist

Create a ranked list of the entities that matter most for the chosen domain.

For a semi-automated re-rank:

```
python3 scripts/score_entities.py <entity-snapshot.json> \
    [--weights signal=3,influence=2,output=2,ecosystem=1,near_term=2] \
    [--group person|company|product|...]
```

The script scores each entity on 5 dimensions (documented in `references/research-rules.md` #1) and proposes a new rank within its group. Authors decide which re-ranks to accept.

### 3. Build the Source Directory

For each entity, collect the highest-signal official and near-official sources.

Prioritize:
1. official website
2. official blog or newsroom
3. official X
4. official YouTube
5. official docs or changelog
6. official GitHub, forum, Discord, LinkedIn, or help center
7. high-signal community sources only when clearly labeled as community

Use `references/research-rules.md`.

### 4. Generate the Collection Plan

Lay out the fan-out deterministically:

```
python3 scripts/collect_updates.py <entity-snapshot.json> \
    --window-start 2026-04-22 --window-end 2026-04-24 \
    [--include-community] \
    [--group <entity_group>] \
    [--output jobs.json]
```

Each job contains an `(entity, source)` pair, suggested fetch queries, a fetch hint, and a template for the expected update record.

### 4b. Execute the Plan — Auto-Collect (preferred)

`execute_jobs.py` runs every job in parallel against the right fetcher and writes a ready-to-sync update snapshot. This is the default path — use it daily.

```
python3 scripts/execute_jobs.py jobs.json \
    --output snapshot.json \
    --cache .cache/executor-ai.json \
    --max-workers 12 \
    --per-job-timeout 15 \
    --budget 600 \
    --include-manual
```

**Performance contract (enforced by the executor)**:

| Knob | Default | Effect |
|---|---|---|
| `--max-workers` | 12 | Concurrent fetcher threads |
| `--per-job-timeout` | 15s | Hard wall-clock cap per (entity, source). Future is cancelled past it; reason logged as `executor:job_timeout` |
| `--budget` | 600s = 10 min | Global wall-clock deadline. Pending futures cancelled past it; reason `executor:budget_exceeded` |
| `--max-per-source` | 5 | Cap items emitted per source URL |

Underlying HTTP timeouts are tighter than per-job:
- `base.http_get` default: **4s**
- `SitemapFetcher`: **4s** per candidate, with **same-host first-timeout circuit breaker** that abandons remaining candidates immediately
- `_try_common_feed_paths` (the RSS path probe): **3s** per candidate, **4 candidates max** (`/feed`, `/rss.xml`, `/atom.xml`, `/index.xml`)
- 403/429 → automatic single retry with browser User-Agent (Cloudflare-style blocks)

Real-world numbers on the AI watchlist (60 entities × ~4 sources = 265 jobs):

```
wall-clock:        6:49
hit rate:          11.3%   (fetched_jobs / total_jobs)
items kept:        112
entity coverage:   22 / 60
manual_required:   56     (x / linkedin / discord — no public API)
job_timeout:       12     (slow sites caught by 15s cap, not freezing the run)
budget exceeded:   0
```

If a run takes much longer than ~7 min on the same watchlist, suspect either a regressed timeout or a flaky local network. Kill and rerun.

### 4c. (Alternative) Manual Collect via Claude

If editorial judgment matters more than coverage, Claude in-session can run a few broad WebSearch queries and write the snapshot JSON by hand. Use this for breaking-news days; the auto-collect for routine runs.

### 5. Enrich + Validate Before Syncing

Sitemap-derived rows arrive with empty `title` / `summary` (sitemap.xml doesn't carry them). Run `enrich.py` to fill them from each source URL's `og:title` / `og:description`:

```
python3 scripts/enrich.py snapshot.json --sleep 0.2
```

Then validate, dedupe, and (optionally) diff:

```
python3 scripts/validate_snapshot.py snapshot.json
python3 scripts/dedupe_updates.py    snapshot.json --in-place
python3 scripts/diff_snapshots.py    previous.json snapshot.json
```

Validator enforces:
- `YYYY-MM-DD` dates on `snapshot_date` / `window_start` / `window_end`
- window containment on `published_at`
- `source_url` uniqueness within `updates[]`
- at most one `is_primary: true` source per entity
- `retired_at` required when `status == "retired"`
- `entity_group` / `source_type` / `content_type` from allowed lists
- `title` is required; **`summary` is optional** (sitemap-only rows often lack `og:description`)

### 5b. Observability — Hit Rate + Diagnostics

Every `execute_jobs.py` invocation appends one line to `<cache_dir>/run-stats.jsonl` plus a `diagnostics[]` array inside the snapshot. Each diagnostic carries a structured reason code in the form `<fetcher>:<code>` so you can see WHY a source returned 0 items.

```
python3 scripts/view_run_stats.py --last 14
python3 scripts/view_run_stats.py --by-source-type   # latest run by platform
```

Reason-code grammar (all documented at the top of each fetcher module):

```
rss:ok | rss:not_modified | rss:no_feed_discovered | rss:not_a_feed |
rss:feed_empty | rss:no_items_in_window | rss:all_already_seen |
rss:fetch_error_<status>      ← e.g. rss:fetch_error_403, rss:fetch_error_timeout
rss:youtube_handle_unresolved
github:ok | github:not_a_repo_url | github:org_no_releases |
github:no_releases | github:no_items_in_window | github:api_error_<status>
sitemap:ok | sitemap:not_found | sitemap:empty | sitemap:no_lastmod |
sitemap:no_items_in_window | sitemap:all_already_seen
html:ok | html:fetch_error | html:empty_body | html:no_date | html:out_of_window
executor:job_timeout | executor:budget_exceeded
```

Persistent watchlist quality issues (e.g. dead URLs, sources that never publish in the window) surface as concentrated reason codes. To get a fix-list:

```
python3 scripts/watchlist_hygiene.py snapshot.json
python3 scripts/watchlist_hygiene.py snapshot.json --reasons rss:feed_empty,rss:fetch_error_403
python3 scripts/watchlist_hygiene.py snapshot.json --csv > stale-sources.csv
```

Hit rate guidelines:

- **≥ 70%** — most sources are reachable; watchlist is healthy
- **40 – 70%** — typical; some platforms blocked or quiet that day
- **10 – 40%** — current baseline; many watchlist URLs need cleanup (feed-empty / no-feed-discovered dominate)
- **< 10%** — investigate: rate-limit, broad CDN block, or executor timeout regression

### 6. Sync to Supabase

When the user wants persistence, there are **three** paths:

**A. One-shot wrapper (recommended for single domain)**

```
python3 scripts/run_collection.py \
    --entities examples/ai-watchlist/ai-entities-2026-04-20.json \
    --updates examples/ai-watchlist/ai-updates-2026-04-23.json \
    --run examples/ai-watchlist/ai-collection-run-2026-04-23.json \
    [--diff-against examples/ai-watchlist/ai-updates-2026-04-20.json] \
    --database-url $DATABASE_URL
```

The wrapper chains: validate → dedupe → (optional diff) → sync. If validation fails, sync does NOT run. Without `--database-url` it is effectively a dry-run.

**B. Multi-domain batch**

`tools/sync_configured_domains.py` reads `config/domains.json` and syncs every enabled domain. Good when you keep multiple domains (AI + LCA + …) in a single config.

```
python3 tools/sync_configured_domains.py --database-url $DATABASE_URL
```

**C. Raw building blocks**

Direct use of `tools/supabase_sync.py` — the lowest-level entry point. Used by both A and B under the hood.

Schemas live at:
- `/Users/shujudagongren/Documents/learnspace/qdaily-backup/supabase/ai_tracking_schema.sql`
- `/Users/shujudagongren/Documents/learnspace/qdaily-backup/supabase/ai_person_updates_schema.sql`

Generic table names map to domain-prefixed Supabase tables — see `references/data-model.md § Table Naming` for the mapping.

### 7. Verify Before Claiming Completion

Always verify:
- row counts
- sample records
- date coverage
- official-source attribution
- duplicate handling

### 8. Optional — Route Into Editorial Writing

If the goal shifts from monitoring to article writing, use the news-brief bridge to feed the [daily-article-editor](../daily-article-editor/) skill:

```
python3 scripts/updates_to_news_brief.py update.json \
    [--entity-snapshot entities.json] \
    [--bucketing top_plus|by_group|by_official] \
    [--top-rank-threshold 15] \
    [--output daily-brief.md]
```

The output conforms to the editor skill's `news-brief / bucketed` structure — it can be piped directly into `daily-article-editor/scripts/build_article_package.py`. See `references/workflow-examples.md § Step F`.

## Scripts

Located under `scripts/`:

| Script | Purpose |
|---|---|
| `validate_snapshot.py` | Schema validation for entity / update / collection-run snapshots; `--check-urls` for liveness pings |
| `diff_snapshots.py` | Compare two snapshots (added / removed / rank / status / source changes) |
| `dedupe_updates.py` | Collapse duplicate updates by `source_url`; preserves earliest `collected_at` |
| `score_entities.py` | Compute per-dimension scores and propose a new rank within each group |
| `collect_updates.py` | Generate a fan-out job file from an entity snapshot for a time window |
| `updates_to_news_brief.py` | Bridge: turn an update snapshot into a daily-article-editor news-brief draft |
| `run_collection.py` | One-shot wrapper: validate → dedupe → (optional diff) → sync to Supabase. Halts before sync on any validation error. |
| `execute_jobs.py` | **Auto-collector** — reads a jobs.json, dispatches each `(entity, source)` to the right fetcher, runs them on a 12-thread `ThreadPoolExecutor` with a 15s per-job hard cap and a 600s overall budget. Outputs a ready-to-sync update snapshot plus per-job diagnostics. Persists ETag + GUID cache to `.cache/executor-<domain>.json`. |
| `enrich.py` | Backfills `title` / `summary` on rows that have empty fields (typically sitemap-derived). Fetches each `source_url` once and extracts `og:title` + `og:description`. Idempotent; safe to re-run. |
| `view_run_stats.py` | Reads `<cache_dir>/run-stats.jsonl` and prints a hit-rate table + rolling averages + reason-code breakdown for the latest run. `--by-source-type` shows platform-level coverage. |
| `watchlist_hygiene.py` | **Run-time** hygiene. Walks `snapshot.diagnostics[]` and groups stale sources by reason code (`rss:feed_empty`, `rss:fetch_error_403`, …). Useful after an executor run when the snapshot still carries diagnostics. |
| `audit_watchlist.py` | **Pre-flight** hygiene. HEAD-checks every URL in the entity snapshot in parallel, classifies each one (`http_404` / `http_403` / `timeout` / `probable_landing_page` / `feed_ok` / `non_feed_platform`), and emits a Markdown report grouped by classification. Use this BEFORE running the executor — typical run on the AI watchlist surfaces ~75 sources pointed at brand homepages instead of feed URLs. Doesn't need diagnostics, doesn't need a recent run. |
| `score_topic_candidates.py` | After collection, ranks entity-clusters as topic candidates on signal density / freshness / source diversity, and flags Jaccard overlap against a recently-published-articles history file (`--history`). Output is a Markdown checklist that feeds the topic-card step in `topic-selection-and-routing.md`. Makes the "5 candidates from 112 updates" picking auditable instead of intuition-based. |
| `entity_lookup.py` | Cross-skill bridge to `daily-article-editor`. Given one entity name + the standard snapshot files, prints a Markdown research card containing official sources, recent updates, theme-neighbour entities, and prior-coverage articles. Use this during the editor's writing pass when you need to ground a claim or check for duplicate angles. |
| `fetchers/` | Pluggable source-type fetchers used by `execute_jobs.py`: `rss.py` (RSS 2.0 + Atom + YouTube/Reddit shortcuts + HTML feed-link discovery + 4-path probe fallback), `github_releases.py` (Releases API + org-URL fallback that walks top 5 repos), `sitemap.py` (sitemap.xml + sitemap-index, with same-host first-timeout circuit breaker), `html_dated.py` (HTML fallback that pulls `og:article:published_time` / `<time>` / JSON-LD). All stdlib-only. Source types `x` / `linkedin` / `discord` have no programmatic fetcher and are emitted to the snapshot's `manual_required[]` block. |

## References

- `references/data-model.md`
- `references/research-rules.md`
- `references/workflow-examples.md`
- `references/domain-adaptation.md`

## Assets

- `assets/entity-tracking-template.json`
- `assets/update-snapshot-template.json`
- `assets/collection-run-template.json`
- `config/domains.json`

## Tests

Located under `tests/` — **92 tests, all stdlib + `unittest.mock`, no network**:

- `test_validate_snapshot.py` — schema validation, `summary` is optional
- `test_diff_snapshots.py` — snapshot diffing
- `test_dedupe_updates.py` — update dedupe
- `test_score_entities.py` — entity scoring
- `test_collect_updates.py` — collection job generation
- `test_updates_to_news_brief.py` — editor-skill bridge structural tests
- `test_run_collection.py` — wrapper validate → dedupe → sync flow
- `test_fetchers.py` — RSS / Atom / GitHub / sitemap / HTML fetchers + reason codes (rss:not_a_feed, rss:youtube_handle_unresolved, github:org fallback, etc.)
- `test_execute_jobs.py` — parallel executor, per-job timeout, manual-required routing
- `test_http_get_retry.py` — 403/429 → browser-UA retry
- `test_enrich.py` — backfill of title/summary from `og:*` meta

Run all:

```
cd skills/domain-intelligence-tracker
python3 -m unittest discover tests
```

## Common Mistakes

- ranking by hype instead of signal
- mixing official and community links without labeling them
- treating media reports as if they were first-party sources
- using relative dates without pinning exact dates
- collecting updates with no time-window boundary
- storing summaries without the original source URL
- writing database rows that cannot be traced back to a source
- deleting retired entities instead of flipping `status` (breaks diff traceability)
- running a Supabase sync before `validate_snapshot.py` + `dedupe_updates.py` have passed
