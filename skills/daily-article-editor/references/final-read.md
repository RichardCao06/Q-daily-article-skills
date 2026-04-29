# Final Read

Last pass between layout and publish. Catches the class of error that
fact-check and layout miss: **the prose still reads like notes, not like a
finished article**.

## Why this pass exists

At least one article shipped with this section heading inside the body:

> ## 为什么这一篇值得在 `好论文` 栏目里发

That paragraph belongs in the **topic card** (a planning step), not in
the published prose. The reader doesn't know what `好论文` is. The reader
doesn't care that column-styles.md says good-paper articles should end on
a specific limitation. The reader cares about the SUBJECT.

The author who wrote it (me, this session) had read column-styles.md so
recently that the column rules leaked into the writing. Fact-check
didn't fire — the heading isn't a factual error. Layout didn't fire —
the heading is a valid `## H2`. Neither pass has any reason to flag
"this is meta-commentary".

So we add a third pass.

## What this pass catches

### 1. Meta-commentary (always error)

The article refers to itself, or cites its own column / writing-method
rules, in a way that breaks the fourth wall. Examples:

| violation | why it's wrong |
|---|---|
| `## 为什么这一篇值得在 \`好论文\` 栏目里发` | section heading talks ABOUT the article |
| `按 \`好论文\` 栏目的约束，结尾应该指出……` | prose cites column-styles' contract |
| `这是好论文该有的样子` | praise of the column's structure rule |
| `这一段是 data-piece 的第一道工序` | prose names the article-type as if explaining the writing |
| `值得在好论文栏目` | self-reference about column placement |
| `this article` / `this piece` / `in this column` | English equivalents |

These are **not** style preferences — they are concrete signs that the
topic-card phase leaked into prose. Fix by:

- Replacing the meta-heading with a topic-focused heading. For example,
  `## 为什么这一篇值得在好论文栏目里发` → `## 这件事的影响面`
  (or `## 对 X 行业意味着什么`, `## 下一步会发生什么`, etc.).
- Removing in-line meta-references entirely; the conclusion that follows
  almost always stands on its own.

### 2. Draft markers (always error)

`TODO`, `FIXME`, `XXX`, `HACK`, `WIP`, `placeholder`, `占位符`,
`[draft]`, `[草稿]`, `lorem ipsum` and similar must all be replaced
with real content before publish.

### 3. Editor placeholders (always error)

Bracketed editor instructions:

- `[insert quote here]`
- `[TBD]`, `[TKTK]`, `[to be added]`
- `<author name>`, `<date>`, `<figure>`
- `{author}`, `{date}`, `{name}`

Note: this pattern deliberately whitelists Markdown links `[text](url)`
and footnote markers `[1]` `[i]`.

### 4. Empty blocks (always error)

- Heading line with no content: `### `
- List bullet with no content: `- ` or `1. `
- Empty list items mean the author started enumerating something and
  forgot to fill the last one in.

### 5. Unclosed `**bold` (warning)

A line with an **odd number of `**` markers** (after stripping
backtick-delimited code spans) is suspicious. Either the author opened a
bold span and forgot to close it, or they pasted markdown from elsewhere
and the closer is on a different line. Manual review.

This is a warning rather than an error because some markdown flavors
allow `**` to span paragraphs and we don't want to false-positive on
that case. `--strict` promotes warnings to errors for CI.

## How to run

### As a standalone scan

```
python3 scripts/validate_article.py output/<slug>.md
```

Exit codes:

- `0` — clean
- `1` — one or more errors found
- `2` — I/O error

### As a publish pre-flight gate

`publish_to_daily.py` runs the validator automatically before commit. If
any error fires, the publish is **blocked** with exit code 6, before any
Storage upload happens. Override with `--skip-content-check` (use only
for the rare metacritical piece about Q-daily itself).

## What this pass does NOT do

- It does NOT verify facts (that's `references/fact-check.md` /
  `scripts/fact_check_inventory.py`)
- It does NOT verify column / domain alignment (that's
  `references/column-styles.md`)
- It does NOT check word-count or rhythm (column-styles.md does that
  loosely; G7 is the planned automation)
- It does NOT verify rendering on the live site (that's `--verify-render`
  in publish_to_daily.py)

It only catches **draft / planning-notes leakage into the published
prose**. That's a small corner of editorial quality but it's the corner
that visibly screams "this isn't finished" to readers when violated.

## Override

If you genuinely want to publish a metacritical piece about Q-daily
itself — one that talks about columns, article-types, or the editorial
pipeline as its actual subject — pass `--skip-content-check`. Document
in the PR / commit why this article is the rare exception.
