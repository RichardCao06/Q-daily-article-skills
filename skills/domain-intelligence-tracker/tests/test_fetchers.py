"""Unit tests for the fetcher modules.

These tests do NOT make real network calls. We monkey-patch
`fetchers.base.http_get` to return fixture bytes.
"""

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "fetchers"

# Make scripts/ importable for `from fetchers import ...`
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from fetchers import base, RssFetcher, GitHubReleasesFetcher, SitemapFetcher, HtmlDatedFetcher  # noqa: E402
from fetchers import fetcher_chain_for, FETCHER_CHAIN  # noqa: E402
from fetchers import rss as rss_mod, github_releases as gh_mod, sitemap as sitemap_mod, html_dated as html_mod  # noqa: E402


def _read_fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class RssFetcherTest(unittest.TestCase):
    def test_parses_rss2_and_keeps_in_window(self) -> None:
        with mock.patch.object(rss_mod, "http_get", return_value=(_read_fixture("sample_rss.xml"), {})):
            f = RssFetcher()
            items, cache, reason = f.fetch(
                "https://example.com/feed.xml",
                window_start="2026-04-22",
                window_end="2026-04-24",
            )
        self.assertEqual(len(items), 2)
        self.assertEqual(reason, "rss:ok")
        urls = {it.source_url for it in items}
        self.assertIn("https://example.com/blog/post-a", urls)
        self.assertIn("https://example.com/blog/post-b", urls)
        self.assertNotIn("https://example.com/blog/post-c", urls)
        self.assertIn("https://example.com/blog/post-a", cache["last_seen_guids"])
        self.assertEqual(cache["last_publisher"], "Sample Lab Blog")

    def test_parses_atom(self) -> None:
        with mock.patch.object(rss_mod, "http_get", return_value=(_read_fixture("sample_atom.xml"), {})):
            f = RssFetcher()
            items, _, reason = f.fetch(
                "https://example.org/feed.atom",
                window_start="2026-04-22",
                window_end="2026-04-24",
            )
        self.assertEqual(len(items), 1)
        self.assertEqual(reason, "rss:ok")
        self.assertEqual(items[0].source_url, "https://example.org/article-1")
        self.assertTrue(items[0].published_at.startswith("2026-04-23"))

    def test_skips_items_already_in_cache(self) -> None:
        cache_in = {"last_seen_guids": ["https://example.com/blog/post-a"]}
        with mock.patch.object(rss_mod, "http_get", return_value=(_read_fixture("sample_rss.xml"), {})):
            f = RssFetcher()
            items, _, reason = f.fetch(
                "https://example.com/feed.xml",
                window_start="2026-04-22",
                window_end="2026-04-24",
                cache_for_url=cache_in,
            )
        urls = {it.source_url for it in items}
        self.assertNotIn("https://example.com/blog/post-a", urls)
        self.assertEqual(len(items), 1)
        self.assertEqual(reason, "rss:ok")

    def test_handles_304_not_modified(self) -> None:
        with mock.patch.object(rss_mod, "http_get", return_value=(b"", {})):
            f = RssFetcher()
            items, _, reason = f.fetch(
                "https://example.com/feed.xml",
                window_start="2026-04-22",
                window_end="2026-04-24",
                cache_for_url={"etag": "abc"},
            )
        self.assertEqual(items, [])
        self.assertEqual(reason, "rss:not_modified")

    def test_no_feed_discovered_returns_distinct_reason(self) -> None:
        # Pretend the seed URL returns HTML with no <link rel="alternate">
        with mock.patch.object(rss_mod, "http_get", return_value=(b"<html><body>nothing</body></html>", {})):
            f = RssFetcher()
            items, _, reason = f.fetch(
                "https://blog.example/no-feed-link/",  # not a feed URL
                window_start="2026-04-22",
                window_end="2026-04-24",
            )
        self.assertEqual(items, [])
        self.assertEqual(reason, "rss:no_feed_discovered")

    def test_fetch_error_carries_status_code(self) -> None:
        from fetchers.base import HttpError
        with mock.patch.object(rss_mod, "http_get", side_effect=HttpError(403, "forbidden")):
            f = RssFetcher()
            items, _, reason = f.fetch(
                "https://blog.example/",
                window_start="2026-04-22",
                window_end="2026-04-24",
            )
        self.assertEqual(items, [])
        self.assertEqual(reason, "rss:fetch_error_403")

    def test_fetch_error_timeout_label(self) -> None:
        from fetchers.base import HttpError
        with mock.patch.object(rss_mod, "http_get", side_effect=HttpError(-1, "timeout")):
            f = RssFetcher()
            items, _, reason = f.fetch(
                "https://blog.example/",
                window_start="2026-04-22",
                window_end="2026-04-24",
            )
        self.assertEqual(reason, "rss:fetch_error_timeout")

    def test_common_path_probe_recovers_when_html_link_missing(self) -> None:
        """Seed URL returns HTML with no <link rel="alternate">. The probe
        list (/feed, /rss.xml, etc.) should still find a valid feed."""
        rss_body = _read_fixture("sample_rss.xml")
        html_body = b"<html><body>no feed link</body></html>"

        def fake_http_get(url, timeout=12.0, extra_headers=None, follow_redirects=True, retry_on_block=True):
            # Seed URL returns HTML; the probe targets /feed.xml or /feed
            if url == "https://blog.example/" or url == "https://blog.example":
                return html_body, {}
            if url.endswith("/feed.xml") or url.endswith("/feed") or url.endswith("/feed/"):
                return rss_body, {}
            return b"", {}

        with mock.patch.object(rss_mod, "http_get", side_effect=fake_http_get):
            f = RssFetcher()
            items, _, reason = f.fetch(
                "https://blog.example/",
                window_start="2026-04-22",
                window_end="2026-04-24",
            )
        self.assertEqual(reason, "rss:ok")
        self.assertEqual(len(items), 2)

    def test_distinguishes_not_a_feed_from_feed_empty(self) -> None:
        # body that's HTML (not a feed) when fetcher hits a feed-like URL
        with mock.patch.object(rss_mod, "http_get", return_value=(b"<html></html>", {})):
            f = RssFetcher()
            items, _, reason = f.fetch(
                "https://example.com/feed.xml",
                window_start="2026-04-22",
                window_end="2026-04-24",
            )
        self.assertEqual(items, [])
        self.assertEqual(reason, "rss:not_a_feed")

    def test_youtube_handle_unresolved_returns_distinct_reason(self) -> None:
        # /@handle URL returns HTML with no channelId pattern → unresolved
        html_no_channel_id = b"<html><body>no UC id here</body></html>"
        with mock.patch.object(rss_mod, "http_get", return_value=(html_no_channel_id, {})):
            f = RssFetcher()
            items, _, reason = f.fetch(
                "https://www.youtube.com/@somehandle",
                window_start="2026-04-22",
                window_end="2026-04-24",
            )
        self.assertEqual(items, [])
        self.assertEqual(reason, "rss:youtube_handle_unresolved")

    def test_youtube_handle_resolves_via_channel_id_meta(self) -> None:
        # /@handle URL → first http_get returns HTML with channelId meta;
        # second http_get returns Atom feed
        atom_body = _read_fixture("sample_atom.xml")
        handle_html = b'<html><meta itemprop="channelId" content="UCabc123XYZ"></html>'

        def fake_http_get(url, timeout=12.0, extra_headers=None, follow_redirects=True):
            if "youtube.com/@" in url and "/feeds/" not in url:
                return handle_html, {}
            if "feeds/videos.xml" in url:
                return atom_body, {}
            return b"", {}

        with mock.patch.object(rss_mod, "http_get", side_effect=fake_http_get):
            f = RssFetcher()
            items, _, reason = f.fetch(
                "https://www.youtube.com/@some-channel",
                window_start="2026-04-22",
                window_end="2026-04-24",
            )
        self.assertEqual(reason, "rss:ok")
        self.assertEqual(len(items), 1)

    def test_no_items_in_window_returns_distinct_reason(self) -> None:
        with mock.patch.object(rss_mod, "http_get", return_value=(_read_fixture("sample_rss.xml"), {})):
            f = RssFetcher()
            items, _, reason = f.fetch(
                "https://example.com/feed.xml",
                window_start="2030-01-01",  # far future, no items will match
                window_end="2030-01-31",
            )
        self.assertEqual(items, [])
        self.assertEqual(reason, "rss:no_items_in_window")

    def test_youtube_channel_url_resolves_to_feeds_endpoint(self) -> None:
        from fetchers.rss import _resolve_platform_feed
        resolved = _resolve_platform_feed("https://www.youtube.com/channel/UC123abc")
        self.assertIn("/feeds/videos.xml?channel_id=UC123abc", resolved)


