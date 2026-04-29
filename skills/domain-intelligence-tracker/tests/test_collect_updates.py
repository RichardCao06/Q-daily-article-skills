"""Unit tests for scripts/collect_updates.py."""

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "collect_updates.py"
SPEC = importlib.util.spec_from_file_location("collect_updates_module", SCRIPT)
COLLECT = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(COLLECT)


ENTITY_DOC = {
    "domain": "ai",
    "snapshot_date": "2026-04-20",
    "entities": [
        {
            "entity_group": "person",
            "name": "Sam Altman",
            "rank": 1,
            "status": "active",
            "sources": [
                {"source_type": "website", "url": "https://blog.samaltman.com/", "is_official": True, "is_primary": True},
                {"source_type": "x", "url": "https://x.com/sama", "is_official": True},
                {"source_type": "reddit", "url": "https://reddit.com/u/anon", "is_official": False},
            ],
        },
        {
            "entity_group": "company",
            "name": "OpenAI",
            "rank": 1,
            "status": "active",
            "sources": [
                {"source_type": "newsroom", "url": "https://openai.com/news", "is_official": True},
            ],
        },
        {
            "entity_group": "person",
            "name": "Retired Person",
            "rank": 99,
            "status": "retired",
            "retired_at": "2026-04-01",
            "sources": [
                {"source_type": "website", "url": "https://old.example/", "is_official": True},
            ],
        },
    ],
}


class BuildJobsTest(unittest.TestCase):
    def test_one_job_per_official_source_by_default(self) -> None:
        jobs = COLLECT.build_jobs(
            ENTITY_DOC, "2026-04-22", "2026-04-23",
            group_filter=None, include_community=False,
        )
        # 2 official from Sam Altman + 1 from OpenAI = 3
        self.assertEqual(len(jobs), 3)
        for job in jobs:
            self.assertTrue(job["is_official"])

    def test_community_sources_included_with_flag(self) -> None:
        jobs = COLLECT.build_jobs(
            ENTITY_DOC, "2026-04-22", "2026-04-23",
            group_filter=None, include_community=True,
        )
        self.assertEqual(len(jobs), 4)

    def test_retired_entities_are_skipped(self) -> None:
        jobs = COLLECT.build_jobs(
            ENTITY_DOC, "2026-04-22", "2026-04-23",
            group_filter=None, include_community=True,
        )
        names = {job["entity_name"] for job in jobs}
        self.assertNotIn("Retired Person", names)

    def test_group_filter_limits_output(self) -> None:
        jobs = COLLECT.build_jobs(
            ENTITY_DOC, "2026-04-22", "2026-04-23",
            group_filter="company", include_community=False,
        )
        for job in jobs:
            self.assertEqual(job["entity_group"], "company")

    def test_x_source_gets_handle_aware_query(self) -> None:
        jobs = COLLECT.build_jobs(
            ENTITY_DOC, "2026-04-22", "2026-04-23",
            group_filter=None, include_community=False,
        )
        x_jobs = [j for j in jobs if j["source_type"] == "x"]
        self.assertEqual(len(x_jobs), 1)
        query = x_jobs[0]["suggested_queries"][0]
        self.assertIn("site:x.com", query)
        self.assertIn("after:2026-04-22", query)

    def test_expected_update_template_is_populated(self) -> None:
        jobs = COLLECT.build_jobs(
            ENTITY_DOC, "2026-04-22", "2026-04-23",
            group_filter=None, include_community=False,
        )
        tpl = jobs[0]["expected_update_template"]
        for key in ("entity_group", "entity_name", "source_url", "title", "summary", "published_at", "is_official"):
            self.assertIn(key, tpl)


class DomainOfTest(unittest.TestCase):
    def test_strips_protocol_and_path(self) -> None:
        self.assertEqual(COLLECT._domain_of("https://blog.samaltman.com/posts/1"), "blog.samaltman.com")
        self.assertEqual(COLLECT._domain_of("http://openai.com"), "openai.com")
        self.assertEqual(COLLECT._domain_of(""), "")


if __name__ == "__main__":
    unittest.main()
