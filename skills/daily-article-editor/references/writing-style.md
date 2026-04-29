# Writing Style

## Goal

Turn a draft into something closer to a publishable newsroom article.
The writing should feel edited, not merely expanded.

## Relation to `column-styles.md`

This file is organized by **article_type** (the structural skeleton —
`profile`, `feature(*)`, `explainer`, `data-piece`, etc.). It says how each
skeleton is built.

`column-styles.md` is organized by **column** (the editorial container —
`好文章` / `好观点` / `好家伙` / `好论文`). It says how each column should feel
to read.

Both apply at once. When the column's style sheet contradicts the article
type's structure (e.g., a `feature` skeleton drafted at 5,000 chars landing
in `好家伙`, which caps around 2,500), the **column wins** — trim the skeleton
to fit the column's promise. See `topic-selection-and-routing.md` for which
article types belong in which columns.

## Editorial Priorities

1. clarify what the article is really about
2. make the opening enter quickly
3. keep paragraphs moving
4. let evidence do more work than explanation
5. end on a clean problem or judgment, not a slogan

## Article Types

- `profile`
  - focus on a person as a way into a larger question
  - good structure: event -> person -> method -> larger context -> unresolved question

- `interview`
  - build the person before the questions become abstract
  - good structure: scene -> context -> Q&A -> tightening close

- `feature`
  - focus on a phenomenon, company, or trend
  - good structure: event -> why it matters -> evidence -> bigger pattern

### `feature:event-news`

- use this when the draft starts from a fresh move, rule change, announcement, removal, filing, resignation, funding event, or platform decision
- good structure: latest move -> real question -> mechanism and context -> affected parties -> unresolved consequence
- the first two paragraphs should already answer both:
  - what just happened
  - why this is more than a single piece of news
- prefer evidence such as:
  - filings, platform rules, public statements, official notices, data points, and concrete market reactions
- end on the remaining constraint, contradiction, or unresolved problem
- do not let the background swallow the news trigger

### `feature:policy-rules`

- use this when the center of gravity is a rule, policy, developer guideline, platform requirement, legal boundary, or enforcement change
- good structure: rule change -> core dispute -> execution mechanism -> affected groups -> limits and aftereffects
- explain the rule in plain language before expanding its meaning
- the key question is usually not “what was updated” but “who now has to change behavior, and why”
- prefer evidence such as:
  - policy text, developer docs, official notices, regulator demands, public responses, implementation examples
- end on the remaining ambiguity:
  - how it will be enforced
  - where the boundary still feels fuzzy
  - who still bears most of the cost

### `feature:company-shift`

- use this when a company changes strategy, budget, product mix, leadership direction, distribution posture, or growth logic
- good structure: company move -> why now -> business logic -> market consequence -> risk and suspense
- do not stop at the move itself; explain what pressure, tradeoff, or ceiling pushed the company there
- the middle should show how brand, revenue, scale, market access, and timing fit together
- prefer evidence such as:
  - earnings signals, internal strategy reports, interviews, pricing or budget clues, product mix changes, analyst or market context
- end on the open business question:
  - whether the move can work
  - what it may cost the company
  - what original position it gives up

### `feature:data-trend`

- use this when the draft starts from a revealing number, report, ranking, comparison, market movement, or usage statistic and turns it into a broader trend explanation
- good structure: data point -> trend judgment -> drivers and variables -> wider meaning -> limits and counterforces
- do not stop at repeating the number; the real work is explaining what conditions made that number possible
- the middle should usually answer:
  - what changed
  - what is driving it
  - who benefits or loses
  - what the number still cannot explain
- prefer evidence such as:
  - official reports, financial data, rankings, year-over-year comparisons, market comparisons, operational metrics, behavior data
- end on the missing side of the picture:
  - structural cost
  - friction in the system
  - where the trend may level off or reverse

### `listicle`

- use this when several related items together form the story, and ranking / sequence / contrast is itself the argument
- good structure: framing dek -> N items, each with a one-sentence judgment + 2–3 sentences of evidence -> closing line that names the pattern across the list
- each item must do real editorial work: a verdict, a fact, or a contrast — never a placeholder entry
- a listicle should have **3–10 items**. Below 3 it is a `feature`; above 10 it is a roundup, not editorial.
- common subforms:
  - week-in-review across one company or one industry
  - a curated set ("5 things this product changes")
  - bucketed news roundup that wants a stronger frame than `news-brief` provides
