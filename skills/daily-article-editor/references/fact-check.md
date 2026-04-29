# Fact-Check

Required pass between writing and publishing. Catches the class of error
that broke the first version of the Anthropic Economic Index article: the
prose said "10% 被雇主拿走"，and the source actually said "10% of respondents
**who named a recipient** said employers or clients were asking for and
getting more work." Both numbers are 10, but the denominator is different.

If a piece survives this pass cleanly, it is publishable. If any item in
the checklist fails, fix the prose before publish — never publish first
and correct later.

## When To Run

- After the writing pass is complete
- After the image pass is complete
- **Before** the layout pass and **before** `publish_to_daily.py --execute`

## The Checklist

For every claim in the article that contains a number, a name, a date, or
a quoted phrase, fill out one row of this table:

| Claim (paragraph reference) | Source URL | Source quote (verbatim) | Match? |
|---|---|---|---|

A claim is anything a competent reader could push back on with "where did
you get that?" — examples:

- A specific number (`8.1 万`, `1.3 个百分点`, `60% vs 80%`, `48-40-10%`)
- A specific date (`4 月 22 日`, `2026-04-22`, `本周`, `周二`)
- A named person, company, product, or paper
- A direct quote (anything in `"..."` or `「...」`)
- An attribution claim ("Anthropic 自己说……", "X 团队发现……")
- A causal claim ("因为 X，所以 Y" — does the source actually argue causation?)

The goal is not to find perfect citations for every word; it is to make
sure the article does not invent or misremember anything.

## How To Verify A Claim

For each checklist row:

1. Read the source's literal sentence (not the headline, not the summary,
   not someone else's recap of it). If the source is a PDF / paper, search
   inside it.
2. Ask the **denominator** question: when the source says `10%`, 10% of
   what? Sample frame, subset, or full population?
3. Ask the **direction** question: does the source claim X → Y, or just
   X correlates with Y? Don't promote correlation to causation.
4. Ask the **time** question: does the source say "as of [date]" or
   "across the last quarter" or just publish a snapshot? If the article
   says "this week" but the source covers the last month, fix it.
5. If the article uses paraphrase (almost always), the paraphrase must
   preserve all four of: the number, the denominator, the direction, and
   the time. Drop any one and you've changed the claim.

## Common Failure Modes

| failure | example | fix |
|---|---|---|
| **Denominator drift** | "10% of users" but source says "10% of users who named a recipient" | Add the qualifier to the prose, or move to a smaller number that doesn't need the qualifier |
| **Causation upgrade** | "AI causes career-stage disparity" but source says "career stage correlates with reported AI benefit" | Use "相关 / correlates with", not "造成 / causes" |
| **Time elision** | "Anthropic just announced…" but source is from 6 weeks ago | State the actual date |
| **Telephone-game quote** | Quote with subtly different word order | Always copy-paste the literal source string |
| **Single-source overreach** | Generalizing from one sample frame to the whole population | Add the sample-frame qualifier in the same paragraph as the number |
| **Headline-only verification** | Citing the headline of a source you didn't fully read | Quote a sentence from the body, not the headline |

## Verification Inventory For A `data-piece`

A `好论文 / data-piece` article has tighter requirements than a `好家伙` news
piece. Every numeric claim in a data-piece must be backed by:

1. A direct link to the source (in the article body, not just metadata)
2. The literal source sentence (in this checklist, not the article)
3. The sample-frame disclosure (already required by `column-styles.md`
   under 好论文; cross-check that it's actually in the prose, not just
   intended)
4. A note on what the data does NOT measure (the standard 好论文 ending)

## How To Use The Checklist

In practice, copy the table at the top of this file into a temporary file
named `output/<slug>-fact-check.md`, fill out one row per claim, then
attach it to the editorial PR review. After publish, the file can be
deleted — its job is done.

## What Passes And What Doesn't

A pass:

```
| 8.1 万人调研（hero, p2, p4） | https://www.anthropic.com/research/81k-economics
  | "We share insights from a survey of approximately 81,000 Claude users."
  | ✅ — 数字、人群（Claude users）、"approximately" 都在 |
```

A fail (the bug we shipped first time round):

```
| 10% 被雇主拿走（p3.3）       | https://www.anthropic.com/research/81k-economics
  | "10% of respondents who named a recipient said that employers or clients
     were asking for and getting more work."
  | ❌ — 我写的是 "10% 主动谈到生产力变化的用户"，分母错了 |
```

The fix went into the article as: "当受访者明确点名'谁拿走了这份生产力'时，
有 10% 的人会指向雇主或客户" — preserving the denominator restriction.

## What This Checklist Does Not Catch

- **Tone / framing** issues — that's the job of `column-styles.md`
- **Structural** issues — that's the job of `writing-style.md`
- **Originality** — that's a separate watchlist-distance check (see
  `topic-selection-and-routing.md`)
- **Visual fidelity** of charts — that's the job of `image-source-priority.md`

This checklist only catches **factual misalignment** between the prose and
its sources. That's a small corner of editorial quality but it's the corner
that erodes trust the fastest when violated, so it gets a dedicated pass.
