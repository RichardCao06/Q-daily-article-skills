# Topic Selection And Routing

## Goal

Move from a collected update set to:

1. one clear story candidate
2. one explicit core judgment
3. one matching writing mode
4. **one column** (栏目) and **one domain** (领域) — see "Two routing axes" below

Do not start from “which item is hottest”.
Start from “which contradiction or shift is most worth explaining”.

## Two Routing Axes

Every Q-daily article carries TWO independent labels at publish time. They are
orthogonal — pick each one separately.

### Axis 1 — Column (栏目, `column_slug`)

This is **what kind of piece** it is — the editorial form, not the topic.

| slug | 中文 | When to use |
|---|---|---|
| `good-article` | 好文章 | Long-form feature, profile, interview, retrospective, listicle. Needs a narrative arc, characters, scenes, or a multi-part structure. |
| `good-take`    | 好观点 | Commentary, op-ed, position piece. The article's value comes from the judgment, not the news event. |
| `good-grief`   | 好家伙 | Industry-shaking event, big-company move, news feature with surprise. Fast pacing, strong signal, a clear "look at this" energy. |
| `good-paper`   | 好论文 | Paper-based explainer, survey-driven data piece, technical mechanism story. The article is built on a published study, dataset, or technical reference. |

A single piece belongs to exactly one column.

### Axis 2 — Domain (领域, `category_slug`)

This is **what topic field** the piece sits in. FK to `public.categories`.

`smart` 智能 / `business` 商业 / `design` 设计 / `fashion` 时尚 /
`entertainment` 娱乐 / `culture` 文化 / `gaming` 游戏

The column and the domain are independent. Examples:

- Anthropic Economic Index 8.1 万人调研 → `good-paper` × `smart`
- LCA 软件市场评论 → `good-take` × `business`
- Google Cloud Next 一周连发 → `good-grief` × `smart` (or `business`)
- Cohere 创始人讲 MoE × speculative decoding → `good-paper` × `smart`

### article_type ↔ column (default mapping, hint only)

The 9 writing methods (`profile / interview / feature / listicle / news-brief /
explainer / data-piece / column / retrospective`) are **shapes of writing**;
columns are **editorial buckets**. They line up roughly like this:

| article_type                                  | default column |
|-----------------------------------------------|----------------|
| profile / interview / feature(general) / retrospective / listicle | `good-article` |
| column                                        | `good-take`    |
| news-brief / feature(event-news) / feature(company-shift) / feature(policy-rules) | `good-grief` |
| explainer / data-piece / feature(data-trend)  | `good-paper`   |

Treat the table as a starting point. A `feature` that is mostly opinion can
still go to `good-take`; a `data-piece` whose hook is "look how loud this
number is" can still go to `good-grief`. Pick by what the piece really does,
not by mechanical lookup.

## Core Rule

**pick by explanatory tension, then route by article logic**

That means:
- first decide what is truly worth explaining
- then decide what kind of article logic the material needs

## Step 1: Rewrite Each Update As A Change Sentence

Do not leave items in headline form.
Rewrite each candidate into one sentence using this pattern:

- `X is not just doing Y; it is changing Z.`

Examples:

- `Perplexity is not just adding Plaid; it is changing what a search AI can access under user permission.`
- `Apple is not just updating its developer rules; it is redrawing the boundary for loot-box transparency.`
- `Amazon is not just changing its film mix; it is choosing scale over the cultural position it built with independent cinema.`

If you cannot rewrite an item this way, it is usually not ready to become a feature.

## Step 2: Group Updates Into Story Candidates

Sort updates into one of two buckets:

- `single-trigger story`
  - one strong update is enough to carry the piece
- `signal-cluster story`
  - multiple updates together prove a larger shift

Good single-trigger stories:
- rule change
- product move with structural consequences
- company strategy turn
- report or market number that reveals a bigger trend

Good signal-cluster stories:
- several companies converging on the same competitive layer
- multiple official updates pointing to the same industry direction

## Step 3: Score Story Candidates

Before drafting, score each candidate on five checks:

- `freshness`
  - is the signal still timely inside the chosen window
- `importance`
  - does it change a market, workflow, rule boundary, company direction, or user behavior
- `explainability`
  - can the piece answer “why is this happening” and not only “what happened”
- `evidence density`
  - is there enough official material to support the judgment
- `ending strength`
  - can the article end on a real unresolved question, limit, or consequence

Prefer the candidate that is strongest across all five.

## Step 4: Fill The Topic Card

Before writing, complete this card:

- `trigger update:`
- `real question:`
- `why now:`
- `evidence set:`
- `final judgment:`
- `recommended mode:`             — one of the 9 article_type values
- `column:`                       — `good-article` / `good-take` / `good-grief` / `good-paper`
- `domain:`                       — `smart` / `business` / `design` / ...

If any of these lines feels vague, the topic is not ready yet.

The `column` and `domain` flow into the article frontmatter as `column` and
`category` (see the layout-style reference) and are written to
`articles.column_slug` and `articles.category_slug` at publish time.

## Routing Table

Use this routing table after the topic card is filled.

### `profile`

Use when:
- one person is the clearest way into the larger issue
- removing the person would collapse the story

Ask:
- is this really about a person’s path, method, tension, or role

### `interview`

Use when:
- the article’s value is primarily carried by a conversation or Q&A source

Ask:
- would this piece lose most of its value without the direct voice

### `feature:general`

Use when:
- multiple updates together support a larger industry judgment
- no single update is sufficient on its own

Ask:
- am I really writing the convergence of several signals

### `feature:event-news`

Use when:
- one fresh move opens the door to a bigger structural question

Ask:
- does the article begin from a new action and then explain what it actually changes

### `feature:policy-rules`

Use when:
- the center of gravity is a rule, policy, requirement, legal boundary, or enforcement shift

Ask:
- is the real issue who must now change behavior, and where the boundary sits

### `feature:company-shift`

Use when:
- the main story is that a company is changing direction, allocation, position, or business logic

Ask:
- is the article mainly answering why the company is turning now and what it gives up or gains

### `feature:data-trend`

Use when:
- a report, ranking, market number, or behavioral metric is the doorway into a larger trend

Ask:
- am I using the number to explain a system, not just repeating the number

## Quick Decision Rules

- If the best opening sentence starts with a specific new move:
  - lean `event-news`
- If the best opening sentence starts with a rule, requirement, or guideline:
  - lean `policy-rules`
- If the best opening sentence starts with a company decision or strategic adjustment:
  - lean `company-shift`
- If the best opening sentence starts with a revealing number or report:
  - lean `data-trend`
- If the strongest evidence only appears when several updates are combined:
  - lean `feature:general`
- If the larger issue is easiest to understand through one person:
  - lean `profile`

## Common Mistakes

- choosing the loudest update instead of the most explainable one
- forcing a cluster story into a single-trigger frame
- writing a trend piece when the material is really a company-turn story
- writing a company-turn story when the real center is a new rule boundary
- mistaking a statistic for a story without explaining the system behind it
- starting the draft before the topic card is complete
