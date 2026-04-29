---
name: daily-article-editor
description: Use when turning an existing long-form draft into a publishable article package with structure editing, image selection, captions, and markdown-ready layout in a Qdaily-like rhythm.
---

# Daily Article Editor

## Overview

This skill is a full editorial workflow for feature-style articles.
It covers four linked jobs:

1. shape the writing
2. choose the right images
3. deliver a clean markdown-ready article package
4. publish the article with Storage-backed media links when Supabase is the target CMS

The core rule is simple:

**edit by function, not by convenience**

That applies to paragraphs, images, captions, and layout.

## When to Use

Use this skill when:
- the draft already exists locally
- the piece is a profile, interview, brand story, feature, or explanatory article
- the user wants the article refined into something closer to a publishable newsroom draft
- the task includes any combination of writing, image planning, image sourcing, captions, or markdown layout

Do not use this skill when:
- the user only wants a single image
- the user only wants isolated copy edits with no editorial packaging
- the content must be invented from scratch as a fictional piece

## Workflow

### 1. Writing Pass

Read the full draft before changing anything.

If the material came from a tracked update set instead of a finished draft, first use the topic card and routing guide in `references/topic-selection-and-routing.md`.

When grounding a specific claim about an entity (a company, person, or product), call into the tracker's cross-skill bridge:

```
python3 ../domain-intelligence-tracker/scripts/entity_lookup.py "Anthropic" \
    --entities ../domain-intelligence-tracker/examples/ai-watchlist/ai-entities-2026-04-20.json \
    --updates  ../domain-intelligence-tracker/examples/ai-watchlist/ai-updates-2026-04-28.json \
    --history  /tmp/qdaily-history.json
```

It returns a Markdown card with official sources, recent first-party updates, theme-neighbour entities, and prior Q-daily coverage. Use it in two places:

1. During the writing pass to enrich a paragraph with a real source URL, instead of inventing or paraphrasing.
2. During the topic card step to detect already-published-on-this-entity overlap before you draft anything.

Decide:
- article type: `profile`, `interview`, or `feature`
- if `feature`, decide whether it is a broader trend feature or an event/news deep feature
- what the piece is really about
- where the opening, turn, evidence, and ending sit
- **column** (栏目): `good-article` / `good-take` / `good-grief` / `good-paper`
- **domain** (领域): `smart` / `business` / `design` / `fashion` / `entertainment` / `culture` / `gaming`

Column and domain are independent axes. See the "Two Routing Axes" section in
`references/topic-selection-and-routing.md`. The column says **what kind of
piece** this is (long-form / op-ed / shock-news / paper-driven); the domain
says **what topic field** it sits in.

Then edit for:
- title sharpness
- summary usefulness
- heading rhythm
- paragraph pacing
- ending restraint
- **column fit**: length band, opening style, voice, and image temperament must match the chosen column

Two reference files apply at this stage and BOTH must be consulted:
- `references/writing-style.md` — how each `article_type` (skeleton) is built
- `references/column-styles.md` — how each column (`好文章` / `好观点` / `好家伙` / `好论文`) should feel to read; per-column length, opening, voice, image rules
- `references/topic-selection-and-routing.md` — how to pick the column and topic in the first place

When the column's style sheet contradicts the article type's structure
(e.g., a long `feature` landing in `好家伙`), the **column wins**.

### News Feature Notes

For Qdaily-style event or news deep reports:
- do not open with generic industry background if there is a fresh triggering event
- use the first move as the door into a larger structural question
- organize the middle by mechanism and consequence, not by miscellaneous background
- keep the ending on what remains unresolved, constrained, or costly

Common `feature` submodes worth checking for:
- `event-news`
  - a fresh move, update, filing, removal, funding event, resignation, or announcement
- `policy-rules`
  - a policy text, developer rule, platform requirement, legal boundary, or enforcement change
- `company-shift`
  - a company changing strategy, product mix, budget allocation, distribution posture, or business direction
- `data-trend`
  - a number, report, ranking, comparison, or market statistic being used to explain a larger trend

### 2. Image Pass

Extract visual slots from the story.

The standard image workflow is source-only:
- fetch usable images from the cited source pages, official pages, or credible coverage pages
- allow only light editorial adjustment such as crop, resize, or mild tone correction
- do not generate title cards, synthetic covers, or AI-made explanatory images as part of the default flow
- choose the cover from the fetched source-image pool, not from a separately generated asset

Use slot types:
- `cover`
- `hero`
- `process`
- `object`
- `achievement`
- `archive`

Route each slot to the correct source pool instead of using one fixed source order.
Choose images by editorial fit, not source convenience.
Leave weak slots empty.

Use:
- `references/image-style.md`
- `references/image-source-priority.md`

### 3. Caption Pass

Write factual captions that do one job cleanly:
- identify
- contextualize
- attribute

Never write slogan-like captions.

### 4. Fact-Check Pass

Before any layout or publish work, run the fact-check pass.

For every claim in the article that contains a number, a date, a name, or
a quoted phrase, verify it against the literal source sentence (not a
headline, not a recap). Pay special attention to **denominators**: when
the source says `10%`, 10% of what? Sample frame, subset, or full
population?

Use `references/fact-check.md` for the full checklist and the four
verification questions (number / denominator / direction / time).

