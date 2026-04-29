"""Unit tests for scripts/dedupe_updates.py."""

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "dedupe_updates.py"
SPEC = importlib.util.spec_from_file_location("dedupe_updates_module", SCRIPT)
DEDUPE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(DEDUPE)


def _upd(url, **kwargs):
    base = {
        "entity_group": "company",
        "entity_name": "X",
        "source_url": url,
        "title": kwargs.get("title", "t"),
        "summary": "s",
        "published_at": kwargs.get("published_at", "2026-04-22"),
    }
    if "collected_at" in kwargs:
        base["collected_at"] = kwargs["collected_at"]
    return base


class DedupeUpdatesTest(unittest.TestCase):
    def test_removes_duplicate_source_urls(self) -> None:
        doc = {
            "window_start": "2026-04-22",
            "window_end": "2026-04-23",
            "updates": [
                _upd("https://a", title="A1"),
                _upd("https://a", title="A2"),
                _upd("https://b", title="B1"),
            ],
        }
        out, summary = DEDUPE.dedupe(doc)
        self.assertEqual(summary["input_count"], 3)
        self.assertEqual(summary["duplicate_groups"], 1)
        self.assertEqual(summary["removed"], 1)
        self.assertEqual(summary["output_count"], 2)
        urls = [u["source_url"] for u in out["updates"]]
        self.assertEqual(sorted(urls), ["https://a", "https://b"])

    def test_keeps_earliest_collected_at_as_canonical(self) -> None:
        doc = {
            "updates": [
                _upd("https://a", title="late", collected_at="2026-04-23T10:00:00Z"),
                _upd("https://a", title="early", collected_at="2026-04-23T01:00:00Z"),
            ]
        }
        out, _ = DEDUPE.dedupe(doc)
        self.assertEqual(out["updates"][0]["title"], "early")

    def test_falls_back_to_published_at_when_collected_at_absent(self) -> None:
        doc = {
            "updates": [
                _upd("https://a", title="newer", published_at="2026-04-23"),
                _upd("https://a", title="older", published_at="2026-04-21"),
            ]
        }
        out, _ = DEDUPE.dedupe(doc)
        self.assertEqual(out["updates"][0]["title"], "older")

    def test_preserves_records_without_source_url_at_end(self) -> None:
        doc = {
            "updates": [
                {"entity_name": "X", "title": "no-url-item"},
                _upd("https://a", title="A"),
            ]
        }
        out, summary = DEDUPE.dedupe(doc)
        self.assertEqual(summary["without_source_url"], 1)
        # the url-less record is retained at the end
        self.assertEqual(out["updates"][-1]["title"], "no-url-item")

    def test_handles_non_list_updates_gracefully(self) -> None:
        doc = {"updates": None}
        out, summary = DEDUPE.dedupe(doc)
        self.assertEqual(out, doc)
        self.assertIn("no updates[] array", summary["note"])


if __name__ == "__main__":
    unittest.main()
