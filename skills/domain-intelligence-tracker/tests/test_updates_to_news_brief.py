"""Integration tests for the tracker → editor news-brief bridge.

These tests validate the Markdown output directly against the
daily-article-editor's `news-brief` structural rules (see the editor skill's
`references/news-brief-style.md`). They do NOT import the editor skill — the
bridge output is tested in isolation so this skill can be verified without
cross-skill coupling.
"""

import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "updates_to_news_brief.py"
SPEC = importlib.util.spec_from_file_location("updates_to_news_brief_module", SCRIPT)
BRIDGE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(BRIDGE)


def _mk_update(
    entity_name: str,
    entity_group: str,
    source_url: str,
    title: str,
    is_official: bool = True,
    publisher: str | None = None,
    summary: str = "摘要内容。",
) -> dict:
    u = {
        "entity_name": entity_name,
        "entity_group": entity_group,
        "source_url": source_url,
        "title": title,
        "summary": summary,
        "is_official": is_official,
        "published_at": "2026-04-22",
    }
    if publisher:
        u["raw_source"] = {"publisher": publisher}
    return u


SAMPLE_UPDATES = {
    "domain": "ai",
    "window_start": "2026-04-22",
    "window_end": "2026-04-23",
    "updates": [
        _mk_update("OpenAI", "company", "https://openai.com/a", "New product A", True, "OpenAI"),
        _mk_update("OpenAI", "company", "https://openai.com/b", "New product B", True, "OpenAI"),
        _mk_update("Some Lab", "company", "https://lab.example/x", "Talk", True),
        _mk_update("Community User", "person", "https://community.example/c", "Community take", False),
    ],
}

SAMPLE_ENTITIES = {
    "domain": "ai",
    "snapshot_date": "2026-04-20",
    "entities": [
        {"entity_group": "company", "name": "OpenAI", "rank": 1},
        {"entity_group": "company", "name": "Some Lab", "rank": 40},
        {"entity_group": "person", "name": "Community User", "rank": 5},
    ],
}


class BridgeStructureTest(unittest.TestCase):
    def test_output_begins_with_h1_following_news_brief_title_pattern(self) -> None:
        md = BRIDGE.build_draft(SAMPLE_UPDATES, "top_plus", SAMPLE_ENTITIES, 15, "大公司头条")
        first = md.splitlines()[0]
        self.assertTrue(first.startswith("# "))
        # Qdaily news-brief headlines have "<column>：<lede 1>，<lede 2>"
        self.assertIn("大公司头条：", first)
        self.assertIn("，", first)

    def test_output_contains_standing_dek_not_rewritten(self) -> None:
        md = BRIDGE.build_draft(SAMPLE_UPDATES, "top_plus", SAMPLE_ENTITIES, 15, "大公司头条")
        self.assertIn("**摘要**", md)
        self.assertIn(BRIDGE.STANDING_DEK, md)

    def test_top_plus_bucketing_routes_high_rank_official_updates_into_top_bucket(self) -> None:
        md = BRIDGE.build_draft(SAMPLE_UPDATES, "top_plus", SAMPLE_ENTITIES, 15, "大公司头条")
        # The two OpenAI (rank 1, official) items must appear under Top bucket.
        top_section = md.split("### Top 15")[1].split("### ")[0]
        self.assertIn("New product A", top_section)
        self.assertIn("New product B", top_section)
        # The non-official Community User update must be in "Also in the News"
        also_section = md.split("### Also in the News")[1] if "### Also in the News" in md else ""
        self.assertIn("Community take", also_section)
        # Some Lab (rank 40, official) — below threshold — goes to 东八区
        dongba = md.split("### 东八区商业新闻")[1].split("### ")[0]
        self.assertIn("Some Lab", dongba)

    def test_item_markdown_uses_bolded_lede_and_embeds_source_link(self) -> None:
        md = BRIDGE.build_draft(SAMPLE_UPDATES, "top_plus", SAMPLE_ENTITIES, 15, "大公司头条")
        # Every item begins with `**<lede>。**`
        # At least one item should match the expected pattern.
        self.assertTrue(re.search(r"\*\*OpenAI：New product A。\*\*", md))
        # Source URL is present as a markdown link
        self.assertIn("(https://openai.com/a)", md)

    def test_by_group_bucketing_produces_group_h3s(self) -> None:
        md = BRIDGE.build_draft(SAMPLE_UPDATES, "by_group", None, 15, "大公司头条")
        self.assertIn("### 公司动态", md)
        self.assertIn("### 人事动态", md)

    def test_by_official_bucketing_splits_official_from_other(self) -> None:
        md = BRIDGE.build_draft(SAMPLE_UPDATES, "by_official", None, 15, "大公司头条")
        self.assertIn("### 官方动态", md)
        self.assertIn("### 其他", md)

    def test_output_has_no_thematic_h2_which_would_violate_news_brief_style(self) -> None:
        md = BRIDGE.build_draft(SAMPLE_UPDATES, "top_plus", SAMPLE_ENTITIES, 15, "大公司头条")
        # news-brief forbids H2 section headings in the body
        h2_lines = [line for line in md.splitlines() if re.match(r"^##\s", line)]
        self.assertEqual(h2_lines, [])

    def test_empty_update_list_produces_placeholder_line(self) -> None:
        md = BRIDGE.build_draft(
            {"domain": "ai", "window_start": "2026-04-22", "window_end": "2026-04-22", "updates": []},
            "top_plus",
            None,
            15,
            "大公司头条",
        )
        self.assertIn("无重点条目", md)


class BridgeEndToEndTest(unittest.TestCase):
    def test_runs_against_real_repo_snapshot(self) -> None:
        """Smoke-test: the real 2026-04-23 AI update snapshot produces valid output."""
        updates_path = ROOT / "examples" / "ai-watchlist" / "ai-updates-2026-04-23.json"
        entities_path = ROOT / "examples" / "ai-watchlist" / "ai-entities-2026-04-20.json"
        if not updates_path.exists() or not entities_path.exists():
            self.skipTest("real snapshot fixtures not present")
        update_doc = json.loads(updates_path.read_text())
        entity_doc = json.loads(entities_path.read_text())
        md = BRIDGE.build_draft(update_doc, "top_plus", entity_doc, 15, "大公司头条")
        # Output should be non-empty markdown with standard header
        self.assertTrue(md.startswith("# 大公司头条"))
        self.assertIn("**摘要**", md)
        self.assertIn("### ", md)


if __name__ == "__main__":
    unittest.main()
