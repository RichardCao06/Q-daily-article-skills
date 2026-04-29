# Feedback Loop — Design Sketch

This is a design doc for closing the loop between **published article** and
**next-cycle editorial decisions**. It is NOT implemented yet.

## Why we need it

Today the pipeline is one-directional:

```
collect → select → write → image → publish
                                      ↓
                                    [end]
```

After publish, nothing flows back. The editor never sees:

- which articles got read to the end vs bounced
- which sentences readers tried to copy / share
- whether a claim got externally fact-checked and is now wrong
- which entities readers searched for after reading
- whether a topic still earns a follow-up next week

So the next cycle starts cold every time, even though the previous cycle
just generated a lot of evidence about what worked.

## What "closed loop" looks like

```
collect → select → write → image → publish
   ↑                                  ↓
   └──────── feedback signals ────────┘
```

The signals fall into four buckets:

### 1. Reader behavior signals (frontend → DB)

Lightweight, anonymized:

- `read_complete` — fraction of viewers who scrolled past the last block
- `read_time_p50` — median time on page in seconds
- `share_event` — copy-link / X share / WeChat share clicks (no user PII)
- `dwell_at_block` — where readers slow down or speed up (heatmap-ish)

Storage: a new `article_engagement_metrics` table on the daily DB,
populated by a small client-side beacon (already partially implemented in
`article-engagement.tsx`).

### 2. Reader correction signals (frontend → DB)

When a reader spots a factual error:

- A "纠错" link in the article footer that opens a small form
- One field: which sentence is wrong + their evidence (link or text)
- Stored in `article_corrections(article_slug, paragraph_idx, claim_text,
  evidence, status, reviewed_at)`
- Status flow: `submitted` → `reviewed` → `applied` (article patched) /
  `dismissed` (reader was wrong)

This is the feedback loop's most concrete value: editorial trust grows
when corrections are visible and reversible.

### 3. Re-collection signals (next-cycle tracker)

When the next collection run happens, it can read the published article
history and:

- Boost any entity that had a popular article in the last 7 days
  (because readers want a follow-up)
- Drop or de-prioritize entities whose articles got `read_time_p50`
  under N seconds (readers don't care)
- Flag any claim that has a pending `article_corrections` entry — block
  re-using the claim until correction is applied

### 4. Editorial-pass signals (publish → next selection)

After a piece publishes, write a small structured "editorial outcome"
record:

- `intended_column` — what the topic-card said
- `actual_column` — what column_slug ended up on the article
- `intended_length` — column-styles' expected band
- `actual_length` — final body chars
- `article_type` — final shape

When the next round of writing happens, the topic-selection step can
compare candidates against this record:

> "Last 5 articles in `好家伙` averaged 2,800 chars; this candidate's
>  estimated material would push past 4,500 chars. Either trim the
>  topic or route it to `好文章`."

## Implementation order

| step | difficulty | unlocks |
|---|---|---|
| 1. read-time + read-complete beacon (frontend → `article_engagement_metrics`) | low (~1 day) | "are people reading" telemetry |
| 2. "纠错" form + `article_corrections` table | medium (~2 days) | factual feedback |
| 3. cron job: `nightly_feedback_rollup.py` writes per-article aggregates | low (~half day) | feeds next-cycle scorer |
| 4. extend `score_topic_candidates.py` to consume rollups | low (~half day) | reader-aware ranking |
| 5. editorial-outcome record on publish (auto from publish_to_daily.py) | low (~half day) | column-band drift detection |

Steps 1+3 unlock the "reader behavior" half. Steps 2+4 unlock the
"correction" half. They can ship independently.

## What this document is for right now

It's an **explicit acknowledgment** that the current pipeline ends at
publish. None of the above is implemented. Until it is:

- Editor decisions about "which entity to follow up on" are intuition
- Reader-side corrections happen on social media and disappear
- Column-band drift goes unmeasured
- Topic re-pick decisions can't reference previous-cycle outcomes

If the editorial volume justifies it (≥10 articles / week sustained),
the implementation is small. If volume is lower, the loop has more
value as a discipline (manual reading-back of published articles
before next cycle's topic card) than as code.

## Manual interim ritual

Until automation lands, run this ritual once a week:

1. List articles published in the last 7 days.
2. For each: write one sentence "what worked, what didn't" — column fit,
   length, evidence density, image strength.
3. For each: name one factual claim that, if wrong, would matter — and
   re-verify it.
4. Compile #2 + #3 into `output/weekly-retro-<date>.md`.
5. Read the retro before starting the next topic-selection step.

This catches ~70% of what an automated feedback loop would catch, and
costs ~30 minutes per week.