- prefer evidence such as:
  - first-party announcements, release notes, before/after comparisons, side-by-side facts
- end on the cross-cutting pattern, not on the last item

### `news-brief`

- use this when the goal is to **scan multiple updates inside a window** with low ceremony per item
- good structure: short top-of-page dek that frames the day -> bucketed entries (Top / 区域 / Also in the News) -> 1–3 sentences per entry, no narrative arc
- each entry's job is **identify + locate + 1 line of significance** — not explain
- if any single entry needs more than 4 sentences, lift it out into its own `feature:event-news`
- buckets must be visible (use `H3`-level headings); flat lists feel like RSS dumps
- prefer evidence such as:
  - first-party announcements, official status pages, release notes, exact dates
- end on the most under-noticed item, not the loudest one — that is what makes a brief feel edited
- almost always lives in `好家伙`. If the brief is being framed as one author's reading list of the week, consider `好观点` instead.

### `explainer`

- use this when the article's job is to make a mechanism legible — a model trick, a system, a market structure, a benchmark, a technical phenomenon
- good structure: observation or counter-intuitive claim -> standard model -> where it breaks -> the better mechanism -> what it predicts -> a specific limitation
- the writer is a guide, not a critic; opinion belongs in `好观点`
- each mechanism step should be answerable in one short paragraph
- prefer evidence such as:
  - the paper or post being explained, official benchmarks, reproducible code, mechanistic diagrams, before/after numbers
- end on what the mechanism does NOT explain or where it would break — that is the honest signal of an explainer
- use sub-headings as **mechanism-step delimiters**, not topical breaks

### `data-piece`

- use this when a dataset, survey, ranking, telemetry stream, or benchmark IS the article — without the data, the piece collapses
- good structure: hook number or headline finding -> dataset description (who collected, what window, sample size) -> 2–4 sub-findings, each with its own number -> structural reading of what made the number possible -> caveats on what the data cannot show
- always disclose: source, window, sample size, methodology link
- one chart at minimum; for benchmarks include a side-by-side table; cite the cell in the dataset, not just the conclusion
- prefer evidence such as:
  - the raw dataset (linked), survey methodology, comparable historical numbers, third-party reproduction
- end on what the data does NOT measure — sampling gaps, time-window blind spots, missing populations
- closely related to `feature:data-trend`. Use `data-piece` when the dataset itself is the story (e.g. a quarterly index release); use `feature:data-trend` when a single number opens a trend story.

### `column`

- use this when the value of the piece is the **writer's judgment**, supported by evidence rather than constructed from it
- good structure: position by paragraph two -> claim → why now → evidence A → evidence B → counter-claim handled → judgment
- each paragraph must advance the argument; "balanced reporting" is an anti-pattern here, not a virtue
- the writer has a stake; first-person is allowed when it sharpens, not when it softens
- prefer evidence such as:
  - public statements, contradictions across time, structural numbers, on-the-record positions taken by named actors
- end on the consequence of being right, or the cost of being right
- almost always lives in `好观点`

### `retrospective`

- use this when the lens is **time** — looking back across a window (a quarter, a year, a product cycle, a person's tenure) to name what actually changed
- good structure: scene from the present -> what the moment looked like at the start of the window -> the turn that re-shaped it -> what was given up that nobody talks about -> what now feels permanent
- a retrospective is not a timeline; it must commit to a single judgment about what the period was really about
- the closing should answer "what does this period make possible / impossible going forward"
- prefer evidence such as:
  - product or release timelines, market numbers across the window, named actors who changed roles, statements that aged poorly or aged well
- almost always lives in `好文章`. Avoid in `好家伙` (too slow) and `好论文` (no mechanism).

## What To Edit

- Title
  - should contain both information and angle

- Summary
  - should tell the reader what the piece is really about

- Headings
  - keep them short and functional

- Paragraphs
  - prefer short to medium paragraphs
  - remove repeated judgments

- Ending
  - make it quieter and sharper
  - do not over-explain the conclusion

## Anti-Patterns

- repeating the same argument in three forms
- confusing “strong voice” with “more adjectives”
- explaining a judgment before evidence has earned it
- ending on motivational language
