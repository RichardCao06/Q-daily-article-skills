# Workflow Examples

These examples show how the workflow can be applied.

## Example 1: AI Domain Tracking

### Goal

Track the most important AI people, companies, and products.

### Step A: Build the watchlist

Create ranked lists such as:
- top 20 people
- top 20 companies
- top 20 products

### Step B: Build the source directory

For each entity collect:
- official website
- official blog or newsroom
- X
- YouTube
- Reddit
- Discord
- other high-signal official links

### Step C: Collect updates

Choose a window like `2026-04-07` through `2026-04-14`.

Then gather:
- official posts
- official news pages
- official product updates

To help organize the fan-out, use the job-file generator:

```
python3 scripts/collect_updates.py \
    examples/ai-watchlist/ai-entities-2026-04-20.json \
    --window-start 2026-04-22 --window-end 2026-04-23 \
    --output /tmp/ai-collection-jobs.json
```

The job file lists every `(entity, source)` pair to check in the window.

### Auto-collect (default — full pipeline in 4 commands)

```
# 1. Generate jobs (deterministic)
python3 scripts/collect_updates.py \
    examples/ai-watchlist/ai-entities-2026-04-20.json \
    --window-start 2026-04-22 --window-end 2026-04-24 \
    --output /tmp/ai-collection-jobs.json

# 2. Execute in parallel — hard 10-min budget
python3 scripts/execute_jobs.py /tmp/ai-collection-jobs.json \
    --output examples/ai-watchlist/ai-updates-2026-04-24.json \
    --cache  .cache/executor-ai.json \
    --max-workers 12 --per-job-timeout 15 --budget 600 \
    --include-manual

# 3. Backfill title / summary for sitemap-derived rows
python3 scripts/enrich.py examples/ai-watchlist/ai-updates-2026-04-24.json --sleep 0.2

# 4. Validate → dedupe → (optional diff) → sync to data_collect
python3 scripts/run_collection.py \
    --entities examples/ai-watchlist/ai-entities-2026-04-20.json \
    --updates  examples/ai-watchlist/ai-updates-2026-04-24.json \
    --run      examples/ai-watchlist/ai-collection-run-2026-04-24.json \
    --database-url "$COLLECT_DATABASE_URL"
```

Routing inside `execute_jobs.py`:
- `blog` / `newsroom` / `podcast` / `youtube` / `reddit` → `RssFetcher` (with `<link rel="alternate">` discovery + 4-path probe fallback)
- `github` / `release-notes` → `GitHubReleasesFetcher` (with org-URL fallback that walks top 5 repos; set `$GITHUB_TOKEN` for 5000 req/h)
- `website` / `docs` / `changelog` → `SitemapFetcher` first, `HtmlDatedFetcher` fallback
- `x` / `linkedin` / `discord` → no programmatic fetcher → emitted to `snapshot.manual_required[]` for human follow-up

Real numbers (60-entity AI watchlist, 265 jobs):

```
wall-clock:        6 min 49 sec
hit rate:          11.3%   (40 fetched of 209 chained jobs; 56 manual)
items kept:        112
entity coverage:   22 / 60
job_timeout:       12     ← caught hung connections without freezing the run
budget exceeded:   0
```

After step 4 the snapshot is in `data_collect.entity_updates`. The frontend mirror in `daily.entity_updates` is populated by a separate pipeline (not in this repo).

### Hand-run by Claude (ad-hoc / breaking news)

For days where editorial judgment matters more than coverage, Claude in-session can run a few broad WebSearch queries and write the snapshot JSON by hand. Skip `execute_jobs.py` and `enrich.py` for that mode; jump straight to `run_collection.py`.

### Cron template (auto mode, daily at 08:00)

```
# /etc/crontab or `crontab -e`
QDAILY_ROOT=/Users/shujudagongren/Documents/learnspace/qdaily-backup
0 8 * * * cd $QDAILY_ROOT && set -a && . .env.local && set +a && \
  TODAY=$(date +%F) && \
  ENT=skills/domain-intelligence-tracker/examples/ai-watchlist/ai-entities-2026-04-20.json && \
  WL=skills/domain-intelligence-tracker/examples/ai-watchlist && \
  python3 skills/domain-intelligence-tracker/scripts/collect_updates.py $ENT \
      --window-start $TODAY --window-end $TODAY --output /tmp/ai-jobs-$TODAY.json && \
  python3 skills/domain-intelligence-tracker/scripts/execute_jobs.py /tmp/ai-jobs-$TODAY.json \
      --output $WL/ai-updates-$TODAY.json --cache .cache/executor-ai.json \
      --max-workers 12 --per-job-timeout 15 --budget 600 --include-manual && \
  python3 skills/domain-intelligence-tracker/scripts/enrich.py $WL/ai-updates-$TODAY.json --sleep 0.2 && \
  python3 skills/domain-intelligence-tracker/scripts/run_collection.py \
      --entities $ENT --updates $WL/ai-updates-$TODAY.json \
      --run      $WL/ai-collection-run-$TODAY.json \
      --database-url "$COLLECT_DATABASE_URL"
```

