"""Tests for enrich.py — verifying the title/summary backfill on
sitemap-derived rows."""

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "fetchers"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

# Load enrich.py as a module
spec = importlib.util.spec_from_file_location("enrich", SCRIPTS / "enrich.py")
ENRICH = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(ENRICH)


SAMPLE_HTML = (FIXTURES / "sample_article.html").read_bytes()


def _row(title: str = "", summary: str = "", source_url: str = "https://lab.example/x") -> dict:
    return {
        "entity_group": "company",
        "entity_name": "X",
        "source_url": source_url,
        "title": title,
        "summary": summary,
        "published_at": "2026-04-23T10:00:00Z",
        "source_platform": "website",
    }


class EnrichTest(unittest.TestCase):
    def test_fills_empty_title_and_summary_from_og_meta(self) -> None:
        row = _row(title="", summary="")
        with mock.patch.object(ENRICH, "http_get", return_value=(SAMPLE_HTML, {})):
            ENRICH.enrich_row(row, timeout=1.0)
        self.assertIn("GPT-X drops", row["title"])
        self.assertIn("opengraph description", row["summary"])
        self.assertEqual(row["enrichment"]["status"], "ok")
        self.assertIn("title", row["enrichment"]["fields_added"])
        self.assertIn("summary", row["enrichment"]["fields_added"])

    def test_preserves_existing_title_does_not_overwrite(self) -> None:
        row = _row(title="Pre-existing title", summary="")
        with mock.patch.object(ENRICH, "http_get", return_value=(SAMPLE_HTML, {})):
            ENRICH.enrich_row(row, timeout=1.0)
        self.assertEqual(row["title"], "Pre-existing title")
        self.assertIn("opengraph description", row["summary"])
        self.assertIn("summary", row["enrichment"]["fields_added"])
        self.assertNotIn("title", row["enrichment"]["fields_added"])

    def test_records_fetch_error_with_status(self) -> None:
        from fetchers.base import HttpError
        row = _row()
        with mock.patch.object(ENRICH, "http_get", side_effect=HttpError(403, "blocked")):
            ENRICH.enrich_row(row, timeout=1.0)
        self.assertEqual(row["enrichment"]["status"], "fetch_error_403")
        self.assertEqual(row["title"], "")

    def test_records_no_fields_when_html_has_no_meta(self) -> None:
        row = _row()
        with mock.patch.object(ENRICH, "http_get", return_value=(b"<html><body>plain</body></html>", {})):
            ENRICH.enrich_row(row, timeout=1.0)
        self.assertEqual(row["enrichment"]["status"], "no_fields_extracted")

    def test_only_empty_filter(self) -> None:
        # only-empty=True → only rows with both title AND summary empty
        self.assertTrue(ENRICH.needs_enrichment(_row("", ""), only_both_empty=True))
        self.assertFalse(ENRICH.needs_enrichment(_row("X", ""), only_both_empty=True))
        # default: enrich if either is empty
        self.assertTrue(ENRICH.needs_enrichment(_row("X", ""), only_both_empty=False))
        self.assertFalse(ENRICH.needs_enrichment(_row("X", "Y"), only_both_empty=False))


if __name__ == "__main__":
    unittest.main()
