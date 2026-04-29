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


class NormalizeUrlForDedupTest(unittest.TestCase):
    """G3 — locale-prefix collapsing."""

    def test_strips_two_letter_locale_prefix(self) -> None:
        self.assertEqual(
            DEDUPE.normalize_url_for_dedup("https://cohere.com/fr/about"),
            DEDUPE.normalize_url_for_dedup("https://cohere.com/about"),
        )

    def test_strips_hyphenated_regional_locale(self) -> None:
        self.assertEqual(
            DEDUPE.normalize_url_for_dedup("https://example.com/zh-CN/blog/post"),
            DEDUPE.normalize_url_for_dedup("https://example.com/blog/post"),
        )

    def test_does_not_strip_non_locale_first_segment(self) -> None:
        normalized = DEDUPE.normalize_url_for_dedup("https://cohere.com/blog/x")
        self.assertIn("/blog/x", normalized)

    def test_does_not_strip_locale_in_later_segments(self) -> None:
        # We only strip the first segment to avoid merging unrelated content
        a = DEDUPE.normalize_url_for_dedup("https://example.com/blog/fr/post1")
        b = DEDUPE.normalize_url_for_dedup("https://example.com/blog/post1")
        self.assertNotEqual(a, b)

    def test_strips_www_prefix(self) -> None:
        self.assertEqual(
            DEDUPE.normalize_url_for_dedup("https://www.example.com/x"),
            DEDUPE.normalize_url_for_dedup("https://example.com/x"),
        )

    def test_drops_query_and_fragment(self) -> None:
        self.assertEqual(
            DEDUPE.normalize_url_for_dedup("https://example.com/x?utm=foo#frag"),
            DEDUPE.normalize_url_for_dedup("https://example.com/x"),
        )


class DedupeWithLocaleCollapsingTest(unittest.TestCase):
    """End-to-end: i18n duplicates collapse, summary reports it."""

    def test_collapses_localized_about_pages(self) -> None:
        doc = {
            "updates": [
                _upd("https://cohere.com/about", title="About"),
                _upd("https://cohere.com/fr/about", title="À propos"),
                _upd("https://cohere.com/zh-CN/about", title="关于"),
                _upd("https://cohere.com/blog/post-1", title="Post 1"),
            ]
        }
        out, summary = DEDUPE.dedupe(doc)
        # 3 about variants collapse to 1, plus 1 blog post = 2 total
        self.assertEqual(summary["output_count"], 2)
        self.assertEqual(summary["duplicate_groups"], 1)
        self.assertEqual(summary["locale_collapsed_groups"], 1)
        self.assertEqual(summary["removed"], 2)

    def test_no_locale_collapse_flag_disables(self) -> None:
        doc = {
            "updates": [
                _upd("https://cohere.com/about", title="About"),
                _upd("https://cohere.com/fr/about", title="À propos"),
            ]
        }
        out, summary = DEDUPE.dedupe(doc, normalize_locale=False)
        # No collapse — both records retained
        self.assertEqual(summary["output_count"], 2)
        self.assertEqual(summary["duplicate_groups"], 0)

    def test_locale_collapsed_only_counts_when_raw_urls_differ(self) -> None:
        # Exact-duplicate URLs collapse but should NOT be counted as
        # locale-collapsed, because no locale collision happened.
        doc = {
            "updates": [
                _upd("https://example.com/x", title="A"),
                _upd("https://example.com/x", title="B"),
            ]
        }
        out, summary = DEDUPE.dedupe(doc)
        self.assertEqual(summary["duplicate_groups"], 1)
        self.assertEqual(summary["locale_collapsed_groups"], 0)


if __name__ == "__main__":
    unittest.main()
