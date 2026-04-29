# Layout Style

## Goal

Produce a markdown draft that is easy to publish or paste into a CMS.

## Frontmatter Spec

Every Q-daily article markdown starts with YAML-ish frontmatter delimited by
`---` lines. Required keys (in this order):

```yaml
---
title:        <短句标题>
slug:         <kebab-case-slug-with-date>
excerpt:      <一段长 60–100 字的摘要>
publishedAt:  <ISO-8601 with timezone, e.g. 2026-04-24T16:00:00+08:00>
author:       <author display name, must exist in public.authors>
readingTime:  <e.g. "6 分钟">
category:     <smart | business | design | fashion | entertainment | culture | gaming>
column:       <good-article | good-take | good-grief | good-paper>
tags:         <comma-separated, optional>
palette:      <CSS gradient string for cover>
coverAlt:     <英文 alt 文本>
heroImage:    <full URL — local OR external; publish step migrates external to Storage>
heroCaption:  <图注：...来源：[名称](链接)>
---
```

`category` is the **领域 (topic domain)**; `column` is the **栏目 (editorial
column)** introduced by the two-axis model — see
`references/topic-selection-and-routing.md` for which value to choose.

`column` is required for new articles. Older drafts written before the axis
existed may omit it; the publish script will leave `articles.column_slug`
NULL in that case.

## Order

1. title
2. summary
3. hero image
4. body
5. mid-story images only where the story opens up visually
6. ending with minimal visual interruption

## Spacing Rules

- keep one blank line between paragraphs
- keep one blank line around images
- keep caption format consistent

## Caption Format

Use one consistent form:

`*图注：……来源：[名称](链接)*`

Keep captions factual and short.

## Image Rhythm

- do not insert an image after every heading
- use mid-story images only when they clarify the turn of the piece
- keep the ending visually tighter than the middle

## Final Pass Checklist

- title and summary are present
- headings are short
- images are in the right slots
- captions match the tone of the article
- no weak image was inserted just to fill space
