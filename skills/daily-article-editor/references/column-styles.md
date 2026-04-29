# Column Styles

This file is the per-column style sheet for Q-daily's four editorial columns
(`好文章` / `好观点` / `好家伙` / `好论文`).

## Why This File Exists

`writing-style.md` answers "how do I build the skeleton of a `feature` /
`profile` / `explainer` / etc.". This file answers a different question:
"what should this column **feel** like to read?"

Both files apply at once:
- `column-styles.md` decides the column's rhythm, length, voice, opening, image temperament.
- `writing-style.md` decides which structural template the article follows.

When the two collide (e.g., a `feature` skeleton drafted at 5,000 chars
landing in `好家伙`, which prefers 1,500–2,500), the column wins. Trim the
skeleton to fit the column.

See `topic-selection-and-routing.md` for how to assign the column in the first
place.

---

## 好文章 (`good-article`)

### Promise

A piece worth sitting down for. The reader expects narrative, scenes,
characters, voice — long-form journalism, not a news bulletin.

### Methods

| use | borrow | avoid |
|---|---|---|
| `feature` (general / company-shift / policy-rules), `profile`, `interview`, `retrospective`, long `listicle` | `data-piece` (when the data drives a long narrative) | `news-brief`, `column` (too op-ed), short event roundups |

### Style sheet

| dimension | rule |
|---|---|
| length | 2,500 – 6,000 chars |
| opening | Slow-build is allowed. A scene, a person walking into a room, a single quote, or a "this is the second time in three years that…" framing all work. |
| middle | Narrative arc: **event → person/company → method → tension → larger context**. Use sub-headings as navigation, not as filler. |
| ending | Quiet. Land on the unresolved problem, the cost paid, or the question still open. Avoid explicit moral. |
| voice | Editorial. The author is present but disciplined. Adjective use is rationed. |
| images | Documentary photography, scenes, faces. Multi-image is OK; let images breathe between sections. |
| sub-headings | Encouraged — use 3–5 to navigate longer pieces. Keep them noun-phrase short. |
| anti-patterns | Treating a single-day news event as if it were a deep feature; repeating the same judgment in three forms; over-quoting. |

### Reference

`mistral-open-model-europe-feature-editorial` — a `feature:company-shift`
inside `好文章 × 商业`: the news (Mistral 发新模型) is the door, but the article
walks through Europe's open-model thesis as the larger arc.

---

## 好观点 (`good-take`)

### Promise

The reader is here for **judgment**. They want to know what the writer
thinks, why, and what evidence supports it. The article is built as an
argument, not as a report.

### Methods

| use | borrow | avoid |
|---|---|---|
| `column` | `interview` (only when the conversation IS the position) | `news-brief`, `retrospective`, `profile`, `data-piece` (data is evidence here, never the structure) |

### Style sheet

| dimension | rule |
|---|---|
| length | 1,500 – 3,000 chars |
| opening | The position must be visible by the **second paragraph**. Slow scene-setting kills the column. |
| middle | Argument-first structure: **claim → why now → evidence A → evidence B → counter-claim handled → judgment.** Each paragraph should advance the argument. |
| ending | Strong but not slogan-like. End on the consequence of the position being right, or the cost of it being right. |
| voice | Strongest of the four columns. The author has a stake. First-person OK if it sharpens, not softens, the take. |
| images | Minimal. Often just the hero. Inline images only when an image carries an argument the prose can't (rare). |
| sub-headings | Almost never. The piece should read as one continuous argument. |
| anti-patterns | "On the one hand / on the other hand" balanced reporting; hiding the take in the last paragraph; replacing argument with adjectives. |

### Reference

`cover-gpt-5-5-new-class-of-intelligence-2026-04-24` — `column` in `好观点 ×
智能`: stakes the position ("this is marketing or a real turn"), then walks
the evidence to a clean judgment without retreating to balance.

---

