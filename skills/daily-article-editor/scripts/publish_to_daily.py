#!/usr/bin/env python3
"""Publish a Q-daily article to the `daily` Supabase project.

Pipeline:
    1. Parse frontmatter + body from a markdown file.
    2. For every external image URL (heroImage + inline `![](url)`):
          download → SHA256 → upload to Storage bucket `article-media`
          at `articles/<slug>/<hero|inline>/<digest>-<filename>`.
       Already-existing objects are reused (idempotent).
    3. Rewrite source_markdown, heroImage, and image-block `src` fields to
       the resulting Storage public URLs.
    4. Upsert into `articles`; delete+re-insert `article_blocks`.

Expected environment:
    DAILY_DATABASE_URL         direct Postgres URL for the daily project
    DAILY_SERVICE_ROLE_KEY     (preferred) Supabase service_role JWT — grants
                               access to the permanent RLS policies named
                               "Service role uploads/updates/deletes article media"
                               so uploads work without opening any temporary policy
    Q-daily .env.local         (path configurable via --env-file) provides
                               NEXT_PUBLIC_SUPABASE_URL (always) +
                               NEXT_PUBLIC_SUPABASE_ANON_KEY (fallback when
                               DAILY_SERVICE_ROLE_KEY is not set)

Usage:
    python3 publish_to_daily.py <markdown>
        [--execute]              # actually write; otherwise dry-run
        [--status draft|published]
        [--open-policy]          # DEPRECATED. Use DAILY_SERVICE_ROLE_KEY instead.
                                 # If you still pass it, the script adds and
                                 # drops a temporary RLS policy as a fallback.
        [--env-file PATH]

The script matches the schema observed on the live `daily` project:
    articles.(slug, title, excerpt, published_at, author_slug,
              reading_time, category_slug, column_slug, palette, cover_alt,
              hero_image_url, hero_image_caption, status, source_markdown,
              comments_count, likes_count)
    article_blocks.(article_slug, position, kind, content)

Two-axis editorial model (see `references/topic-selection-and-routing.md`):
    - frontmatter `category` -> articles.category_slug   (领域 / topic domain)
    - frontmatter `column`   -> articles.column_slug     (栏目 / editorial column)

`column` is optional in the frontmatter for backward compatibility with
articles written before the axis existed; when missing, column_slug is left
NULL (and the row should be filled in via a backfill pass later).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import sys
import urllib.parse
from pathlib import Path

import psycopg2
import requests


DEFAULT_ENV_FILE = "/Users/shujudagongren/Documents/learnspace/Q-daily/.env.local"
DEFAULT_BUCKET = "article-media"
TEMP_POLICY_NAME = "Temporary publish_to_daily upload policy"


# ---------------------------------------------------------------------------
# frontmatter + body parsing
# ---------------------------------------------------------------------------

def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not m:
        raise ValueError("no frontmatter found")
    head, body = m.group(1), m.group(2).lstrip("\n")
    fm: dict[str, str] = {}
    for line in head.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm, body


def load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def content_type_for(name: str) -> str:
    lower = name.lower()
    if lower.endswith(".webp"):
        return "image/webp"
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if lower.endswith(".gif"):
        return "image/gif"
    guess = mimetypes.guess_type(name)[0]
    return guess or "application/octet-stream"


def safe_basename(url: str) -> str:
    path = urllib.parse.urlparse(url).path
    name = Path(path).name or "image"
    name = re.sub(r"[^a-zA-Z0-9._-]+", "-", name).strip("-")
    if not name or name.startswith("."):
        name = f"image{name}"
    return name[:80]


# ---------------------------------------------------------------------------
# storage helpers
# ---------------------------------------------------------------------------

def open_upload_policy(db_url: str, bucket: str) -> None:
    sql = (
        f'drop policy if exists "{TEMP_POLICY_NAME}" on storage.objects; '
        f'create policy "{TEMP_POLICY_NAME}" on storage.objects '
        f"for insert with check (bucket_id = '{bucket}');"
    )
    with psycopg2.connect(db_url) as c:
        with c.cursor() as cur:
            cur.execute(sql)
        c.commit()


def close_upload_policy(db_url: str) -> None:
    sql = f'drop policy if exists "{TEMP_POLICY_NAME}" on storage.objects;'
    with psycopg2.connect(db_url) as c:
        with c.cursor() as cur:
            cur.execute(sql)
        c.commit()


def public_url_exists(url: str) -> bool:
    try:
        r = requests.head(url, timeout=10)
        return r.status_code == 200
    except Exception:
        return False


def download(url: str) -> tuple[bytes, str]:
    # Use a descriptive UA that complies with Wikimedia's User-Agent policy
    # (https://meta.wikimedia.org/wiki/User-Agent_policy) — anonymous Mozilla
    # strings get rate-limited or 400'd at upload.wikimedia.org.
    r = requests.get(
        url,
        timeout=30,
        headers={
            "User-Agent": "QDailyPublisher/1.0 (https://qdaily.com; +editorial@qdaily.com) python-requests"
        },
    )
    r.raise_for_status()
    ct = r.headers.get("Content-Type", "application/octet-stream").split(";")[0].strip()
    if ct in ("application/octet-stream", "binary/octet-stream", ""):
        ct_by_ext = content_type_for(url)
        if ct_by_ext != "application/octet-stream":
            ct = ct_by_ext
    return r.content, ct


def build_object_path(slug: str, kind: str, url: str, content: bytes, content_type: str) -> str:
    digest = hashlib.sha256(content).hexdigest()[:12]
    base = safe_basename(url)
    if not Path(base).suffix:
        ext_map = {"image/webp": ".webp", "image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif"}
        base = base + ext_map.get(content_type, ".bin")
    return f"articles/{slug}/{kind}/{digest}-{base}"


def upload(project_url: str, anon_key: str, bucket: str, object_path: str, content: bytes, content_type: str) -> str:
    public_url = f"{project_url}/storage/v1/object/public/{bucket}/{object_path}"
    if public_url_exists(public_url):
        return public_url
    r = requests.post(
        f"{project_url}/storage/v1/object/{bucket}/{object_path}",
        headers={
            "Authorization": f"Bearer {anon_key}",
            "apikey": anon_key,
            "Content-Type": content_type,
            "x-upsert": "false",
        },
        data=content,
        timeout=60,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Storage upload failed: {r.status_code} {r.text}")
    return public_url


# ---------------------------------------------------------------------------
# markdown block parser
# ---------------------------------------------------------------------------

_IMAGE_IN_PARA_RE = re.compile(r"^\s*!\[([^\]]*)\]\(([^)]+)\)\s*(?:\*(.+?)\*)?\s*$", re.DOTALL)
_HEADING_RE = re.compile(r"^(#{2,4})\s+(.+)$")
_CAPTION_ONLY_RE = re.compile(r"^\*([^*].*[^*])\*$", re.DOTALL)
_BULLET_LINE_RE = re.compile(r"^\s*[-*+]\s+(.+)$")
_ORDERED_LINE_RE = re.compile(r"^\s*\d+\.\s+(.+)$")


def _try_parse_list(p: str) -> tuple[bool, str] | None:
    """If the paragraph chunk is entirely list lines, return (ordered, json).

    Treats a chunk where EVERY non-empty line matches `- item` / `* item` /
    `+ item` (unordered) or `1. item` / `2. item` (ordered) as a list block.
    Mixed bullet+ordered lines fall back to paragraph.
    """
    lines = [ln for ln in p.splitlines() if ln.strip()]
    if len(lines) < 2:
        # A single list line is allowed but should still split — `- foo` on
        # its own is a one-item list, useful for callouts.
        if len(lines) == 1:
            single = lines[0]
            if _BULLET_LINE_RE.match(single):
                item = _BULLET_LINE_RE.match(single).group(1).strip()
                return False, json.dumps({"ordered": False, "items": [item]}, ensure_ascii=False)
            if _ORDERED_LINE_RE.match(single):
                item = _ORDERED_LINE_RE.match(single).group(1).strip()
                return True, json.dumps({"ordered": True, "items": [item]}, ensure_ascii=False)
        return None

    bullet_items: list[str] = []
    ordered_items: list[str] = []
    for ln in lines:
        m = _BULLET_LINE_RE.match(ln)
        if m:
            bullet_items.append(m.group(1).strip())
            continue
        m = _ORDERED_LINE_RE.match(ln)
        if m:
            ordered_items.append(m.group(1).strip())
            continue
        # Line is not a list item — bail out, this paragraph is mixed prose.
        return None

    if bullet_items and not ordered_items:
        return False, json.dumps({"ordered": False, "items": bullet_items}, ensure_ascii=False)
    if ordered_items and not bullet_items:
        return True, json.dumps({"ordered": True, "items": ordered_items}, ensure_ascii=False)
    # Mixed bullet+ordered: ambiguous, keep as paragraph.
    return None


def split_blocks(body: str) -> list[tuple[str, str]]:
    """Turn the markdown body into a flat list of (kind, content) blocks.

    Recognized block kinds:
      - `heading`   for `## H2`, `### H3`, or `#### H4`
      - `image`     for `![alt](url)` optionally with a `*caption*` line
      - `list`      for consecutive lines all starting with `- ` / `* ` / `+ `
                    (unordered) or `1. ` / `2. ` etc. (ordered). Stored as
                    JSON `{"ordered": bool, "items": [str, ...]}`.
      - `paragraph` for everything else

    Edge cases handled:
      - Image + caption split across two paragraph blocks (blank line between
        them). The standalone `*caption*` block is merged into the preceding
        image block IF the image has no caption yet.
      - `####` H4 produces a level=4 heading.
      - A list is detected ONLY when every non-empty line in the chunk is a
        list item; mixed prose+bullet falls back to paragraph.
    """
    blocks: list[tuple[str, str]] = []
    paras = re.split(r"\n\s*\n", body.strip())
    for p in paras:
        p = p.strip()
        if not p:
            continue
        m = _HEADING_RE.match(p)
        if m:
            level = len(m.group(1))
            blocks.append(("heading", json.dumps({"level": level, "content": m.group(2).strip()}, ensure_ascii=False)))
            continue
        m = _IMAGE_IN_PARA_RE.match(p)
        if m:
            alt = (m.group(1) or "").strip()
            src = m.group(2).strip()
            caption = (m.group(3) or "").strip()
            blocks.append(("image", json.dumps({"src": src, "alt": alt, "caption": caption}, ensure_ascii=False)))
            continue
        list_payload = _try_parse_list(p)
        if list_payload is not None:
            _, content = list_payload
            blocks.append(("list", content))
            continue
        blocks.append(("paragraph", p))

    # Post-pass: merge a standalone `*caption*` block into the preceding image
    # block when the image has no caption yet.
    merged: list[tuple[str, str]] = []
    for kind, content in blocks:
        if kind == "paragraph" and merged and merged[-1][0] == "image":
            cap_match = _CAPTION_ONLY_RE.match(content)
            if cap_match:
                prev_block = json.loads(merged[-1][1])
                if not prev_block.get("caption"):
                    prev_block["caption"] = cap_match.group(1).strip()
                    merged[-1] = ("image", json.dumps(prev_block, ensure_ascii=False))
                    continue
        merged.append((kind, content))
    return merged


def rewrite_markdown(source: str, url_map: dict[str, str]) -> str:
    out_lines = []
    for line in source.splitlines():
        new_line = line
        if line.startswith("heroImage:"):
            _, v = line.split(":", 1)
            src = v.strip()
            if src in url_map:
                new_line = f"heroImage: {url_map[src]}"
        else:
            m = re.match(r"^(!\[.*\]\()([^)]+)(\))$", line)
            if m:
                prefix, src, suffix = m.groups()
                if src in url_map:
                    new_line = f"{prefix}{url_map[src]}{suffix}"
        out_lines.append(new_line)
    return "\n".join(out_lines) + ("\n" if source.endswith("\n") else "")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("markdown")
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--status", default="published", choices=["draft", "published"])
    ap.add_argument("--open-policy", action="store_true")
    ap.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    ap.add_argument("--bucket", default=DEFAULT_BUCKET)
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    md_path = Path(args.markdown)
    source_markdown = md_path.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(source_markdown)
    fm["status"] = args.status

    required = ["title", "slug", "excerpt", "author", "readingTime", "category", "palette", "coverAlt", "heroImage", "heroCaption"]
    missing = [k for k in required if not fm.get(k)]
    if missing:
        print(f"frontmatter missing: {missing}", file=sys.stderr)
        return 2

    slug = fm["slug"]
    blocks = split_blocks(body)

    # Collect external URLs that need to be migrated to Storage
    db_url = os.environ["DAILY_DATABASE_URL"]
    env = load_env_file(Path(args.env_file))
    project_url = env["NEXT_PUBLIC_SUPABASE_URL"]

    # Prefer service_role key (permanent policies grant it full access to
    # article-media). Fall back to anon only when DAILY_SERVICE_ROLE_KEY is not
    # set; that path also requires --open-policy.
    service_role_key = os.environ.get("DAILY_SERVICE_ROLE_KEY")
    anon_key = env.get("NEXT_PUBLIC_SUPABASE_ANON_KEY", "")
    if service_role_key:
        upload_key = service_role_key
        key_source = "service_role"
    else:
        upload_key = anon_key
        key_source = "anon"

    storage_prefix = f"{project_url}/storage/"

    targets: list[tuple[str, str]] = []  # (kind, url)
    hero_url = fm["heroImage"]
    if hero_url.startswith(("http://", "https://")) and not hero_url.startswith(storage_prefix):
        targets.append(("hero", hero_url))
    for kind, content in blocks:
        if kind != "image":
            continue
        block = json.loads(content)
        src = block.get("src", "")
        if src.startswith(("http://", "https://")) and not src.startswith(storage_prefix):
            targets.append(("inline", src))

    # Print plan
    print(f"slug:             {slug}")
    print(f"title:            {fm['title']}")
    print(f"status:           {fm['status']}")
    print(f"blocks:           {len(blocks)} total")
    print(f"external images:  {len(targets)} (will upload to Storage)")
    print(f"upload auth:      {key_source}"
          f"{'  (needs --open-policy)' if key_source == 'anon' and targets else ''}")
    for kind, url in targets:
        print(f"  {kind:<8} {url[:110]}")

    if not args.execute:
        print("\n[dry-run] pass --execute to upload images + write to DAILY")
        return 0

    # 0. Pre-flight DB checks. Resolve every FK we'll need later, BEFORE any
    #    Storage upload happens — otherwise a failing FK leaves orphan files
    #    in the bucket that nobody knows to clean up.
    pre_conn = psycopg2.connect(db_url, connect_timeout=8)
    pre_conn.autocommit = True
    try:
        pcur = pre_conn.cursor()
        pcur.execute("select slug from public.authors where name=%s", (fm["author"],))
        author_row = pcur.fetchone()
        if not author_row:
            print(f"[pre-flight] FAIL: author '{fm['author']}' not in public.authors", file=sys.stderr)
            return 4
        author_slug = author_row[0]

        pcur.execute("select slug from public.categories where slug=%s", (fm["category"],))
        if not pcur.fetchone():
            print(f"[pre-flight] FAIL: category_slug '{fm['category']}' not in public.categories", file=sys.stderr)
            return 4

        column_slug = fm.get("column") or None
        if column_slug:
            pcur.execute("select slug from public.columns where slug=%s", (column_slug,))
            if not pcur.fetchone():
                print(f"[pre-flight] FAIL: column_slug '{column_slug}' not in public.columns "
                      f"(allowed: good-article / good-take / good-grief / good-paper)",
                      file=sys.stderr)
                return 4
        print(f"[pre-flight] author_slug={author_slug}  category_slug={fm['category']}  "
              f"column_slug={column_slug or '∅'}  OK")
    finally:
        pre_conn.close()

    # When using service_role we do NOT need the temporary open-policy trick;
    # the permanent "Service role uploads article media" policy covers it.
    # --open-policy remains supported only for legacy anon-only setups.
    policy_opened = False
    need_temp_policy = args.open_policy and key_source == "anon" and bool(targets)
    try:
        if need_temp_policy:
            open_upload_policy(db_url, args.bucket)
            policy_opened = True
            print(f"[policy] opened temporary insert policy on {args.bucket}")
        elif args.open_policy and key_source == "service_role":
            print("[policy] --open-policy ignored; service_role already has "
                  "permanent write access via RLS policy")

        # 1. Upload all external images to Storage (after pre-flight passed)
        url_map: dict[str, str] = {}
        for kind, url in targets:
            data, ct = download(url)
            obj_path = build_object_path(slug, kind, url, data, ct)
            public = upload(project_url, upload_key, args.bucket, obj_path, data, ct)
            url_map[url] = public
            print(f"[upload] {kind:<8} {len(data):>7}B {ct:<12} -> {obj_path}")

        # 2. Rewrite frontmatter + body + source_markdown with Storage URLs
        if url_map:
            new_source = rewrite_markdown(source_markdown, url_map)
            fm["heroImage"] = url_map.get(hero_url, hero_url)
            rebuilt_blocks: list[tuple[str, str]] = []
            for kind, content in blocks:
                if kind == "image":
                    block = json.loads(content)
                    src = block.get("src", "")
                    if src in url_map:
                        block["src"] = url_map[src]
                    content = json.dumps(block, ensure_ascii=False)
                rebuilt_blocks.append((kind, content))
            blocks = rebuilt_blocks
            md_path.write_text(new_source, encoding="utf-8")
            print(f"[local] rewrote {md_path}")
            source_markdown = new_source

        # 3. Upsert into articles + replace article_blocks atomically
        conn = psycopg2.connect(db_url, connect_timeout=8)
        conn.autocommit = False
        try:
            cur = conn.cursor()
            # FK lookups already verified in pre-flight; reuse the resolved
            # author_slug. We re-check inside the transaction in case the
            # author row was deleted between pre-flight and commit.
            cur.execute("select slug from public.authors where name=%s", (fm["author"],))
            row = cur.fetchone()
            if not row:
                raise RuntimeError(f"author '{fm['author']}' disappeared between pre-flight and commit")
            author_slug = row[0]

            cur.execute(
                """
                insert into public.articles (
                    slug, title, excerpt, published_at, author_slug,
                    reading_time, category_slug, column_slug, palette, cover_alt,
                    hero_image_url, hero_image_caption, status, source_markdown,
                    comments_count, likes_count
                ) values (
                    %(slug)s, %(title)s, %(excerpt)s, %(published_at)s, %(author_slug)s,
                    %(reading_time)s, %(category_slug)s, %(column_slug)s, %(palette)s, %(cover_alt)s,
                    %(hero_image_url)s, %(hero_image_caption)s, %(status)s, %(source_markdown)s,
                    0, 0
                )
                on conflict (slug) do update set
                    title = excluded.title,
                    excerpt = excluded.excerpt,
                    published_at = excluded.published_at,
                    author_slug = excluded.author_slug,
                    reading_time = excluded.reading_time,
                    category_slug = excluded.category_slug,
                    column_slug = excluded.column_slug,
                    palette = excluded.palette,
                    cover_alt = excluded.cover_alt,
                    hero_image_url = excluded.hero_image_url,
                    hero_image_caption = excluded.hero_image_caption,
                    status = excluded.status,
                    source_markdown = excluded.source_markdown,
                    updated_at = now()
                """,
                {
                    "slug": slug,
                    "title": fm["title"],
                    "excerpt": fm["excerpt"],
                    "published_at": fm.get("publishedAt"),
                    "author_slug": author_slug,
                    "reading_time": fm["readingTime"],
                    "category_slug": fm["category"],
                    "column_slug": column_slug,
                    "palette": fm["palette"],
                    "cover_alt": fm["coverAlt"],
                    "hero_image_url": fm["heroImage"],
                    "hero_image_caption": fm["heroCaption"],
                    "status": fm["status"],
                    "source_markdown": source_markdown,
                },
            )

            cur.execute("delete from public.article_blocks where article_slug=%s", (slug,))
            for pos, (kind, content) in enumerate(blocks, start=1):
                cur.execute(
                    "insert into public.article_blocks (article_slug, position, kind, content) "
                    "values (%s,%s,%s,%s)",
                    (slug, pos, kind, content),
                )

            conn.commit()
            print(f"[db] committed: 1 article + {len(blocks)} blocks")
        except Exception as e:
            conn.rollback()
            print(f"[rollback] {type(e).__name__}: {e}", file=sys.stderr)
            return 3
        finally:
            conn.close()

        return 0
    finally:
        if policy_opened:
            close_upload_policy(db_url)
            print("[policy] dropped temporary insert policy")


if __name__ == "__main__":
    raise SystemExit(main())
