#!/usr/bin/env python3
"""Deduplicate an update snapshot by `source_url`.

Research-rules.md #6 ("preserve attribution") and data-model.md recommend
`source_url` as the uniqueness handle for entity_updates. This script enforces
that rule: if the same URL appears more than once in `updates[]`, keep the
earliest `collected_at` (or, when `collected_at` is missing, the earliest
`published_at`; or, when both are missing, the first-seen entry).

Usage:
    python3 dedupe_updates.py <input.json> [--output OUT.json] [--in-place]

If neither --output nor --in-place is given, the deduped document is printed
to stdout.

Also prints a human-readable summary to stderr:

    input count: 12
    duplicate groups: 2
    removed: 3
    output count: 9
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any


# Path segments that indicate a localized variant of a page. The English
# version at /about and the French version at /fr/about should collapse.
# We strip these segments from the path during URL normalization for the
# purpose of detecting duplicates ONLY — the original `source_url` on the
# canonical record is preserved.
#
# Common 2-letter ISO 639-1 codes (lowercased), plus the few hyphenated
# regional codes that appear in real publisher URLs.
_LOCALE_SEGMENTS = frozenset({
    # 2-letter language codes — the most common case
    "en", "zh", "ja", "ko", "fr", "de", "es", "it", "pt", "ru", "nl",
    "ar", "hi", "tr", "pl", "sv", "no", "da", "fi", "cs", "el", "he",
    "th", "vi", "id", "uk", "ro", "hu", "bg",
    # Hyphenated regional codes seen in CMSes
    "en-us", "en-gb", "en-ca", "en-au",
    "zh-cn", "zh-tw", "zh-hk",
    "fr-ca", "fr-fr",
    "es-es", "es-mx", "es-ar",
    "pt-br", "pt-pt",
    "de-de", "de-at",
    "ja-jp", "ko-kr",
})


def normalize_url_for_dedup(url: str) -> str:
    """Strip i18n path segments + query/fragment to build a dedup key.

    Examples:
        cohere.com/about               -> cohere.com/about
        cohere.com/fr/about            -> cohere.com/about
        cohere.com/fr-CA/about         -> cohere.com/about
        cohere.com/blog/post           -> cohere.com/blog/post
        anthropic.com/news/foo?utm=... -> anthropic.com/news/foo
        anthropic.com/news/foo/        -> anthropic.com/news/foo

    Only strips the FIRST path segment if it looks like a locale code.
    Doesn't touch later segments — `cohere.com/blog/fr/post` would NOT
    have its `/fr/` removed (we'd risk merging two unrelated articles).
    """
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return url

    netloc = parsed.netloc.lower()
    # Strip a leading `www.`
    if netloc.startswith("www."):
        netloc = netloc[4:]

    # Split path into non-empty segments
    segments = [s for s in parsed.path.split("/") if s]
    if segments and segments[0].lower() in _LOCALE_SEGMENTS:
        segments = segments[1:]

    # Reassemble path; ignore query/fragment for dedup purposes
    path = "/" + "/".join(segments)
    if path != "/" and parsed.path.endswith("/"):
        path += "/"
    # Strip a trailing slash for stable comparison
    path = path.rstrip("/") if path != "/" else path

    return f"{parsed.scheme.lower() or 'https'}://{netloc}{path}"


def _sort_key(upd: dict) -> tuple[int, str]:
    """Priority ordering used to pick the 'canonical' record in a dup group."""
    collected = upd.get("collected_at")
    if isinstance(collected, str) and collected:
        return (0, collected)
    published = upd.get("published_at")
    if isinstance(published, str) and published:
        return (1, published)
    return (2, "")


def dedupe(doc: dict, *, normalize_locale: bool = True) -> tuple[dict, dict]:
    """Return (deduped_doc, summary).

    By default, URLs are bucketed by `normalize_url_for_dedup(source_url)`
    so that localized variants of the same page (`/about`, `/fr/about`,
    `/zh-CN/about`) collapse into one record. Pass
    `normalize_locale=False` to fall back to literal source_url
    bucketing — useful when a publisher's locale paths host genuinely
    different content rather than translations.
    """
    updates = doc.get("updates")
    if not isinstance(updates, list):
        return doc, {
            "input_count": 0,
            "duplicate_groups": 0,
            "removed": 0,
            "output_count": 0,
            "note": "no updates[] array; nothing to do",
        }

    # Preserve first-seen order while bucketing by normalized URL.
    # The canonical record keeps its original `source_url`; only the
    # bucket key is normalized for the purpose of finding duplicates.
    groups: dict[str, list[dict]] = {}
    null_url_bucket: list[dict] = []
    order: list[str] = []
    locale_collapsed_groups = 0
    for upd in updates:
        url = upd.get("source_url")
        if not isinstance(url, str) or not url:
            null_url_bucket.append(upd)
            continue
        key = normalize_url_for_dedup(url) if normalize_locale else url
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(upd)

    deduped: list[dict] = []
    duplicate_groups = 0
    removed = 0
    for key in order:
        bucket = groups[key]
        if len(bucket) > 1:
            duplicate_groups += 1
            removed += len(bucket) - 1
            # If the duplicates have DIFFERENT raw source_urls, this group
            # was collapsed by locale normalization (not by exact match).
            raw_urls = {u.get("source_url", "") for u in bucket}
            if len(raw_urls) > 1:
                locale_collapsed_groups += 1
            # pick earliest by the sort key
            bucket.sort(key=_sort_key)
        deduped.append(bucket[0])

    # Entries without a source_url are preserved untouched and at the end;
    # we cannot dedupe them without the uniqueness handle.
    deduped.extend(null_url_bucket)

    new_doc = dict(doc)
    new_doc["updates"] = deduped

    summary = {
        "input_count": len(updates),
        "duplicate_groups": duplicate_groups,
        "removed": removed,
        "output_count": len(deduped),
        "without_source_url": len(null_url_bucket),
        "locale_collapsed_groups": locale_collapsed_groups,
    }
    return new_doc, summary


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", help="Input update-snapshot JSON")
    parser.add_argument("--output", help="Write deduped JSON here")
    parser.add_argument(
        "--in-place", action="store_true", help="Overwrite the input file"
    )
    parser.add_argument(
        "--no-locale-collapse", action="store_true",
        help="Disable i18n URL normalization. By default, URLs that differ "
             "only in their locale prefix (`/fr/about` vs `/about`) are "
             "treated as the same record. Pass this flag to keep them "
             "separate (use when a publisher's locale paths host "
             "genuinely different content, not translations).",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"No such file: {args.input}", file=sys.stderr)
        return 2

    doc = json.loads(input_path.read_text(encoding="utf-8"))
    deduped, summary = dedupe(doc, normalize_locale=not args.no_locale_collapse)

    # Summary to stderr regardless of output mode
    print(
        f"input count: {summary['input_count']}\n"
        f"duplicate groups: {summary['duplicate_groups']}\n"
        f"  (of which locale-collapsed: {summary.get('locale_collapsed_groups', 0)})\n"
        f"removed: {summary['removed']}\n"
        f"output count: {summary['output_count']}",
        file=sys.stderr,
    )

    payload = json.dumps(deduped, ensure_ascii=False, indent=2)
    if args.in_place:
        input_path.write_text(payload + "\n", encoding="utf-8")
    elif args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
