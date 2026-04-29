"""Source-type fetchers for execute_jobs.py.

Each fetcher pulls items from a single source URL and returns records that
match the `expected_update_template` shape from collect_updates.py:

    {
        "entity_name":     <pre-filled by executor>,
        "entity_group":    <pre-filled by executor>,
        "source_url":      <item URL — different from the source feed URL>,
        "source_platform": "blog" / "github" / "youtube" / etc.,
        "source_domain":   <domain of source_url>,
        "title":           <item title>,
        "summary":         <1-3 sentence factual summary>,
        "published_at":    "YYYY-MM-DDTHH:MM:SSZ",
        "content_type":    "post" / "release-notes" / "news" / etc.,
        "is_official":     <pre-filled by executor>,
        "raw_source": {
            "publisher":       <feed/site name>,
            "published_label": <original date string>,
        }
    }

Fetchers raise `ManualFetchRequired` when they can't proceed and the source
needs human attention (e.g. X/LinkedIn/Discord).
"""

from .base import Fetcher, FetchResult, ManualFetchRequired
from .rss import RssFetcher
from .github_releases import GitHubReleasesFetcher
from .sitemap import SitemapFetcher
from .html_dated import HtmlDatedFetcher


# Map source_type → ordered list of fetcher classes to try (first success wins)
FETCHER_CHAIN: dict[str, list[type[Fetcher]]] = {
    # platforms with reliable RSS / API
    "blog":          [RssFetcher, HtmlDatedFetcher],
    "newsroom":      [RssFetcher, HtmlDatedFetcher],
    "press":         [RssFetcher, HtmlDatedFetcher],
    "podcast":       [RssFetcher],
    "newsletter":    [RssFetcher, HtmlDatedFetcher],
    "youtube":       [RssFetcher],            # /feeds/videos.xml?channel_id=…
    "reddit":        [RssFetcher],            # /<sub>/.rss
    "forum":         [RssFetcher],
    "github":        [GitHubReleasesFetcher],
    "release-notes": [GitHubReleasesFetcher, HtmlDatedFetcher, RssFetcher],
    "changelog":     [HtmlDatedFetcher, RssFetcher],
    "docs":          [HtmlDatedFetcher],
    "website":       [SitemapFetcher, HtmlDatedFetcher, RssFetcher],
    # platforms requiring manual fetch (no public RSS / API)
    "x":             [],
    "linkedin":      [],
    "discord":       [],
}


def fetcher_chain_for(source_type: str) -> list[type[Fetcher]]:
    return FETCHER_CHAIN.get(source_type, [HtmlDatedFetcher])


__all__ = [
    "Fetcher",
    "FetchResult",
    "ManualFetchRequired",
    "RssFetcher",
    "GitHubReleasesFetcher",
    "SitemapFetcher",
    "HtmlDatedFetcher",
    "FETCHER_CHAIN",
    "fetcher_chain_for",
]