A piece does not advance to layout until every checklist item passes.
This pass exists because at least one published article shipped with a
denominator drift between the prose and the source — the failure mode is
silent, low-frequency, and erodes trust faster than any other kind of
editorial bug.

### 5. Layout Pass

Prepare a markdown-ready article:
- title
- summary
- images in the right places
- captions in a consistent format
- breathing room between text and images

Use `references/layout-style.md`.

### 6. Final Read Pass

Read the article from start to end **as a reader who has never seen the
topic card**.

The reader does not care which column hosts the article, doesn't know
about column-styles rules, and shouldn't see any sentence that talks
ABOUT the writing rather than ABOUT the subject. Catch:

- meta-commentary that survived the writing pass:
  "为什么这一篇值得在 `好论文` 栏目里发", "按 `好论文` 栏目的约束……",
  "这是好论文该有的样子", "this article", "in this column", and any
  heading or sentence that names the article-type ("data-piece",
  "explainer") inside the prose
- draft markers: `TODO`, `FIXME`, `XXX`, `HACK`, `WIP`, `占位符`,
  `[draft]`, lorem ipsum
- editor placeholders: `[insert quote here]`, `<author name>`,
  `{date}`, `[TBD]`, `[TKTK]`
- empty headings, empty list items
- unclosed `**bold` markers (a line with an odd count of `**`)

Two ways to run this pass:

```
# 1. Standalone scan, errors → exit 1, machine-readable JSON option
python3 scripts/validate_article.py <article.md>
python3 scripts/validate_article.py <article.md> --json
python3 scripts/validate_article.py <article.md> --strict   # CI mode

# 2. Automatically run as a pre-flight gate in publish_to_daily.py
python3 scripts/publish_to_daily.py <article.md> --execute
# Skip with --skip-content-check ONLY for metacritical pieces about
# Q-daily itself (the rare exception).
```

The full checklist + rationale lives in `references/final-read.md`.

This pass exists because at least one article shipped with the topic-card
scaffolding ("为什么这一篇值得在 `好论文` 栏目里发") still in the body.
Fact-check catches FACTUAL errors; layout catches STRUCTURAL errors;
neither catches "this still reads like notes". Hence: a dedicated pass.

### 7. Publish Pass

When the target is Q-daily / Supabase, do not stop at a local Markdown draft.

The default publish rule is:
- upload the chosen hero and inline images to Supabase Storage `article-media`
- rewrite `heroImage` and inline Markdown image URLs to the Storage public URLs
- sync the article row, `article_blocks`, `article_tags`, and `source_markdown` so the database matches the rewritten Markdown

In this project, use:
- `scripts/publish_qdaily_supabase.py <article.md> --database-url ... --temporary-open-upload-policy`

If you also keep a mirrored final draft outside Q-daily, pass it via:
- `--mirror-markdown <other-file.md>`

This publish step is complete only when:
- the uploaded objects are reachable through public Storage URLs
- `articles.hero_image_url` uses the Storage URL
- `article_blocks` image payloads use the Storage URLs
- `source_markdown` also reflects the rewritten URLs

## Scripts

- `scripts/build_article_package.py <draft.md>`
  Builds a combined package with writing guidance, image slots, caption suggestions, and layout recommendations.

- `scripts/plan_images.py <draft.md>`
  Produces a visual plan JSON from a Markdown article draft.

- `scripts/generate_captions.py <plan.json>`
  Produces caption and placement-note suggestions from that plan.

- `scripts/source_images.py <plan.json> ...`
  Builds candidate source pages with slot-aware ranking.

- `scripts/extract_primary_image_assets.py <jobs.json> ...`
  Extracts likely image assets from source pages, including media pages.

- `scripts/publish_qdaily_supabase.py <article.md> --database-url ...`
  Uploads hero/inline media to Supabase Storage, rewrites the article to use public Storage URLs, and syncs the final article into Q-daily's Supabase tables.

## References

- `references/writing-style.md` — per-`article_type` structural templates (skeletons)
- `references/column-styles.md` — per-column (`好文章` / `好观点` / `好家伙` / `好论文`) length / opening / voice / image rules
- `references/topic-selection-and-routing.md` — two-axis (栏目 × 领域) routing, topic card, article-type ↔ column mapping
- `references/fact-check.md` — required pass between writing and publishing; verify every number / date / quote against literal source
- `references/final-read.md` — required pass between layout and publishing; catches meta-commentary, draft markers, placeholders that survived the writing pass
- `references/image-style.md`
- `references/image-source-priority.md` — slot-based source ranking + paper/report figure extraction (for `好论文`)
- `references/layout-style.md` — frontmatter spec including `column:` and `category:` fields

## Output Standard

The preferred end state is a markdown-ready package that includes:
- a tightened title
- a useful summary
- edited body structure
- image choices or deliberate empty slots
- factual captions
- layout notes or a final markdown draft

If the article is being published to Q-daily / Supabase, the preferred end state also includes:
- Storage-backed hero and inline media URLs
- database rows that match the final rewritten Markdown
- both axes filled: `articles.column_slug` (栏目) and `articles.category_slug` (领域)

## Common Mistakes

- treating image selection as a search task instead of an editorial task
- forcing an image into every slot
- using promotional visuals where documentary images are needed
- using the most common image instead of the most fitting one
- writing captions that repeat the paragraph without adding value
- weakening the ending by inserting unnecessary images late in the piece
