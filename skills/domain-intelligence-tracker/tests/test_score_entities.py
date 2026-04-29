"""Unit tests for scripts/score_entities.py."""

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "score_entities.py"
SPEC = importlib.util.spec_from_file_location("score_entities_module", SCRIPT)
SCORE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(SCORE)


class ParseWeightsTest(unittest.TestCase):
    def test_defaults_when_no_spec(self) -> None:
        w = SCORE.parse_weights(None)
        for dim in SCORE.DIMENSIONS:
            self.assertIn(dim, w)

    def test_overrides_are_applied(self) -> None:
        w = SCORE.parse_weights("signal=5,output=0.5")
        self.assertEqual(w["signal"], 5)
        self.assertEqual(w["output"], 0.5)
        # unchanged dims keep defaults
        self.assertEqual(w["influence"], SCORE.DEFAULT_WEIGHTS["influence"])

    def test_unknown_dimension_raises(self) -> None:
        with self.assertRaises(ValueError):
            SCORE.parse_weights("nope=1")

    def test_malformed_spec_raises(self) -> None:
        with self.assertRaises(ValueError):
            SCORE.parse_weights("signal3")


class ScoreEntityTest(unittest.TestCase):
    def test_inline_scores_win_over_rank_fallback(self) -> None:
        entity = {
            "entity_group": "person",
            "name": "X",
            "rank": 20,
            "scores": {"signal": 3, "influence": 3, "output": 3, "ecosystem": 3, "near_term": 3},
        }
        # group_size is irrelevant when inline scores present
        out = SCORE.score_entity(entity, group_size=20)
        self.assertEqual(out, {"signal": 3, "influence": 3, "output": 3, "ecosystem": 3, "near_term": 3})

    def test_rank_fallback_maps_top_quartile_to_3(self) -> None:
        entity = {"entity_group": "person", "name": "Y", "rank": 1}
        out = SCORE.score_entity(entity, group_size=20)
        # rank 1 of 20 → top quartile → 3
        self.assertEqual(out["signal"], 3)

    def test_rank_fallback_bottom_quartile_maps_to_0(self) -> None:
        entity = {"entity_group": "person", "name": "Z", "rank": 20}
        out = SCORE.score_entity(entity, group_size=20)
        self.assertEqual(out["signal"], 0)

    def test_score_clipped_to_0_3_range(self) -> None:
        entity = {"scores": {"signal": 10, "influence": -2, "output": 2, "ecosystem": 2, "near_term": 2}}
        out = SCORE.score_entity(entity, group_size=1)
        self.assertEqual(out["signal"], 3)
        self.assertEqual(out["influence"], 0)


class BuildScoreboardTest(unittest.TestCase):
    def test_reranks_within_groups(self) -> None:
        doc = {
            "entities": [
                {"entity_group": "person", "name": "A", "rank": 2, "scores": {"signal": 3, "influence": 3, "output": 3, "ecosystem": 3, "near_term": 3}},
                {"entity_group": "person", "name": "B", "rank": 1, "scores": {"signal": 0, "influence": 0, "output": 0, "ecosystem": 0, "near_term": 0}},
            ]
        }
        rows = SCORE.build_scoreboard(doc, SCORE.DEFAULT_WEIGHTS, None)
        # A should get proposed_rank 1 because its total is highest
        by_name = {r["name"]: r for r in rows}
        self.assertEqual(by_name["A"]["proposed_rank"], 1)
        self.assertEqual(by_name["B"]["proposed_rank"], 2)
        # rank_delta: A was at 2, now 1 → delta = 1
        self.assertEqual(by_name["A"]["rank_delta"], 1)

    def test_group_filter_excludes_other_groups(self) -> None:
        doc = {
            "entities": [
                {"entity_group": "person", "name": "A", "rank": 1},
                {"entity_group": "company", "name": "C", "rank": 1},
            ]
        }
        rows = SCORE.build_scoreboard(doc, SCORE.DEFAULT_WEIGHTS, group_filter="person")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["entity_group"], "person")


if __name__ == "__main__":
    unittest.main()
