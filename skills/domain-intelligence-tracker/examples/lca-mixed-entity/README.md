# LCA Mixed-Entity Sample

This example validates that `domain-intelligence-tracker` generalizes beyond AI.

## Why LCA is a good test

LCA shifts the signal structure:

- people matter, but official updates often come from institutions and software teams
- products and databases matter as much as companies
- docs, release notes, training pages, and methodology announcements are often more useful than social posts

That makes LCA a strong contrast case for the skill.

## What this sample contains

- `lca-entities-2026-04-14.json`
  A mixed watchlist with people, companies, products, institutions, and projects
- `lca-updates-2026-04-14.json`
  A time-bounded official update snapshot for `2026-03-01` through `2026-04-14`
- `lca-collection-run-2026-04-14.json`
  A sample collection-run record showing scope and source policy

## What this demonstrates

The core workflow stays the same:

1. define the field
2. build a ranked watchlist
3. collect verified source links
4. collect updates in a fixed date range
5. prepare database-ready output

But the source mix changes:

- AI tends to favor `X + newsroom + product launch pages`
- LCA tends to favor `docs + release notes + webinars + methodology pages + institutional news`

That difference is the point of the sample.
