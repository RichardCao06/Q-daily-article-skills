#!/usr/bin/env python3
r"""Final read pass — scan an article markdown for draft / meta-commentary / placeholder leaks.

This is the pre-publish "fresh-eyes" check. The fact-check pass verifies
NUMBERS; the layout pass verifies STRUCTURE. This pass verifies that the
prose **reads as a finished article to a reader**, not as planning notes
that leaked through from the topic-card step.

Categories of violation we catch:

  - meta-commentary   The article refers to itself as an article, or
                      cites the column-styles / writing-style rules
                      ("为什么这一篇值得在 `好论文` 栏目里发",
                       "按 `好论文` 栏目的约束……",
                       "这是好论文该有的样子",
                       "this article", "this piece", "in this column").

  - draft markers     `TODO`, `FIXME`, `XXX`, `HACK`, `WIP`, `PLACEHOLDER`,
                      `[draft]`, etc.

  - placeholder text  `[...]`, `<...>`, `{...}` containing instruction-like
                      hints ("[insert quote]", "<author name>", "{date}").
                      Bare bracketed Markdown links `[text](url)` are NOT
                      flagged.

  - empty blocks      Empty headings, empty list items.

  - suspect formatting Raw `**` or `__` floating in the body — usually
                      a half-finished bold tag.

  - 4th-wall slips    The grep test from writing-style.md anti-patterns:
                      strings like `按 \`好论文\``, `值得在`, `值得读`,
                      `这一段是.*的第一道工序`. These are sometimes
                      intentional (a metacritical piece about Q-daily
                      itself), so they're warnings not errors by default.

Usage:
    validate_article.py <markdown>
        [--strict]       treat warnings as errors (use in CI)
        [--json]         machine-readable output

Exit codes:
    0   no violations
    1   one or more errors found
    2   I/O error / bad input
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# violation patterns — (regex, severity, description)
# Severities:
#   "error"    — must be fixed before publish
#   "warning"  — looks suspicious but may be legitimate; --strict promotes
#                to error
# ---------------------------------------------------------------------------

# Meta-commentary: explicit references to the article / column from inside
# the prose. These are nearly always topic-card scaffolding that leaked.
META_COMMENTARY_PATTERNS = [
    # Section headings like "## 为什么这一篇值得在 `好论文` 栏目里发"
    (re.compile(r"^#{1,6}\s+为什么这[^#]*?(篇|稿|文章)[^#]*?(值得|栏目|发布|读)", re.MULTILINE),
     "error", "section heading is meta-commentary about the article itself"),
    # In-prose: "按 `好论文` 栏目的约束……"
    (re.compile(r"按\s*[`「『]?好(?:论文|文章|观点|家伙)[`」』]?\s*栏目"),
     "error", "prose cites column-styles rules ('按 `好论文` 栏目的约束')"),
    # In-prose: "这是好论文该有的样子"
    (re.compile(r"这是好(?:论文|文章|观点|家伙)\s*该有的"),
     "error", "prose cites column promise ('这是好论文该有的样子')"),
    # English equivalents — "this article" / "in this column"
    (re.compile(r"\b(?:this article|this piece|in this column)\b", re.IGNORECASE),
     "warning", "fourth-wall break ('this article' / 'in this column')"),
    # data-piece / explainer / etc. as a writing-method shoutout in prose
    (re.compile(r"这.{0,5}(?:段|篇).{0,15}是\s*(?:data-piece|explainer|column|news-brief|profile|interview|listicle|retrospective|feature)\s*的"),
     "error", "prose names the article-type ('这一段是 data-piece 的……')"),
    # Self-reference about column placement
    (re.compile(r"值得在\s*[`「『]?好(?:论文|文章|观点|家伙)[`」』]?\s*栏目"),
     "error", "self-reference about column placement ('值得在好论文栏目')"),
]

# Draft / WIP markers
DRAFT_MARKERS = [
    (re.compile(r"\b(?:TODO|FIXME|XXX|HACK|WIP)\b"),
     "error", "draft marker (TODO/FIXME/XXX/HACK/WIP)"),
    (re.compile(r"\b(?:placeholder|PLACEHOLDER|占位符)\b"),
     "error", "literal 'placeholder' / 占位符"),
    (re.compile(r"\b(?:lorem ipsum)\b", re.IGNORECASE),
     "error", "lorem ipsum text"),
    (re.compile(r"\[(?:draft|草稿|未完成)\]", re.IGNORECASE),
     "error", "[draft] / [草稿] tag"),
]

# Placeholder bracketed instructions — like [insert quote here], <author name>,
# {date}, etc. We deliberately whitelist `[text](url)` (links) and `[N]` /
# `[i]` (numeric footnote markers) and `[bold]` style mid-word.
# Strategy: flag bracket-content that LOOKS LIKE an editor instruction (verbs
# in imperative, "insert", "TBD", "to be", etc.).
PLACEHOLDER_PATTERNS = [
    (re.compile(r"\[(?:insert|add|fill in?|TBD|to be (?:added|determined)|TK|TKTK)[^\]]*\]", re.IGNORECASE),
     "error", "editor instruction in brackets ([insert ...] / [TBD] / [TKTK])"),
    (re.compile(r"<\s*(?:author|date|number|figure|chart|quote|source)\s*[^>]*>", re.IGNORECASE),
     "error", "angle-bracket placeholder (<author>, <date>, etc.)"),
    (re.compile(r"\{(?:author|date|number|figure|chart|quote|source|name)\b[^}]*\}", re.IGNORECASE),
     "error", "curly-brace placeholder ({author}, {date}, etc.)"),
]

# Empty blocks — a heading line with nothing after it, or a list bullet
# with no content
EMPTY_BLOCK_PATTERNS = [
    (re.compile(r"^#{1,6}\s*$", re.MULTILINE),
     "error", "empty heading"),
    (re.compile(r"^\s*[-*+]\s*$", re.MULTILINE),
     "error", "empty list item"),
    (re.compile(r"^\s*\d+\.\s*$", re.MULTILINE),
     "error", "empty numbered list item"),
]

# Half-finished markdown is hard to detect with a single regex (markdown's
# bold/italic rules tolerate cross-line spans). The simple-and-correct
# heuristic: a line with an ODD count of `**` (after stripping code spans)
# is suspicious. We do this in code rather than as a single regex.
SUSPECT_FORMATTING: list[tuple[re.Pattern, str, str]] = []  # checked separately, see _check_odd_bold


def _check_odd_bold(text: str) -> list[Violation]:
    """Return violations for lines with unbalanced ** markers."""
    out: list[Violation] = []
    code_span = re.compile(r"`[^`\n]*`")
    bold = re.compile(r"\*\*")
    for idx, line in enumerate(text.splitlines(), start=1):
        # Strip backtick-delimited code spans where ** is literal text
        stripped = code_span.sub("", line)
        # Count standalone ** sequences. Treat `***` as `**` + leftover
        # `*` (which itself is italic, ignored here).
        count = len(bold.findall(stripped))
        if count > 0 and count % 2 == 1:
            col = stripped.find("**") + 1
            out.append(Violation(
                line=idx, col=col,
                severity="warning",
                category="formatting",
                description="line has odd number of `**` markers (likely unclosed bold)",
                snippet=line[:80],
            ))
    return out


@dataclass
class Violation:
    line: int
    col: int
    severity: str
    category: str
    description: str
    snippet: str


def _line_col(text: str, offset: int) -> tuple[int, int]:
    """Convert a flat byte offset into 1-based (line, col)."""
    pre = text[:offset]
    line = pre.count("\n") + 1
    last_nl = pre.rfind("\n")
    col = offset - (last_nl + 1) + 1
    return line, col


def _scan(text: str, patterns: list[tuple[re.Pattern, str, str]], category: str) -> list[Violation]:
    out: list[Violation] = []
    for pat, severity, desc in patterns:
        for m in pat.finditer(text):
            line, col = _line_col(text, m.start())
            snippet = m.group(0)
            if len(snippet) > 80:
                snippet = snippet[:77] + "…"
            out.append(Violation(
                line=line, col=col,
                severity=severity, category=category,
                description=desc,
                snippet=snippet,
            ))
    return out


def parse_frontmatter_and_body(text: str) -> tuple[str, str]:
    """Returns (frontmatter, body). Empty frontmatter if missing."""
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not m:
        return "", text
    return m.group(1), m.group(2).lstrip("\n")


def validate(text: str) -> list[Violation]:
    """Run all checks against the BODY of the article (frontmatter excluded)."""
    _frontmatter, body = parse_frontmatter_and_body(text)

    violations: list[Violation] = []
    violations.extend(_scan(body, META_COMMENTARY_PATTERNS, "meta-commentary"))
    violations.extend(_scan(body, DRAFT_MARKERS, "draft-marker"))
    violations.extend(_scan(body, PLACEHOLDER_PATTERNS, "placeholder"))
    violations.extend(_scan(body, EMPTY_BLOCK_PATTERNS, "empty-block"))
    violations.extend(_check_odd_bold(body))
    return violations


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def render_human(violations: list[Violation], path: Path) -> str:
    if not violations:
        return f"✅ {path.name}: no violations"

    errors = [v for v in violations if v.severity == "error"]
    warnings = [v for v in violations if v.severity == "warning"]

    lines = [f"📋 {path.name}: {len(errors)} error(s), {len(warnings)} warning(s)", ""]
    by_cat: dict[str, list[Violation]] = {}
    for v in violations:
        by_cat.setdefault(v.category, []).append(v)
    for cat, vs in by_cat.items():
        lines.append(f"  {cat}:")
        for v in vs:
            badge = "❌" if v.severity == "error" else "⚠️ "
            lines.append(f"    {badge} L{v.line}:{v.col}  {v.description}")
            lines.append(f"        > {v.snippet}")
        lines.append("")
    return "\n".join(lines)


def render_json(violations: list[Violation], path: Path) -> str:
    return json.dumps({
        "path": str(path),
        "violation_count": len(violations),
        "errors": sum(1 for v in violations if v.severity == "error"),
        "warnings": sum(1 for v in violations if v.severity == "warning"),
        "violations": [
            {
                "line": v.line,
                "col": v.col,
                "severity": v.severity,
                "category": v.category,
                "description": v.description,
                "snippet": v.snippet,
            }
            for v in violations
        ],
    }, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("markdown", type=Path)
    ap.add_argument("--strict", action="store_true",
                    help="Treat warnings as errors. Use in CI.")
    ap.add_argument("--json", action="store_true",
                    help="Machine-readable output.")
    args = ap.parse_args()

    if not args.markdown.exists():
        print(f"no such file: {args.markdown}", file=sys.stderr)
        return 2

    try:
        text = args.markdown.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(f"read failed: {e}", file=sys.stderr)
        return 2

    violations = validate(text)

    if args.json:
        print(render_json(violations, args.markdown))
    else:
        print(render_human(violations, args.markdown))

    has_errors = any(v.severity == "error" for v in violations)
    has_warnings = any(v.severity == "warning" for v in violations)

    if has_errors:
        return 1
    if args.strict and has_warnings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