Watch the rolling stats and watchlist quality:

```
python3 scripts/view_run_stats.py --last 14 --by-source-type
python3 scripts/watchlist_hygiene.py $WL/ai-updates-$TODAY.json --reasons rss:feed_empty,rss:fetch_error_403
```

### Step D: Validate before syncing

Before any Supabase write, run the snapshot validators:

```
python3 scripts/validate_snapshot.py examples/ai-watchlist/ai-entities-2026-04-20.json
python3 scripts/validate_snapshot.py examples/ai-watchlist/ai-updates-2026-04-23.json
python3 scripts/dedupe_updates.py examples/ai-watchlist/ai-updates-2026-04-23.json --in-place
```

For a week-over-week view:

```
python3 scripts/diff_snapshots.py \
    examples/ai-watchlist/ai-entities-2026-04-14.json \
    examples/ai-watchlist/ai-entities-2026-04-20.json
```

### Step E: Sync to Supabase

In this project the AI workflow used:
- `public.ai_tracking_entities`
- `public.ai_tracking_person_updates`

Supporting files:
- `/Users/shujudagongren/Documents/learnspace/qdaily-backup/ai-tracking-directory-2026-04-14.md`
- `/Users/shujudagongren/Documents/learnspace/qdaily-backup/data/ai-person-weekly-updates-2026-04-14.json`
- `/Users/shujudagongren/Documents/learnspace/qdaily-backup/tools/supabase_sync.py`

For multi-domain batch sync, use the config-driven entry point:

```
python3 tools/sync_configured_domains.py --print-only
python3 tools/sync_configured_domains.py --database-url $DATABASE_URL
```

### Step F: Route into editorial writing

If the goal shifts from monitoring to article writing, use the
`updates_to_news_brief.py` bridge to feed the
[daily-article-editor](../../daily-article-editor/) skill:

```
# tracker update snapshot → news-brief markdown draft
python3 scripts/updates_to_news_brief.py \
    examples/ai-watchlist/ai-updates-2026-04-23.json \
    --entity-snapshot examples/ai-watchlist/ai-entities-2026-04-20.json \
    --bucketing top_plus \
    --output /tmp/daily-brief-2026-04-23.md

# news-brief markdown → editorial package (via the editor skill)
python3 ../daily-article-editor/scripts/build_article_package.py \
    /tmp/daily-brief-2026-04-23.md
```

The editor skill's classifier should report:
- `article_type: news-brief`
- `article_subtype: bucketed`
- `structure: [标题列合, 标准 dek, Top / 重点板块, 区域板块, Also in the News, ...]`

Alternative bucketing strategies for `updates_to_news_brief.py`:
- `by_group` — buckets are `公司动态`, `产品动态`, `人事动态`, ...
- `by_official` — splits into `官方动态` vs `其他`
- `top_plus` — default; mirrors Qdaily's Top / 东八区 / Also in the News layout

## Example 2: Another Domain

Suppose the domain is `climate software`.

You might track:
- people: founders, researchers, policy operators
- companies: software vendors, marketplaces, MRV platforms
- products: climate reporting tools, carbon accounting tools, data platforms

Then the workflow stays the same:
- build the ranked list
- collect source links
- define the update window
- validate + dedupe
- store entities and updates

## Example 3: Narrow Technical Topic

Suppose the domain is `vector databases`.

Entity groups could be:
- companies
- products
- open-source projects

The best sources might shift toward:
- docs
- changelogs
- GitHub releases
- engineering blogs

The workflow still stays the same.

## Example 4: LCA Mixed-Entity Tracking

Lifecycle assessment is a useful stress test for this skill because the signal mix differs from AI.

In this project, see:
- `/Users/shujudagongren/Documents/learnspace/qdaily-backup/skills/domain-intelligence-tracker/examples/lca-mixed-entity/README.md`
- `/Users/shujudagongren/Documents/learnspace/qdaily-backup/skills/domain-intelligence-tracker/examples/lca-mixed-entity/lca-entities-2026-04-14.json`
- `/Users/shujudagongren/Documents/learnspace/qdaily-backup/skills/domain-intelligence-tracker/examples/lca-mixed-entity/lca-updates-2026-04-14.json`
- `/Users/shujudagongren/Documents/learnspace/qdaily-backup/skills/domain-intelligence-tracker/examples/lca-mixed-entity/lca-collection-run-2026-04-14.json`

This sample shows:
- mixed entity groups instead of only people/companies/products
- official docs and release notes outranking social content
- institutions and methodology projects as first-class tracked objects

## Example 5: Scoring a Watchlist Refresh

When deciding which entities to add, drop, or re-rank, run `score_entities.py`
against the current snapshot:

```
python3 scripts/score_entities.py \
    examples/ai-watchlist/ai-entities-2026-04-20.json \
    --weights signal=3,influence=2,output=2,ecosystem=1,near_term=2
```

The script emits a scored and re-ranked entity list to stdout (not to the
snapshot file). The author decides what to accept and which re-ranks to apply.