class GitHubReleasesFetcherTest(unittest.TestCase):
    def test_parses_releases_and_filters_window(self) -> None:
        body = _read_fixture("sample_github_releases.json")
        with mock.patch.object(gh_mod, "http_get", return_value=(body, {})):
            f = GitHubReleasesFetcher()
            items, cache, reason = f.fetch(
                "https://github.com/example/repo",
                window_start="2026-04-22",
                window_end="2026-04-24",
            )
        self.assertEqual(len(items), 1)
        self.assertEqual(reason, "github:ok")
        self.assertEqual(items[0].content_type, "release-notes")
        self.assertIn("v4.0.0", items[0].title)

    def test_returns_distinct_reason_for_non_github_url(self) -> None:
        f = GitHubReleasesFetcher()
        items, _, reason = f.fetch("https://example.com/", "2026-04-22", "2026-04-24")
        self.assertEqual(items, [])
        self.assertEqual(reason, "github:not_a_repo_url")

    def test_returns_distinct_reason_for_no_releases(self) -> None:
        with mock.patch.object(gh_mod, "http_get", return_value=(b"[]", {})):
            f = GitHubReleasesFetcher()
            items, _, reason = f.fetch(
                "https://github.com/example/repo", "2026-04-22", "2026-04-24",
            )
        self.assertEqual(items, [])
        self.assertEqual(reason, "github:no_releases")

    def test_org_url_falls_back_to_listing_top_repos(self) -> None:
        # Org URL like https://github.com/openai → list user/org repos →
        # walk each looking for releases in window. Mock returns 1 repo with
        # 1 release in window.
        org_repos_response = b'[{"full_name":"openai/whisper"}]'
        releases_response = _read_fixture("sample_github_releases.json")

        def fake_http_get(url, timeout=12.0, extra_headers=None, follow_redirects=True):
            if "/orgs/openai/repos" in url or "/users/openai/repos" in url:
                return org_repos_response, {}
            if "/repos/openai/whisper/releases" in url:
                return releases_response, {}
            return b"", {}

        with mock.patch.object(gh_mod, "http_get", side_effect=fake_http_get):
            f = GitHubReleasesFetcher()
            items, _, reason = f.fetch(
                "https://github.com/openai", "2026-04-22", "2026-04-24",
            )
        self.assertEqual(reason, "github:ok")
        self.assertEqual(len(items), 1)
        self.assertIn("openai/whisper", items[0].title)

    def test_api_error_carries_status_label(self) -> None:
        from fetchers.base import HttpError
        with mock.patch.object(gh_mod, "http_get", side_effect=HttpError(403, "rate-limited")):
            f = GitHubReleasesFetcher()
            items, _, reason = f.fetch(
                "https://github.com/example/repo", "2026-04-22", "2026-04-24",
            )
        self.assertEqual(reason, "github:api_error_403")


