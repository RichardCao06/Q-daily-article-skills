#!/usr/bin/env python3
"""Score topic candidates from a tracker updates snapshot.

The previous workflow picked candidates by hand from a large updates snapshot
("read 112 items, eyeball 5 themes, write rationale in prose"). That is hard
to reproduce, hard to audit, and means the editor's biases are invisible.

This script makes the picking auditable:

  1. Cluster updates into candidate topics (by entity + theme).
  2. Score each candidate on three reproducible dimensions:
        - signal_density   — count of first-party updates in the window
        - freshness        — most recent update's age (days)
        - source_diversity — distinct source platforms covering it
  3. Compute a novelty distance against a history file of recently
     published articles. Anything that looks like an already-published
     story is flagged so the editor can choose to skip or differentiate.

The output is a Markdown list with scores and notes — feed it into the
topic-card step of `topic-selection-and-routing.md`.

Usage:
    score_topic_candidates.py \\
        --updates  examples/ai-watchlist/ai-updates-2026-04-28.json \\
        --history  history.json \\
        --published-window 90 \\
        [--min-signal 3] \\
        [--top 10]

History file format (JSON):
    [
      {"slug": "...", "title": "...", "published_at": "2026-04-24"},
      ...
    ]

You can dump it from Supabase with:
    psql "$DAILY_DATABASE_URL" -c "\\copy (
        select json_agg(json_build_object(
            'slug', slug, 'title', title, 'published_at', published_at
        )) from articles where status='published'
    ) to stdout" > history.json

The script does NOT decide what to write. It produces a ranked, annotated
list; the editor still picks.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# loaders
# ---------------------------------------------------------------------------

def load_updates(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Returns (updates list, snapshot meta)."""
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data, {}
    if isinstance(data, dict) and "updates" in data:
        return data["updates"], {k: v for k, v in data.items() if k != "updates"}
    raise SystemExit(f"unrecognized updates snapshot shape: {path}")


