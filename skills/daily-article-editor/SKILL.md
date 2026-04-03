---
name: daily-article-editor
description: Use when turning an existing long-form draft into a publishable article package with structure editing, image selection, captions, and markdown-ready layout in a Qdaily-like rhythm.
---

# Daily Article Editor

## Overview

This skill is a full editorial workflow for feature-style articles.
It covers three linked jobs:

1. shape the writing
2. choose the right images
3. deliver a clean markdown-ready article package

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

Decide:
- article type: `profile`, `interview`, or `feature`
- what the piece is really about
- where the opening, turn, evidence, and ending sit

Then edit for:
- title sharpness
- summary usefulness
- heading rhythm
- paragraph pacing
- ending restraint

Use `references/writing-style.md`.

### 2. Image Pass

Extract visual slots from the story.

Use slot types:
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

### 4. Layout Pass

Prepare a markdown-ready article:
- title
- summary
- images in the right places
- captions in a consistent format
- breathing room between text and images

Use `references/layout-style.md`.

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

## References

- `references/writing-style.md`
- `references/image-style.md`
- `references/image-source-priority.md`
- `references/layout-style.md`

## Output Standard

The preferred end state is a markdown-ready package that includes:
- a tightened title
- a useful summary
- edited body structure
- image choices or deliberate empty slots
- factual captions
- layout notes or a final markdown draft

## Common Mistakes

- treating image selection as a search task instead of an editorial task
- forcing an image into every slot
- using promotional visuals where documentary images are needed
- using the most common image instead of the most fitting one
- writing captions that repeat the paragraph without adding value
- weakening the ending by inserting unnecessary images late in the piece