## 好家伙 (`good-grief`)

### Promise

Look at this. The reader feels the surprise — a big company moved, a price
flipped, a product shipped that nobody expected. The article validates that
surprise and explains why it's bigger than it looks.

### Methods

| use | borrow | avoid |
|---|---|---|
| `news-brief`, `feature:event-news`, `feature:company-shift`, `feature:policy-rules`, short `listicle` (3–8 items, news-shaped) | `data-piece` (when the **number itself** is the surprise) | `profile`, `retrospective`, long-form narrative |

### Style sheet

| dimension | rule |
|---|---|
| length | 1,500 – 2,500 chars |
| opening | The **first sentence is the news**. Scene-setting is forbidden. The second paragraph answers "and here's why this is more than a news headline." |
| middle | Mechanism + consequence: **what happened → who must change → what it gives up / gains → what it tells us about the industry layer**. |
| ending | A real constraint, contradiction, or unresolved cost. Don't end on hype. |
| voice | Cool, news-register. The surprise lives in the facts, not in the adjectives. |
| images | News photography, product shots, conference floor, founder portraits. Hero + maybe one inline. Avoid stock. |
| sub-headings | 0–2. If the piece needs more, it has become a `好文章`. |
| anti-patterns | Slow scene-setting; over-explaining background before the news lands; bucketing into too many sections. |

### Reference

`anthropic-three-clouds-compute-alliance-2026-04-24` — `feature:company-shift`
in `好家伙 × 智能`: opens with "三朵云" by paragraph two, lays down the
numbers, ends on the structural constraint Anthropic has now bought into.

---

## 好论文 (`good-paper`)

### Promise

The reader is here to **understand a mechanism**. There is a paper, a
dataset, a benchmark, or a technical claim at the center, and the article's
job is to walk the reader through how it works and what it implies.

### Methods

| use | borrow | avoid |
|---|---|---|
| `explainer`, `data-piece`, `feature:data-trend` | `interview` (only when interviewing the researcher about the work) | `news-brief`, `column`, `profile` (unless the researcher's path *is* the explanation) |

### Style sheet

| dimension | rule |
|---|---|
| length | 2,000 – 4,000 chars |
| opening | A question, a counter-intuitive claim, or a single observation that the rest of the article will explain. Cite the source by paragraph two. |
| middle | Step-by-step mechanism: **observation → standard model → where it breaks → the new mechanism → what it predicts → evidence in the paper/data**. Each step should be answerable in one paragraph. |
| ending | A specific limitation: what the paper does NOT prove, what the next experiment would need, or what would break the mechanism. |
| voice | Explanatory, near-lecture. The author is a guide, not a critic. Stronger judgment belongs in `好观点`. |
| images | Charts, paper figures (with permission / fair-use credit), mechanism diagrams, screenshots of the dataset. Captions do real explanatory work. |
| sub-headings | Encouraged — use them as mechanism-step delimiters, not as topical breaks. |
| anti-patterns | Substituting opinion for evidence; skipping the "where the standard model breaks" step; treating the paper as news. |

### Reference

`reward-hacking-gradient-feature-editorial` — `explainer` in `好论文 × 智能`:
opens on the counter-intuitive observation ("when models start gaming, only
looking at the answer is no longer enough"), then walks the mechanism by
which reward hacking emerges.

---

## Cross-column Quick Decision

When in doubt between two columns, ask:

| question | answer |
|---|---|
| Does the value come from **the news event itself**? | 好家伙 |
| Does the value come from **the writer's judgment**? | 好观点 |
| Does the value come from **a paper / dataset / mechanism**? | 好论文 |
| Does the value come from **the reading experience itself** (narrative, scene, character)? | 好文章 |

If two answers are tied, the longer-lived value wins: 好文章 > 好论文 > 好观点
> 好家伙. (好家伙 ages fastest; 好文章 has the longest re-read shelf life.)