def load_history(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    if not path.exists():
        print(f"[warn] history file {path} does not exist; novelty checks skipped.", file=sys.stderr)
        return []
    with path.open(encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# clustering
# ---------------------------------------------------------------------------

@dataclass
class Candidate:
    entity_name: str
    updates: list[dict[str, Any]] = field(default_factory=list)

    @property
    def signal_density(self) -> int:
        # count of distinct first-party (is_official=True) updates
        return sum(1 for u in self.updates if u.get("is_official", True))

    @property
    def all_count(self) -> int:
        return len(self.updates)

    @property
    def freshness_days(self) -> float:
        latest = max(
            (parse_date(u.get("published_at", "")) for u in self.updates),
            default=None,
        )
        if latest is None:
            return 999.0
        now = datetime.now(timezone.utc)
        return max(0.0, (now - latest).total_seconds() / 86400)

    @property
    def source_diversity(self) -> int:
        return len({u.get("source_platform", "") for u in self.updates})

    @property
    def content_types(self) -> list[str]:
        return sorted({u.get("content_type", "") for u in self.updates if u.get("content_type")})

    @property
    def title_words(self) -> set[str]:
        # Tokens for novelty comparison: titles + entity name.
        bag: set[str] = set()
        for u in self.updates:
            bag.update(tokens(u.get("title", "")))
        bag.update(tokens(self.entity_name))
        return bag


def parse_date(s: str) -> datetime | None:
    if not s:
        return None
    # Accept ISO with or without timezone, also `YYYY-MM-DD`.
    s = s.strip()
    formats = (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    )
    for fmt in formats:
        try:
            d = datetime.strptime(s, fmt)
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            return d
        except ValueError:
            continue
    # Last resort: ISO 8601 fromisoformat
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d
    except ValueError:
        return None


_TOKEN_RE = re.compile(r"[\w一-鿿]+", re.UNICODE)


def tokens(s: str) -> set[str]:
    if not s:
        return set()
    raw = _TOKEN_RE.findall(s.lower())
    # Cap noise: drop very short tokens and pure-digit tokens unless 4+ digits (years etc.)
    out = set()
    for t in raw:
        if len(t) < 2:
            continue
        if t.isdigit() and len(t) < 4:
            continue
        out.add(t)
    return out


def cluster_by_entity(updates: list[dict[str, Any]]) -> list[Candidate]:
    by_entity: dict[str, Candidate] = {}
    for u in updates:
        name = u.get("person_name") or u.get("entity_name") or "(unknown)"
        if name not in by_entity:
            by_entity[name] = Candidate(entity_name=name)
        by_entity[name].updates.append(u)
    return list(by_entity.values())


# ---------------------------------------------------------------------------
# scoring + novelty
# ---------------------------------------------------------------------------

@dataclass
class HistoryDoc:
    slug: str
    title: str
    published_at: str
    bag: set[str] = field(default_factory=set)


def build_history_bags(history: list[dict[str, Any]], window_days: int) -> list[HistoryDoc]:
    cutoff = datetime.now(timezone.utc).timestamp() - window_days * 86400
    out: list[HistoryDoc] = []
    for h in history:
        pa = parse_date(h.get("published_at", ""))
        if pa and pa.timestamp() < cutoff:
            continue
        out.append(HistoryDoc(
            slug=h.get("slug", ""),
            title=h.get("title", ""),
            published_at=h.get("published_at", ""),
            bag=tokens(h.get("title", "")),
        ))
    return out


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def novelty_concerns(candidate: Candidate, history: list[HistoryDoc], threshold: float) -> list[tuple[float, HistoryDoc]]:
    """Find published articles that probably cover the same story.

    Two signals, either is enough to surface a concern:

    1. Token-Jaccard between the candidate's title-bag and the published
       title-bag. Works when both are written in the same language.

    2. Entity-name appearance: if the candidate's entity name (or a
       lowercased variant) is a substring of the published title or slug.
       This catches the cross-language case where the candidate's English
       entity-update titles share zero tokens with a Chinese published
       title — common for Q-daily where prose is Chinese but the source
       posts are English.

    The entity-name signal returns a synthetic score of `1.0` so it
    always sorts above token matches.
    """
    cand_bag = candidate.title_words
    hits: list[tuple[float, HistoryDoc]] = []

    # Signal 1: token Jaccard
    for h in history:
        score = jaccard(cand_bag, h.bag)
        if score >= threshold:
            hits.append((score, h))

    # Signal 2: entity-name word-component match against title / slug.
    # An entity like "Google DeepMind" should match a slug like
    # `google-cloud-next-2026-04-22` even though the full string doesn't
    # appear. We match each name-component (>= 4 chars to avoid noise like
    # "AI" or "the") with word-boundary anchors against the haystack.
    seen_slugs = {h.slug for _, h in hits}
    name_components = [
        c for c in re.split(r"[\s/\-]+", (candidate.entity_name or "").lower())
        if len(c) >= 4 and not c.isdigit()
    ]
    if name_components:
        for h in history:
            if h.slug in seen_slugs:
                continue
            haystack = f"{h.title} {h.slug}".lower()
            # Slug uses dashes, title may use anything; treat both as word-
            # boundary delimited to avoid "open" matching "openai".
            matched = any(
                re.search(rf"(?:^|[^a-z]){re.escape(comp)}(?:[^a-z]|$)", haystack)
                for comp in name_components
            )
            if matched:
                # Synthetic score 1.0 — entity-name match is a stronger
                # signal than partial token overlap, sort it to the top.
                hits.append((1.0, h))
                seen_slugs.add(h.slug)

    hits.sort(key=lambda pair: pair[0], reverse=True)
    return hits[:3]


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def render(
    ranked: list[tuple[float, Candidate, list[tuple[float, HistoryDoc]]]],
    snapshot_meta: dict[str, Any],
    history_window: int,
    history_count: int,
    novelty_threshold: float,
) -> str:
    win = snapshot_meta.get("window_start", "?")
    win_end = snapshot_meta.get("window_end", "?")
    domain = snapshot_meta.get("domain", "?")

    lines = [
        "# Topic candidates — scored",
        "",
        f"- Domain: `{domain}`",
        f"- Window: `{win}` → `{win_end}`",
        f"- History compared against: {history_count} articles published in the last {history_window} days",
        f"- Novelty distance threshold (Jaccard ≥): {novelty_threshold:.2f}",
        "",
        "Each candidate is one entity's cluster of updates inside the window. ",
        "The editor still picks; this list just makes scoring auditable.",
        "",
        "## Ranking",
        "",
        "| # | Total | Entity | Signals | Fresh (d) | Sources | Content types | Novelty concerns |",
        "|---|------:|--------|--------:|----------:|--------:|---------------|------------------|",
    ]
    for n, (total, c, concerns) in enumerate(ranked, start=1):
        concern_str = "—"
        if concerns:
            top = concerns[0]
            concern_str = f"⚠ overlaps {top[0]:.2f} with `{top[1].slug or top[1].title[:40]}`"
        lines.append(
            f"| {n} | {total:.2f} | {c.entity_name} | {c.signal_density} ({c.all_count}) | {c.freshness_days:.1f} | {c.source_diversity} | {', '.join(c.content_types)[:60] or '—'} | {concern_str} |"
        )

    lines.append("")
    lines.append("## Detail per candidate")
    lines.append("")
    for n, (total, c, concerns) in enumerate(ranked, start=1):
        lines.append(f"### {n}. {c.entity_name} — total {total:.2f}")
        lines.append("")
        lines.append(f"- Signal density (1st-party / total): **{c.signal_density} / {c.all_count}**")
        lines.append(f"- Freshness: most recent update **{c.freshness_days:.1f} days ago**")
        lines.append(f"- Source diversity: **{c.source_diversity}** distinct platforms")
        lines.append(f"- Content types: {', '.join(c.content_types) or '—'}")
        lines.append("")
        if concerns:
            lines.append("**Novelty concerns** (Jaccard with recently-published titles):")
            for score, h in concerns:
                lines.append(f"- {score:.2f} — `{h.slug or '?'}` — {h.title} ({h.published_at})")
            lines.append("")
        lines.append("Recent updates:")
        for u in sorted(c.updates, key=lambda x: x.get("published_at", ""), reverse=True)[:6]:
            title = (u.get("title") or "")[:90]
            ct = u.get("content_type", "?")
            sp = u.get("source_platform", "?")
            pa = (u.get("published_at") or "")[:10]
            lines.append(f"- [{ct}/{sp}/{pa}] {title}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--updates", required=True, type=Path)
    ap.add_argument("--history", type=Path, default=None,
                    help="JSON file of recently-published articles for novelty checks")
    ap.add_argument("--published-window", type=int, default=90)
    ap.add_argument("--novelty-threshold", type=float, default=0.18,
                    help="Jaccard similarity above which a candidate is flagged as overlapping a published article")
    ap.add_argument("--min-signal", type=int, default=2,
                    help="Drop candidates with fewer than this many official updates")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--output", type=Path, default=None)
    args = ap.parse_args()

    updates, meta = load_updates(args.updates)
    history = load_history(args.history)
    history_bags = build_history_bags(history, args.published_window)

    candidates = cluster_by_entity(updates)

    # Drop weak candidates early.
    candidates = [c for c in candidates if c.signal_density >= args.min_signal]

    # Total = signal_density * 1.0 + source_diversity * 0.5 - freshness_days * 0.1
    # (negative coefficient on staleness — older = lower score).
    scored: list[tuple[float, Candidate, list[tuple[float, HistoryDoc]]]] = []
    for c in candidates:
        total = (
            c.signal_density * 1.0
            + c.source_diversity * 0.5
            + max(0.0, 7 - c.freshness_days) * 0.2  # bonus if within last week
        )
        concerns = novelty_concerns(c, history_bags, args.novelty_threshold)
        # Each high-distance overlap reduces total.
        for score, _ in concerns:
            total -= score * 1.5
        scored.append((total, c, concerns))

    scored.sort(key=lambda t: t[0], reverse=True)
    scored = scored[: args.top]

    out = render(scored, meta, args.published_window, len(history_bags), args.novelty_threshold)
    if args.output:
        args.output.write_text(out, encoding="utf-8")
    else:
        sys.stdout.write(out)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
