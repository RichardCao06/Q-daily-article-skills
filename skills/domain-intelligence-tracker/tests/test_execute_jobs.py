"""Integration test for execute_jobs.py.

Walks 4 mocked jobs (one of each handled source_type, plus one manual).
"""

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

# Import as a module so we can pass an in-memory jobs_doc
spec = importlib.util.spec_from_file_location("execute_jobs", SCRIPTS / "execute_jobs.py")
EXEC = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(EXEC)

from fetchers import (  # noqa: E402
    rss as rss_mod,
    github_releases as gh_mod,
    sitemap as sitemap_mod,
    html_dated as html_mod,
)


JOBS_DOC = {
    "domain": "ai",
    "window_start": "2026-04-22",
    "window_end": "2026-04-24",
    "jobs": [
        {
            "entity_group": "company",
            "entity_name":  "Sample Lab",
            "source_type":  "blog",
            "url":          "https://example.com/feed.xml",
            "is_official":  True,
        },
        {
            "entity_group": "product",
            "entity_name":  "Example",
            "source_type":  "github",
            "url":          "https://github.com/example/repo",
            "is_official":  True,
        },
        {
            "entity_group": "company",
            "entity_name":  "Atom Lab",
            "source_type":  "newsroom",
            "url":          "https://example.org/feed.atom",
            "is_official":  True,
        },
        {
            "entity_group": "person",
            "entity_name":  "Some Founder",
            "source_type":  "x",
            "url":          "https://x.com/founder",
            "is_official":  True,
        },
    ],
}


def _read(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class ExecuteJobsTest(unittest.TestCase):
    def test_walks_jobs_dispatches_to_correct_fetcher_emits_snapshot(self) -> None:
        # Map URL → fixture body for the mock to return
        url_map = {
            "https://example.com/feed.xml":               _read("sample_rss.xml"),
            "https://api.github.com/repos/example/repo/releases?per_page=20":
                                                           _read("sample_github_releases.json"),
            "https://example.org/feed.atom":              _read("sample_atom.xml"),
        }

        def fake_http_get(url, timeout=12.0, extra_headers=None, follow_redirects=True):
            for k, body in url_map.items():
                if url.startswith(k) or k in url:
                    return body, {"content-type": "application/xml"}
            return b"", {}

        # Patch http_get in each fetcher module's local namespace
        with mock.patch.object(rss_mod, "http_get", side_effect=fake_http_get), \
             mock.patch.object(gh_mod, "http_get", side_effect=fake_http_get), \
             mock.patch.object(sitemap_mod, "http_get", side_effect=fake_http_get), \
             mock.patch.object(html_mod, "http_get", side_effect=fake_http_get), \
             tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "executor.json"
            cache = {"version": 1, "domain": "ai", "saved_at": "", "entries": {}}
            result = EXEC.execute(
                JOBS_DOC, cache,
                max_per_source=10,
                include_manual=True,
                max_workers=4, per_job_timeout=5.0, overall_budget_s=60.0,
            )

        snap = result["snapshot"]
        stats = result["stats"]
        self.assertEqual(snap["domain"], "ai")
        urls = [u["source_url"] for u in snap["updates"]]
        self.assertIn("https://example.com/blog/post-a", urls)
        self.assertIn("https://example.org/article-1", urls)
        self.assertTrue(any("v4.0.0" in u["title"] for u in snap["updates"]))
        self.assertEqual(len(snap["manual_required"]), 1)
        self.assertEqual(snap["manual_required"][0]["source_type"], "x")
        # diagnostics aggregated across the run
        self.assertIn("rss:ok",    stats["reason_counts"])
        self.assertIn("github:ok", stats["reason_counts"])
        # diagnostics list also written out per-job
        self.assertIn("diagnostics", snap)
        self.assertEqual(len(snap["diagnostics"]), 3)  # 3 jobs walked a chain (the x job is manual)

    def test_max_per_source_caps_emissions(self) -> None:
        url_map = {
            "https://example.com/feed.xml": _read("sample_rss.xml"),
        }

        def fake_http_get(url, timeout=12.0, extra_headers=None, follow_redirects=True):
            for k, body in url_map.items():
                if url.startswith(k):
                    return body, {}
            return b"", {}

        with mock.patch.object(rss_mod, "http_get", side_effect=fake_http_get), \
             mock.patch.object(html_mod, "http_get", side_effect=fake_http_get), \
             tempfile.TemporaryDirectory() as tmpdir:
            cache = {"version": 1, "domain": "ai", "saved_at": "", "entries": {}}
            result = EXEC.execute(
                {"domain": "ai", "window_start": "2026-04-22", "window_end": "2026-04-24",
                 "jobs": [JOBS_DOC["jobs"][0]]},  # just the blog job
                cache,
                max_per_source=1,
                include_manual=False,
                max_workers=2, per_job_timeout=5.0, overall_budget_s=60.0,
            )
        self.assertEqual(len(result["snapshot"]["updates"]), 1)


if __name__ == "__main__":
    unittest.main()