class SitemapFetcherTest(unittest.TestCase):
    def test_filters_lastmod_in_window(self) -> None:
        sitemap_bytes = _read_fixture("sample_sitemap.xml")
        with mock.patch.object(sitemap_mod, "http_get", return_value=(sitemap_bytes, {})):
            f = SitemapFetcher()
            items, _, reason = f.fetch(
                "https://example.com/",
                window_start="2026-04-22",
                window_end="2026-04-24",
            )
        urls = sorted(it.source_url for it in items)
        self.assertEqual(urls, [
            "https://example.com/post-recent-1",
            "https://example.com/post-recent-2",
        ])
        self.assertEqual(reason, "sitemap:ok")

    def test_returns_distinct_reason_for_not_found(self) -> None:
        with mock.patch.object(sitemap_mod, "http_get", side_effect=ConnectionError("boom")):
            f = SitemapFetcher()
            items, _, reason = f.fetch("https://example.com/", "2026-04-22", "2026-04-24")
        self.assertEqual(items, [])
        self.assertEqual(reason, "sitemap:not_found")


class HtmlDatedFetcherTest(unittest.TestCase):
    def test_extracts_og_title_summary_and_published_time(self) -> None:
        html = _read_fixture("sample_article.html")
        with mock.patch.object(html_mod, "http_get", return_value=(html, {})):
            f = HtmlDatedFetcher()
            items, _, reason = f.fetch(
                "https://lab.example/post-x",
                window_start="2026-04-22",
                window_end="2026-04-24",
            )
        self.assertEqual(len(items), 1)
        self.assertEqual(reason, "html:ok")
        self.assertIn("GPT-X drops", items[0].title)
        self.assertIn("opengraph description", items[0].summary)

    def test_returns_out_of_window_distinct_reason(self) -> None:
        html = _read_fixture("sample_article.html")
        with mock.patch.object(html_mod, "http_get", return_value=(html, {})):
            f = HtmlDatedFetcher()
            items, _, reason = f.fetch(
                "https://lab.example/post-x", "2025-01-01", "2025-01-31",
            )
        self.assertEqual(items, [])
        self.assertEqual(reason, "html:out_of_window")

    def test_no_date_returns_distinct_reason(self) -> None:
        with mock.patch.object(html_mod, "http_get", return_value=(b"<html><body>plain</body></html>", {})):
            f = HtmlDatedFetcher()
            items, _, reason = f.fetch(
                "https://lab.example/post-x", "2026-04-22", "2026-04-24",
            )
        self.assertEqual(items, [])
        self.assertEqual(reason, "html:no_date")

    def test_fetch_error_returns_distinct_reason(self) -> None:
        with mock.patch.object(html_mod, "http_get", side_effect=TimeoutError("slow")):
            f = HtmlDatedFetcher()
            items, _, reason = f.fetch(
                "https://lab.example/post-x", "2026-04-22", "2026-04-24",
            )
        self.assertEqual(items, [])
        self.assertEqual(reason, "html:fetch_error")


class FetcherChainRoutingTest(unittest.TestCase):
    def test_blog_routes_to_rss_then_html(self) -> None:
        chain = fetcher_chain_for("blog")
        self.assertIs(chain[0], RssFetcher)
        self.assertIs(chain[-1], HtmlDatedFetcher)

    def test_github_routes_only_to_github_releases(self) -> None:
        chain = fetcher_chain_for("github")
        self.assertEqual(chain, [GitHubReleasesFetcher])

    def test_x_returns_empty_chain_for_manual_handling(self) -> None:
        self.assertEqual(fetcher_chain_for("x"), [])
        self.assertEqual(fetcher_chain_for("linkedin"), [])
        self.assertEqual(fetcher_chain_for("discord"), [])


if __name__ == "__main__":
    unittest.main()
