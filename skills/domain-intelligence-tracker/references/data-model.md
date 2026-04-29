# Data Model

Use this model when turning a watchlist into a structured tracking system.

## Core Tables

### 1. `entities`

The main object list.

Suggested fields:
- `id`
- `domain`
- `entity_group`
- `name`
- `rank`
- `status`          — one of `active` / `inactive` / `retired`
- `retired_at`      — required when `status == "retired"`; ISO date (YYYY-MM-DD)
- `description`
- `official_url`
- `created_at`
- `updated_at`

Examples of `entity_group`:
- `person`
- `company`
- `product`
- `institution`
- `project`
- `lab` / `brand` / `creator` / `standards body` / `open-source project` / `dataset` / `method`

#### Status semantics

| Status | Meaning | When to use |
|---|---|---|
| `active` | Entity is currently producing first-party signals | Default for new additions |
| `inactive` | Entity exists but has gone quiet — still worth monitoring | Public absence for >30 days without formal closure |
| `retired` | Entity is archived — no longer tracked | Person left role / company shut / product deprecated. Set `retired_at`. Do NOT delete the row — retention is how diff_snapshots.py can explain removals to downstream consumers. |

A `status == retired` row should remain in the entity list so that `scripts/diff_snapshots.py` reports a `status_changed` event instead of a false `removed`.

### 2. `entity_sources`

The source directory for each entity.

Suggested fields:
- `id`
- `entity_id`
- `source_type`
- `platform`
- `label`
- `url`
- `is_official`
- `is_primary`
- `notes`
- `last_checked_at`

Examples of `source_type`:
- `website`
- `blog`
- `newsroom`
- `x`
- `youtube`
- `docs`
- `github`
- `discord`
- `reddit`
- `forum`
- `linkedin`
- `changelog`
- `release-notes`
- `podcast`
- `newsletter`
- `press`

At most **one** source per entity should carry `is_primary: true`. `scripts/validate_snapshot.py` enforces this.

### 3. `entity_updates`

The time-bounded content stream.

Suggested fields:
- `id`
- `entity_id`
- `person_name` or `entity_name`     — required
- `entity_group`                       — required
- `published_at`                       — required, ISO-8601, must fall in window
- `source_platform`                    — required
- `source_url`                         — required, http(s); used as uniqueness key
- `title`                              — required
- `summary`                            — **optional**. Many sitemap-derived rows have no `og:description`; the validator does not reject empty `summary`. `enrich.py` fills it from `og:description` when available. Downstream consumers should fall back to `title` when `summary` is empty.
- `content_type`                       — enum: `post / blog / news / product / release-notes / announcement / engineering / essay / paper / policy / podcast / press / talk / interview / video / docs / changelog / research`
- `source_domain`                      — derived from `source_url`
- `is_official`                        — boolean; true if first-party
- `raw_source`                         — JSONB blob: publisher / published_label / evidence
- `collected_at`                       — ISO-8601

Recommended uniqueness:
- `source_url`
or
- `entity_id + source_url`

`scripts/dedupe_updates.py` collapses duplicates by `source_url`, preferring the earliest `collected_at` (or earliest `published_at` when `collected_at` is missing) as the canonical record.

### 4. `collection_runs`

Metadata for the collection job itself.

Suggested fields:
- `id`
- `domain`
- `goal`
- `window_start`
- `window_end`
- `entity_scope`
- `source_policy`
- `output_tables`
- `notes`
- `started_at`
- `finished_at`

## Practical Shapes

### Minimum viable setup

If you need speed:
- `entities`
- `entity_updates`

### Recommended setup

For ongoing tracking:
- `entities`
- `entity_sources`
- `entity_updates`
- `collection_runs`

## Table Naming: generic ↔ Supabase

The generic names above (`entities`, `entity_sources`, etc.) are the **editorial** names used in this skill's docs and templates. When the data is synced into Supabase via `tools/supabase_sync.py`, the target table names are **domain-prefixed**:

| Generic (this skill) | Supabase live table | Notes |
|---|---|---|
| `entities` | `ai_tracking_entities` | Domain-prefixed to allow multi-domain co-tenancy |
| `entity_updates` | `ai_tracking_person_updates` | Legacy name; covers all entity types despite "person" suffix |
| `entity_sources` | `ai_tracking_entity_sources` | Added when source normalization was needed |
| `collection_runs` | `ai_tracking_collection_runs` | |

When tracking a domain other than AI, the convention is `<domain>_tracking_*` — e.g. `lca_tracking_entities`. See `tools/sync_configured_domains.py` for the dispatch.

## Notes

- Keep entity identity stable across collection runs.
- Store source URLs even when you also store summaries.
- Distinguish `official`, `community`, and `media`.
- Store exact dates, not only phrases like `this week`.
- A retired entity stays in the table; it is not deleted.
- Uniqueness in `entity_updates` is enforced by `source_url` at the scripts layer (`dedupe_updates.py`) and should also be declared at the Supabase schema layer.
