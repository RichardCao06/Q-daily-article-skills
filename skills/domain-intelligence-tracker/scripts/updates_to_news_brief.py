#!/usr/bin/env python3
"""Turn a tracker update snapshot into a daily-article-editor news-brief draft.

Reads an `update-snapshot` JSON file (schema in `references/data-model.md`) and
emits a Markdown draft that conforms to the daily-article-editor skill's
`news-brief / bucketed` structure:

    # 大公司头条：<lede 1>，<lede 2>
    **摘要**
    <fixed boilerplate>
    ### <Bucket A>
    **<lede>** <body>.
    ...

Bucketing strategies:

- `by_group`   — buckets = entity_group (company / person / product / …)
- `by_offical` — buckets = `官方动态` vs `其他`
- `top_plus`   — buckets = `Top / 重点板块`, `东八区 / 区域`, `Also in the News …`
                 (the Qdaily default). The `top` bucket holds updates where
                 `is_official == true` AND the entity ranks high in the latest
                 entity snapshot (when one is provided).

Usage:
    python3 updates_to_news_brief.py <updates.json>
        [--bucketing by_group|by_official|top_plus]
        [--entity-snapshot entities.json]
        [--top-rank-threshold N]
        [--title-prefix "大公司头条"]
        [--output FILE]

If --output is omitted, the draft is written to stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


STANDING_DEK = "我们每天早上为你摘取最重要的商业新闻。"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _entity_rank_index(entity_doc: dict | None) -> dict[tuple[str, str], int]:
    if not entity_doc:
        return {}
    index: dict[tuple[str, str], int] = {}
    for e in entity_doc.get("entities", []):
        if "rank" in e and "name" in e and "entity_group" in e:
            try:
                index[(e["entity_group"], e["name"])] = int(e["rank"])
            except (TypeError, ValueError):
                pass
    return index


def _update_lede(upd: dict) -> str:
    """A single mini-headline form `<entity_name>: <title>`. Trimmed."""
    entity = upd.get("entity_name") or "—"
    title = (upd.get("title") or "").strip()
    if not title:
        title = "（无标题）"
    # A headline in Qdaily big-story format is ~18-40 chars; trim longer ones.
    if len(title) > 40:
        title = title[:38] + "…"
    return f"{entity}：{title}"


def _item_markdown(upd: dict) -> str:
    """One news-brief paragraph: bolded lede + body + source link."""
    lede = _update_lede(upd)
    summary = (upd.get("summary") or "").strip().rstrip("。")
    source_url = upd.get("source_url", "")
    parts = [f"**{lede}。**"]
    if summary:
        parts.append(summary + "。")
    if source_url:
        publisher = (upd.get("raw_source") or {}).get("publisher") or upd.get("source_domain") or "原文"
        parts.append(f"[（{publisher}）]({source_url})")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Bucketing strategies
# ---------------------------------------------------------------------------

def bucket_by_group(updates: list[dict]) -> list[tuple[str, list[dict]]]:
    groups: dict[str, list[dict]] = {}
    for u in updates:
        key = u.get("entity_group", "其他")
        groups.setdefault(key, []).append(u)
    ordering = ["company", "product", "person", "institution", "project"]
    out: list[tuple[str, list[dict]]] = []
    for k in ordering:
        if k in groups:
            out.append((f"{_group_label(k)}", groups.pop(k)))
    for k, v in groups.items():
        out.append((_group_label(k), v))
    return out


def bucket_by_official(updates: list[dict]) -> list[tuple[str, list[dict]]]:
    official = [u for u in updates if u.get("is_official")]
    other = [u for u in updates if not u.get("is_official")]
    result = []
    if official:
        result.append(("官方动态", official))
    if other:
        result.append(("其他", other))
    return result


def bucket_top_plus(
    updates: list[dict],
    rank_index: dict[tuple[str, str], int],
    top_rank_threshold: int,
) -> list[tuple[str, list[dict]]]:
    top: list[dict] = []
    regional: list[dict] = []
    also: list[dict] = []
    for u in updates:
        key = (u.get("entity_group", ""), u.get("entity_name", ""))
        rank = rank_index.get(key)
        is_official = bool(u.get("is_official"))
        if is_official and rank is not None and rank <= top_rank_threshold:
            top.append(u)
        elif is_official:
            regional.append(u)
        else:
            also.append(u)
    buckets: list[tuple[str, list[dict]]] = []
    if top:
        buckets.append(("Top 15 - 改变生活方式的公司", top))
    if regional:
        buckets.append(("东八区商业新闻", regional))
    if also:
        buckets.append(("Also in the News …", also))
    return buckets


_GROUP_LABELS = {
    "company": "公司动态",
    "product": "产品动态",
    "person": "人事动态",
    "institution": "机构动态",
    "project": "项目动态",
}


def _group_label(key: str) -> str:
    return _GROUP_LABELS.get(key, key)


# ---------------------------------------------------------------------------
# Draft renderer
# ---------------------------------------------------------------------------

def render_news_brief(
    update_doc: dict,
    buckets: list[tuple[str, list[dict]]],
    title_prefix: str = "大公司头条",
    dek: str = STANDING_DEK,
) -> str:
    # Headline: prefix + first 1-2 ledes
    first_ledes: list[str] = []
    for _, items in buckets:
        for u in items:
            first_ledes.append(_update_lede(u))
            if len(first_ledes) == 2:
                break
        if len(first_ledes) == 2:
            break
    if first_ledes:
        headline = f"{title_prefix}：{'，'.join(first_ledes)}"
    else:
        window = f"{update_doc.get('window_start','?')}–{update_doc.get('window_end','?')}"
        headline = f"{title_prefix}：{window} 无重点条目"

    lines = [f"# {headline}", "", "**摘要**", dek, ""]

    if not buckets:
        lines.append("（时间窗内无条目。）")
    else:
        for bucket_name, items in buckets:
            lines.append(f"### {bucket_name}")
            lines.append("")
            for u in items:
                lines.append(_item_markdown(u))
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_draft(
    update_doc: dict,
    bucketing: str,
    entity_doc: dict | None,
    top_rank_threshold: int,
    title_prefix: str,
) -> str:
    updates = update_doc.get("updates", [])
    if bucketing == "by_group":
        buckets = bucket_by_group(updates)
    elif bucketing == "by_official":
        buckets = bucket_by_official(updates)
    elif bucketing == "top_plus":
        buckets = bucket_top_plus(
            updates,
            _entity_rank_index(entity_doc),
            top_rank_threshold,
        )
    else:
        raise ValueError(f"unknown bucketing: {bucketing}")
    return render_news_brief(update_doc, buckets, title_prefix=title_prefix)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("updates", help="update-snapshot JSON")
    parser.add_argument(
        "--bucketing",
        choices=["by_group", "by_official", "top_plus"],
        default="top_plus",
    )
    parser.add_argument("--entity-snapshot", default=None)
    parser.add_argument("--top-rank-threshold", type=int, default=15)
    parser.add_argument("--title-prefix", default="大公司头条")
    parser.add_argument("--output", default=None)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    update_path = Path(args.updates)
    if not update_path.exists():
        print(f"No such file: {args.updates}", file=sys.stderr)
        return 2
    update_doc = _load(update_path)

    entity_doc = None
    if args.entity_snapshot:
        entity_path = Path(args.entity_snapshot)
        if not entity_path.exists():
            print(f"No such entity snapshot: {args.entity_snapshot}", file=sys.stderr)
            return 2
        entity_doc = _load(entity_path)

    draft = build_draft(
        update_doc=update_doc,
        bucketing=args.bucketing,
        entity_doc=entity_doc,
        top_rank_threshold=args.top_rank_threshold,
        title_prefix=args.title_prefix,
    )

    if args.output:
        Path(args.output).write_text(draft, encoding="utf-8")
    else:
        sys.stdout.write(draft)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
