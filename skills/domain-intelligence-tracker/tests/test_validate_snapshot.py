"""Unit tests for scripts/validate_snapshot.py."""

import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_snapshot.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SPEC = importlib.util.spec_from_file_location("validate_snapshot_module", SCRIPT)
VALIDATE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(VALIDATE)


class ValidateSnapshotTest(unittest.TestCase):
    def test_infers_kind_from_top_level_keys(self) -> None:
        self.assertEqual(VALIDATE.infer_kind({"entities": []}), "entity")
        self.assertEqual(VALIDATE.infer_kind({"updates": []}), "update")
        self.assertEqual(VALIDATE.infer_kind({"goal": "x"}), "run")
        self.assertEqual(VALIDATE.infer_kind({"foo": "bar"}), "unknown")

    def test_valid_entity_snapshot_yields_no_errors(self) -> None:
        doc = json.loads((FIXTURES / "sample_entity_snapshot.json").read_text())
        self.assertEqual(VALIDATE.validate_entity_snapshot(doc), [])

    def test_valid_update_snapshot_yields_no_errors(self) -> None:
        doc = json.loads((FIXTURES / "sample_update_snapshot.json").read_text())
        self.assertEqual(VALIDATE.validate_update_snapshot(doc), [])

    def test_entity_snapshot_catches_missing_required_fields(self) -> None:
        bad = {
            "domain": "ai",
            "snapshot_date": "not-a-date",
            "entities": [
                {"entity_group": "person"},  # missing name, rank
            ],
        }
        errors = VALIDATE.validate_entity_snapshot(bad)
        paths = {e["path"] for e in errors}
        self.assertIn("/snapshot_date", paths)
        self.assertIn("/entities[0]/name", paths)
        self.assertIn("/entities[0]/rank", paths)

    def test_entity_snapshot_rejects_duplicate_names(self) -> None:
        bad = {
            "domain": "ai",
            "snapshot_date": "2026-04-20",
            "entities": [
                {"entity_group": "person", "rank": 1, "name": "Sam"},
                {"entity_group": "person", "rank": 2, "name": "Sam"},
            ],
        }
        errors = VALIDATE.validate_entity_snapshot(bad)
        self.assertTrue(any("duplicate" in e["error"] for e in errors))

    def test_entity_snapshot_enforces_single_primary_source(self) -> None:
        bad = {
            "domain": "ai",
            "snapshot_date": "2026-04-20",
            "entities": [
                {
                    "entity_group": "person",
                    "rank": 1,
                    "name": "Sam",
                    "sources": [
                        {"source_type": "website", "url": "https://a.example", "is_primary": True},
                        {"source_type": "x", "url": "https://x.example", "is_primary": True},
                    ],
                }
            ],
        }
        errors = VALIDATE.validate_entity_snapshot(bad)
        self.assertTrue(any("is_primary=true" in e["error"] for e in errors))

    def test_entity_snapshot_requires_retired_at_for_retired_status(self) -> None:
        bad = {
            "domain": "ai",
            "snapshot_date": "2026-04-20",
            "entities": [
                {
                    "entity_group": "person",
                    "rank": 5,
                    "name": "Someone",
                    "status": "retired",
                }
            ],
        }
        errors = VALIDATE.validate_entity_snapshot(bad)
        self.assertTrue(any("retired_at" in e["path"] for e in errors))

    def test_update_snapshot_catches_out_of_window_publication_date(self) -> None:
        bad = {
            "domain": "ai",
            "window_start": "2026-04-22",
            "window_end": "2026-04-23",
            "updates": [
                {
                    "entity_group": "company",
                    "entity_name": "OpenAI",
                    "title": "x",
                    "summary": "y",
                    "source_url": "https://openai.com/x",
                    "published_at": "2026-04-20",
                }
            ],
        }
        errors = VALIDATE.validate_update_snapshot(bad)
        self.assertTrue(
            any("outside window" in e["error"] for e in errors),
            f"expected out-of-window error, got {errors}",
        )

    def test_update_snapshot_catches_duplicate_source_urls(self) -> None:
        bad = {
            "domain": "ai",
            "window_start": "2026-04-22",
            "window_end": "2026-04-23",
            "updates": [
                {
                    "entity_group": "company",
                    "entity_name": "OpenAI",
                    "title": "t",
                    "summary": "s",
                    "source_url": "https://openai.com/a",
                    "published_at": "2026-04-22",
                },
                {
                    "entity_group": "company",
                    "entity_name": "OpenAI",
                    "title": "t2",
                    "summary": "s2",
                    "source_url": "https://openai.com/a",
                    "published_at": "2026-04-23",
                },
            ],
        }
        errors = VALIDATE.validate_update_snapshot(bad)
        self.assertTrue(any("duplicate" in e["error"] for e in errors))

    def test_update_snapshot_rejects_non_http_urls(self) -> None:
        bad = {
            "domain": "ai",
            "window_start": "2026-04-22",
            "window_end": "2026-04-23",
            "updates": [
                {
                    "entity_group": "company",
                    "entity_name": "OpenAI",
                    "title": "t",
                    "summary": "s",
                    "source_url": "openai.com/a",  # missing scheme
                    "published_at": "2026-04-22",
                }
            ],
        }
        errors = VALIDATE.validate_update_snapshot(bad)
        self.assertTrue(any(e["path"].endswith("source_url") for e in errors))


if __name__ == "__main__":
    unittest.main()
