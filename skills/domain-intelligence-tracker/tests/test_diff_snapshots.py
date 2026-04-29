"""Unit tests for scripts/diff_snapshots.py."""

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "diff_snapshots.py"
SPEC = importlib.util.spec_from_file_location("diff_snapshots_module", SCRIPT)
DIFF = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(DIFF)


def _entity(group: str, name: str, rank: int, **kwargs) -> dict:
    base = {"entity_group": group, "name": name, "rank": rank}
    base.update(kwargs)
    return base


class DiffEntitySnapshotTest(unittest.TestCase):
    def test_detects_added_and_removed_entities(self) -> None:
        before = {
            "snapshot_date": "2026-04-14",
            "entities": [_entity("person", "Alice", 1), _entity("person", "Bob", 2)],
        }
        after = {
            "snapshot_date": "2026-04-20",
            "entities": [
                _entity("person", "Alice", 1),
                _entity("person", "Carol", 2),
            ],
        }
        report = DIFF.diff_entity_snapshots(before, after)
        self.assertEqual(report["added"], [{"entity_group": "person", "name": "Carol"}])
        self.assertEqual(report["removed"], [{"entity_group": "person", "name": "Bob"}])

    def test_detects_rank_changes_for_kept_entities(self) -> None:
        before = {"entities": [_entity("person", "Alice", 5)]}
        after = {"entities": [_entity("person", "Alice", 2)]}
        report = DIFF.diff_entity_snapshots(before, after)
        self.assertEqual(
            report["rank_changed"],
            [{"entity_group": "person", "name": "Alice", "before_rank": 5, "after_rank": 2}],
        )

    def test_detects_status_transition_to_retired(self) -> None:
        before = {"entities": [_entity("person", "Alice", 1, status="active")]}
        after = {
            "entities": [
                _entity("person", "Alice", 1, status="retired", retired_at="2026-04-20")
            ]
        }
        report = DIFF.diff_entity_snapshots(before, after)
        self.assertEqual(len(report["status_changed"]), 1)
        self.assertEqual(report["status_changed"][0]["after_status"], "retired")

    def test_detects_source_additions_and_removals(self) -> None:
        before = {
            "entities": [
                _entity(
                    "person",
                    "Alice",
                    1,
                    sources=[{"url": "https://a.example"}],
                )
            ]
        }
        after = {
            "entities": [
                _entity(
                    "person",
                    "Alice",
                    1,
                    sources=[
                        {"url": "https://a.example"},
                        {"url": "https://x.com/alice"},
                    ],
                )
            ]
        }
        report = DIFF.diff_entity_snapshots(before, after)
        self.assertEqual(len(report["sources_added"]), 1)
        self.assertEqual(report["sources_added"][0]["urls"], ["https://x.com/alice"])
        self.assertEqual(report["sources_removed"], [])

    def test_detects_rename_via_stable_official_url(self) -> None:
        before = {
            "entities": [
                _entity("company", "Twitter", 1, official_url="https://twitter.com")
            ]
        }
        after = {
            "entities": [_entity("company", "X", 1, official_url="https://twitter.com")]
        }
        report = DIFF.diff_entity_snapshots(before, after)
        self.assertEqual(len(report["rename_candidates"]), 1)
        self.assertEqual(report["rename_candidates"][0]["after_name"], "X")


class DiffUpdateSnapshotTest(unittest.TestCase):
    def _upd(self, url: str, title: str, date: str) -> dict:
        return {
            "entity_group": "company",
            "entity_name": "OpenAI",
            "source_url": url,
            "title": title,
            "published_at": date,
        }

    def test_added_and_removed_updates_keyed_on_source_url(self) -> None:
        before = {
            "window_start": "2026-04-14",
            "window_end": "2026-04-20",
            "updates": [
                self._upd("https://a", "A", "2026-04-14"),
                self._upd("https://b", "B", "2026-04-15"),
            ],
        }
        after = {
            "window_start": "2026-04-21",
            "window_end": "2026-04-23",
            "updates": [
                self._upd("https://b", "B", "2026-04-15"),
                self._upd("https://c", "C", "2026-04-22"),
            ],
        }
        report = DIFF.diff_update_snapshots(before, after)
        self.assertEqual([r["source_url"] for r in report["added"]], ["https://c"])
        self.assertEqual([r["source_url"] for r in report["removed"]], ["https://a"])
        self.assertEqual(report["kept_count"], 1)


class DispatchTest(unittest.TestCase):
    def test_dispatches_by_top_level_keys(self) -> None:
        r1 = DIFF.diff({"entities": []}, {"entities": []})
        r2 = DIFF.diff({"updates": []}, {"updates": []})
        r3 = DIFF.diff({"entities": []}, {"updates": []})
        self.assertEqual(r1["kind"], "entity")
        self.assertEqual(r2["kind"], "update")
        self.assertEqual(r3["kind"], "mismatch")


if __name__ == "__main__":
    unittest.main()
