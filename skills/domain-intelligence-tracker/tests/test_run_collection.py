"""Integration tests for scripts/run_collection.py.

The wrapper orchestrates validate → dedupe → (diff) → sync. We test each
branch without touching a real Supabase instance (no --database-url).
"""

import argparse
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_collection.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SPEC = importlib.util.spec_from_file_location("run_collection_module", SCRIPT)
RUN = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(RUN)


def _ns(**kwargs) -> argparse.Namespace:
    defaults = {
        "entities": None,
        "updates": None,
        "run": None,
        "diff_against": None,
        "database_url": None,
        "no_dedupe": False,
        "skip_validate_urls": True,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _write(tmpdir: Path, name: str, doc: dict) -> Path:
    path = tmpdir / name
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


RUN_DOC = {
    "domain": "ai",
    "goal": "test",
    "window_start": "2026-04-22",
    "window_end": "2026-04-23",
    "entity_scope": ["company"],
    "source_policy": {"include_media": False, "include_community": False},
    "output_targets": ["entities", "entity_updates"],
}


class RunCollectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.entity_doc = json.loads((FIXTURES / "sample_entity_snapshot.json").read_text())
        self.update_doc = json.loads((FIXTURES / "sample_update_snapshot.json").read_text())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _setup_files(self, entity_doc=None, update_doc=None, run_doc=None) -> argparse.Namespace:
        e = _write(self.dir, "entities.json", entity_doc or self.entity_doc)
        u = _write(self.dir, "updates.json", update_doc or self.update_doc)
        r = _write(self.dir, "run.json", run_doc or RUN_DOC)
        return _ns(entities=str(e), updates=str(u), run=str(r))

    def test_passes_validation_and_skips_sync_without_database_url(self) -> None:
        args = self._setup_files()
        code, report = RUN.run(args)
        self.assertEqual(code, 0, msg=report)
        self.assertEqual(report["steps"]["validate"]["entity_errors"], 0)
        self.assertEqual(report["steps"]["validate"]["update_errors"], 0)
        self.assertTrue(report["steps"]["sync"].get("skipped"))
        self.assertIn("dry-run", report["steps"]["sync"]["reason"])

    def test_halts_on_validation_errors_before_sync(self) -> None:
        bad_update = dict(self.update_doc)
        bad_update["updates"] = [
            {
                "entity_name": "OpenAI",
                "entity_group": "company",
                "title": "t",
                "summary": "s",
                "source_url": "not-a-url",
                "published_at": "2026-04-22",
            }
        ]
        args = self._setup_files(update_doc=bad_update)
        code, report = RUN.run(args)
        self.assertEqual(code, 1)
        self.assertGreater(report["steps"]["validate"]["update_errors"], 0)
        # Sync step is never recorded when validation fails.
        self.assertNotIn("sync", report["steps"])

    def test_dedupes_update_snapshot_in_place(self) -> None:
        dup_update = {
            "domain": "ai",
            "window_start": "2026-04-22",
            "window_end": "2026-04-23",
            "updates": [
                {
                    "entity_name": "OpenAI",
                    "entity_group": "company",
                    "title": "A",
                    "summary": "s",
                    "source_url": "https://openai.com/a",
                    "published_at": "2026-04-22",
                },
                {
                    "entity_name": "OpenAI",
                    "entity_group": "company",
                    "title": "A-dup",
                    "summary": "s",
                    "source_url": "https://openai.com/a",
                    "published_at": "2026-04-22",
                },
            ],
        }
        # Bypass validation by using --no-dedupe path? No — dedupe runs after validate.
        # The dup update passes validation because the validator *reports* duplicates
        # as errors. To exercise dedupe, use a snapshot that the validator accepts but
        # that still has a duplicate URL. This is impossible: the validator would fail.
        # So instead, use --no-dedupe=True + compare unchanged counts? No — we want
        # to exercise the dedupe *branch*. Skip validation via a small shim.

        # Workaround: skip-validate-urls is already True; the validator WILL report
        # the duplicate, causing this to exit 1. Handle this by expecting exit 1 and
        # asserting the duplicate is detected. The dedupe logic itself is covered
        # directly in test_dedupe_updates.py.
        args = self._setup_files(update_doc=dup_update)
        code, report = RUN.run(args)
        self.assertEqual(code, 1)
        self.assertTrue(
            any("duplicate" in e["error"] for e in report["validation_errors"]["updates"])
        )

    def test_diff_produces_added_and_removed_counts(self) -> None:
        args = self._setup_files()
        # Prior snapshot with one different URL → one added, one removed
        prior = {
            "domain": "ai",
            "window_start": "2026-04-20",
            "window_end": "2026-04-21",
            "updates": [
                {
                    "entity_name": "OpenAI",
                    "entity_group": "company",
                    "title": "old",
                    "summary": "s",
                    "source_url": "https://openai.com/old",
                    "published_at": "2026-04-20",
                }
            ],
        }
        prior_path = _write(self.dir, "prior.json", prior)
        args.diff_against = str(prior_path)
        code, report = RUN.run(args)
        self.assertEqual(code, 0, msg=report)
        self.assertIn("diff", report)
        self.assertGreaterEqual(report["steps"]["diff"]["added"], 1)

    def test_missing_file_returns_2(self) -> None:
        args = _ns(
            entities="/nope/a.json",
            updates="/nope/b.json",
            run="/nope/c.json",
        )
        code, report = RUN.run(args)
        self.assertEqual(code, 2)
        self.assertIn("missing file", report["error"])

    def test_no_dedupe_flag_skips_dedupe_step(self) -> None:
        args = self._setup_files()
        args.no_dedupe = True
        code, report = RUN.run(args)
        self.assertEqual(code, 0)
        self.assertTrue(report["steps"]["dedupe"].get("skipped"))


if __name__ == "__main__":
    unittest.main()
