"""GitHub Releases fetcher (uses the public Releases API, no auth required).

Rate limit: 60 requests/hour for unauthenticated callers. Set the
`GITHUB_TOKEN` environment variable for 5000 req/hour.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
from typing import Optional

from .base import Fetcher, FetchResult, HttpError, http_get, in_window


_REPO_RE = re.compile(r"github\.com/([^/]+)/([^/?#]+)", re.IGNORECASE)
_ORG_RE = re.compile(r"^https?://github\.com/([A-Za-z0-9_.-]+)/?$", re.IGNORECASE)


def _parse_repo(url: str) -> Optional[tuple[str, str]]:
    m = _REPO_RE.search(url)
    if not m:
        return None
    return (m.group(1), m.group(2).rstrip(".git"))


def _parse_org(url: str) -> Optional[str]:
    """Return the org/user slug if URL looks like https://github.com/<slug> with
    no further path. Returns None for repo-level URLs."""
    m = _ORG_RE.match(url.strip())
    if not m:
        return None
    slug = m.group(1)
    # Avoid catching reserved paths like /search, /settings, /marketplace
    if slug.lower() in {"search", "settings", "marketplace", "topics", "trending", "explore"}:
        return None
    return slug


def _list_org_repos(org: str, *, token: str = "", timeout: float = 4.0, top_n: int = 5) -> list[tuple[str, str]]:
    """For an org URL, list the top-N most recently pushed repos.

    Returns a list of (owner, repo) tuples. The org could actually be a user
    account; we try /orgs/<x>/repos first, then fall back to /users/<x>/repos.
    """
    extra = {"Accept": "application/vnd.github+json"}
    if token:
        extra["Authorization"] = f"Bearer {token}"
    for kind in ("orgs", "users"):
        api = f"https://api.github.com/{kind}/{org}/repos?sort=pushed&per_page={top_n}"
        try:
            body, _ = http_get(api, timeout=timeout, extra_headers=extra)
        except HttpError:
            continue
        except Exception:
            continue
        if not body:
            continue
        try:
            data = json.loads(body)
        except Exception:
            continue
        if isinstance(data, list) and data:
            out: list[tuple[str, str]] = []
            for r in data:
                fn = r.get("full_name", "")
                if "/" in fn:
                    o, n = fn.split("/", 1)
                    out.append((o, n))
            return out
    return []


class GitHubReleasesFetcher(Fetcher):
    """GitHub Releases fetcher. Reason codes:

      github:ok                     — releases returned
      github:not_a_repo_url         — URL doesn't match owner/repo pattern AND
                                      org-fallback also returned nothing
      github:org_no_releases        — URL was an org/user; we listed top repos
                                      but none had releases in window
      github:api_error_<status>     — HTTP error fetching API (status appended)
      github:not_modified           — 304 from ETag match
      github:invalid_response       — non-JSON or non-list body
      github:no_releases            — repo exists but has 0 published releases
      github:no_items_in_window     — releases exist but none in window
      github:all_already_seen       — in-window releases all in cache
    """
    name = "github_releases"

    def fetch(
        self,
        url: str,
        window_start: str,
        window_end: str,
        cache_for_url: Optional[dict] = None,
        timeout: float = 4.0,
    ) -> tuple[list[FetchResult], dict, str]:
        cache = dict(cache_for_url or {})
        token = os.environ.get("GITHUB_TOKEN", "")
        repo = _parse_repo(url)
        if not repo:
            # Maybe an org URL — try listing top repos and walking each.
            org = _parse_org(url)
            if not org:
                return ([], cache, "github:not_a_repo_url")
            top_repos = _list_org_repos(org, token=token, timeout=timeout, top_n=5)
            if not top_repos:
                return ([], cache, "github:not_a_repo_url")
            # Walk each top repo; merge results
            all_kept: list[FetchResult] = []
            new_guids: list[str] = []
            last_seen = set(cache.get("last_seen_guids", []))
            for o, r in top_repos:
                items, _, _ = self._fetch_one_repo(
                    o, r, window_start, window_end, last_seen, token, timeout,
                )
                for it in items:
                    all_kept.append(it)
                    if it.item_guid:
                        new_guids.append(it.item_guid)
            cache["last_seen_guids"] = (new_guids + list(last_seen))[:200]
            cache["last_publisher"] = f"GitHub org: {org}"
            if all_kept:
                return (all_kept, cache, "github:ok")
            return ([], cache, "github:org_no_releases")

        owner, name = repo
        items, new_state, reason = self._fetch_one_repo(
            owner, name, window_start, window_end,
            set(cache.get("last_seen_guids", [])), token, timeout, cache.get("etag"),
        )
        if new_state:
            cache.update(new_state)
        return (items, cache, reason)

    def _fetch_one_repo(
        self, owner: str, name: str,
        window_start: str, window_end: str,
        last_seen: set, token: str, timeout: float, etag: str = "",
    ) -> tuple[list[FetchResult], dict, str]:
        api_url = f"https://api.github.com/repos/{owner}/{name}/releases?per_page=20"
        extra: dict = {"Accept": "application/vnd.github+json"}
        if token:
            extra["Authorization"] = f"Bearer {token}"
        if etag:
            extra["If-None-Match"] = etag

        try:
            body, headers = http_get(api_url, timeout=timeout, extra_headers=extra)
        except HttpError as e:
            label = str(e.status) if e.status > 0 else ("timeout" if e.status == -1 else "dns")
            return ([], {}, f"github:api_error_{label}")
        except Exception:
            return ([], {}, "github:api_error_unknown")

        if not body:
            return ([], {}, "github:not_modified")

        try:
            data = json.loads(body)
        except Exception:
            return ([], {}, "github:invalid_response")

        if not isinstance(data, list):
            return ([], {}, "github:invalid_response")
        if not data:
            return ([], {}, "github:no_releases")

        kept: list[FetchResult] = []
        new_guids: list[str] = []
        any_in_window = False
        for rel in data:
            published_at = (rel.get("published_at") or rel.get("created_at") or "").strip()
            if not in_window(published_at, window_start, window_end):
                continue
            any_in_window = True
            guid = str(rel.get("id", "")) or rel.get("html_url", "")
            if guid and guid in last_seen:
                continue
            html_url = rel.get("html_url", "")
            tag_name = rel.get("tag_name", "")
            title = rel.get("name") or tag_name or "release"
            body_md = (rel.get("body") or "").strip()
            kept.append(FetchResult(
                source_url=html_url,
                title=f"{owner}/{name} {tag_name}: {title}".strip(),
                summary=_first_n_chars(body_md, 280),
                published_at=published_at,
                content_type="release-notes",
                publisher=f"GitHub: {owner}/{name}",
                raw_label=published_at,
                item_guid=guid,
            ))
            if guid:
                new_guids.append(guid)

        new_state = {
            "last_seen_guids": (new_guids + list(last_seen))[:200],
            "etag": headers.get("etag", ""),
            "last_publisher": f"GitHub: {owner}/{name}",
        }

        if kept:
            return (kept, new_state, "github:ok")
        if not any_in_window:
            return ([], new_state, "github:no_items_in_window")
        return ([], new_state, "github:all_already_seen")


def _first_n_chars(s: str, n: int) -> str:
    s = s.replace("\r\n", "\n").strip()
    # Strip markdown headings + horizontal rules; collapse whitespace
    s = re.sub(r"^[#>*-]+\s*", "", s, flags=re.MULTILINE)
    s = re.sub(r"\s+", " ", s).strip()
    return (s[: n - 1] + "…") if len(s) > n else s
