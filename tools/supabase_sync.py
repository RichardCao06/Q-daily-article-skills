#!/usr/bin/env python3
"""Parse the AI tracking directory markdown and sync it into Supabase."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


SCHEMA_SQL = """
create extension if not exists pgcrypto;

create table if not exists public.ai_tracking_entities (
    id uuid primary key default gen_random_uuid(),
    entity_group text not null check (entity_group in ('person', 'company', 'product')),
    entity_rank integer not null,
    name text not null,
    official_url text,
    official_links_markdown text,
    blog_or_news_url text,
    blog_or_news_markdown text,
    x_url text,
    youtube_url text,
    reddit_url text,
    discord_url text,
    other_links jsonb not null default '[]'::jsonb,
    other_links_markdown text,
    notes text,
    source_date date not null,
    source_file text not null,
    raw_row jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (entity_group, name)
);
""".strip()

PERSON_UPDATES_SCHEMA_SQL = """
create extension if not exists pgcrypto;

create table if not exists public.ai_tracking_person_updates (
    id uuid primary key default gen_random_uuid(),
    entity_id uuid references public.ai_tracking_entities(id) on delete set null,
    person_name text not null,
    published_at timestamptz not null,
    source_platform text not null,
    source_url text not null unique,
    title text not null,
    summary text,
    content_type text not null,
    source_domain text not null,
    is_official boolean not null default true,
    raw_source jsonb not null default '{}'::jsonb,
    collected_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
""".strip()

GENERIC_SCHEMA_SQL = """
create extension if not exists pgcrypto;

create table if not exists public.tracked_entities (
    id uuid primary key default gen_random_uuid(),
    domain text not null,
    snapshot_date date,
    entity_group text not null,
    entity_rank integer,
    name text not null,
    description text,
    official_url text,
    status text,
    raw_entity jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (domain, entity_group, name)
);

create table if not exists public.entity_sources (
    id uuid primary key default gen_random_uuid(),
    entity_id uuid references public.tracked_entities(id) on delete cascade,
    domain text not null,
    entity_group text not null,
    entity_name text not null,
    source_type text not null,
    platform text not null,
    label text not null,
    url text not null,
    is_official boolean not null default true,
    is_primary boolean not null default false,
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (domain, entity_group, entity_name, url)
);

create table if not exists public.entity_updates (
    id uuid primary key default gen_random_uuid(),
    entity_id uuid references public.tracked_entities(id) on delete set null,
    domain text not null,
    entity_group text not null,
    entity_name text not null,
    published_at timestamptz not null,
    source_platform text not null,
    source_url text not null unique,
    title text not null,
    summary text,
    content_type text not null,
    source_domain text not null,
    is_official boolean not null default true,
    raw_source jsonb not null default '{}'::jsonb,
    collected_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.collection_runs (
    id uuid primary key default gen_random_uuid(),
    domain text not null,
    goal text not null,
    window_start date not null,
    window_end date not null,
    entity_scope jsonb not null default '[]'::jsonb,
    source_policy jsonb not null default '{}'::jsonb,
    output_targets jsonb not null default '[]'::jsonb,
    notes text,
    raw_run jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (domain, window_start, window_end, goal)
);
""".strip()


SECTION_MAP = {
    "## 一、人物追踪清单": "person",
    "## 二、公司追踪清单": "company",
    "## 三、产品追踪清单": "product",
}

LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")


def extract_markdown_links(text: str) -> list[dict[str, str]]:
    return [{"label": match.group(1), "url": match.group(2)} for match in LINK_RE.finditer(text)]


def first_link_url(text: str) -> str | None:
    links = extract_markdown_links(text)
    return links[0]["url"] if links else None


def strip_markdown(text: str) -> str:
    text = LINK_RE.sub(lambda match: match.group(1), text)
    text = text.replace("`", "")
    return text.strip()


def split_table_row(line: str) -> list[str]:
    line = line.strip()
    if not line.startswith("|") or not line.endswith("|"):
        raise ValueError(f"Not a markdown table row: {line!r}")
    return [cell.strip() for cell in line[1:-1].split("|")]


def is_separator_row(cells: list[str]) -> bool:
    return all(cell.replace("-", "").replace(":", "").strip() == "" for cell in cells)


def parse_tracking_directory(markdown_text: str, source_file: str, source_date: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    current_section: str | None = None
    pending_header: list[str] | None = None
    ranks = {"person": 0, "company": 0, "product": 0}

    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        if line in SECTION_MAP:
            current_section = SECTION_MAP[line]
            pending_header = None
            continue

        if current_section is None or not line.startswith("|"):
            continue

        cells = split_table_row(line)
        if is_separator_row(cells):
            continue

        if pending_header is None:
            pending_header = cells
            continue

        ranks[current_section] += 1
        rows.append(
            row_to_record(
                entity_group=current_section,
                rank=ranks[current_section],
                header=pending_header,
                cells=cells,
                source_file=source_file,
                source_date=source_date,
            )
        )

    return rows


def row_to_record(
    entity_group: str,
    rank: int,
    header: list[str],
    cells: list[str],
    source_file: str,
    source_date: str,
) -> dict[str, Any]:
    if entity_group == "person":
        name, official, x_cell, youtube, other_cell, notes = cells
        record = {
            "entity_group": entity_group,
            "rank": rank,
            "name": strip_markdown(name),
            "official_url": first_link_url(official),
            "official_links_markdown": official,
            "blog_or_news_url": None,
            "blog_or_news_markdown": None,
            "x_url": first_link_url(x_cell),
            "youtube_url": first_link_url(youtube),
            "reddit_url": None,
            "discord_url": None,
            "other_links": extract_markdown_links(other_cell),
            "other_links_markdown": other_cell,
            "notes": strip_markdown(notes),
            "source_date": source_date,
            "source_file": source_file,
            "raw_row": {
                "header": header,
                "cells": cells,
            },
        }
        return record

    name, official, blog_or_news, x_cell, youtube, reddit, discord, other = cells
    record = {
        "entity_group": entity_group,
        "rank": rank,
        "name": strip_markdown(name),
        "official_url": first_link_url(official),
        "official_links_markdown": official,
        "blog_or_news_url": first_link_url(blog_or_news),
        "blog_or_news_markdown": blog_or_news,
        "x_url": first_link_url(x_cell),
        "youtube_url": first_link_url(youtube),
        "reddit_url": first_link_url(reddit),
        "discord_url": first_link_url(discord),
        "other_links": extract_markdown_links(other),
        "other_links_markdown": other,
        "notes": None,
        "source_date": source_date,
        "source_file": source_file,
        "raw_row": {
            "header": header,
            "cells": cells,
        },
    }
    return record


def sql_literal_json(rows: list[dict[str, Any]]) -> str:
    payload = json.dumps(rows, ensure_ascii=False)
    return f"$rows${payload}$rows$"


def build_sync_sql(rows: list[dict[str, Any]]) -> str:
    payload = sql_literal_json(rows)
    return f"""
{SCHEMA_SQL}

with source_rows as (
    select *
    from jsonb_to_recordset({payload}::jsonb) as input_rows(
        entity_group text,
        rank integer,
        name text,
        official_url text,
        official_links_markdown text,
        blog_or_news_url text,
        blog_or_news_markdown text,
        x_url text,
        youtube_url text,
        reddit_url text,
        discord_url text,
        other_links jsonb,
        other_links_markdown text,
        notes text,
        source_date date,
        source_file text,
        raw_row jsonb
    )
)
insert into public.ai_tracking_entities (
    entity_group,
    entity_rank,
    name,
    official_url,
    official_links_markdown,
    blog_or_news_url,
    blog_or_news_markdown,
    x_url,
    youtube_url,
    reddit_url,
    discord_url,
    other_links,
    other_links_markdown,
    notes,
    source_date,
    source_file,
    raw_row,
    updated_at
)
select
    entity_group,
    rank,
    name,
    official_url,
    official_links_markdown,
    blog_or_news_url,
    blog_or_news_markdown,
    x_url,
    youtube_url,
    reddit_url,
    discord_url,
    coalesce(other_links, '[]'::jsonb),
    other_links_markdown,
    notes,
    source_date,
    source_file,
    raw_row,
    now()
from source_rows
on conflict (entity_group, name)
do update set
    entity_rank = excluded.entity_rank,
    official_url = excluded.official_url,
    official_links_markdown = excluded.official_links_markdown,
    blog_or_news_url = excluded.blog_or_news_url,
    blog_or_news_markdown = excluded.blog_or_news_markdown,
    x_url = excluded.x_url,
    youtube_url = excluded.youtube_url,
    reddit_url = excluded.reddit_url,
    discord_url = excluded.discord_url,
    other_links = excluded.other_links,
    other_links_markdown = excluded.other_links_markdown,
    notes = excluded.notes,
    source_date = excluded.source_date,
    source_file = excluded.source_file,
    raw_row = excluded.raw_row,
    updated_at = now();
""".strip()


def load_person_updates_snapshot(path: str | Path) -> list[dict[str, Any]]:
    snapshot_path = Path(path).expanduser().resolve()
    return json.loads(snapshot_path.read_text(encoding="utf-8"))


def load_json_document(path: str | Path) -> dict[str, Any]:
    document_path = Path(path).expanduser().resolve()
    return json.loads(document_path.read_text(encoding="utf-8"))


def infer_source_type_from_url(url: str) -> tuple[str, str]:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    if "x.com" in host or "twitter.com" in host:
        return "x", "x"
    if "youtube.com" in host or "youtu.be" in host:
        return "youtube", "youtube"
    if "reddit.com" in host:
        return "reddit", "reddit"
    if "discord.gg" in host or "discord.com" in host:
        return "discord", "discord"
    if "github.com" in host:
        return "github", "github"
    if any(part in parsed.path.lower() for part in ["/blog", "/news", "/hub/blog", "/newsroom"]):
        return "blog", "blog"
    return "website", "website"


def build_domain_entity_snapshot_from_tracking_rows(
    domain: str,
    rows: list[dict[str, Any]],
    snapshot_date: str,
) -> dict[str, Any]:
    entities: list[dict[str, Any]] = []
    for row in rows:
        sources: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        def append_source(source: dict[str, Any]) -> None:
            url = source["url"]
            if url in seen_urls:
                return
            seen_urls.add(url)
            sources.append(source)

        if row.get("official_url"):
            source_type, platform = infer_source_type_from_url(row["official_url"])
            append_source(
                {
                    "source_type": source_type,
                    "platform": platform,
                    "label": "Official source",
                    "url": row["official_url"],
                    "is_official": True,
                    "is_primary": True,
                    "notes": None,
                }
            )

        for field, label in [
            ("blog_or_news_url", "Blog or news"),
            ("x_url", "X"),
            ("youtube_url", "YouTube"),
            ("reddit_url", "Reddit"),
            ("discord_url", "Discord"),
        ]:
            if row.get(field):
                source_type, platform = infer_source_type_from_url(row[field])
                append_source(
                    {
                        "source_type": source_type,
                        "platform": platform,
                        "label": label,
                        "url": row[field],
                        "is_official": field not in {"reddit_url", "discord_url"},
                        "is_primary": False,
                        "notes": None,
                    }
                )

        for link in row.get("other_links", []):
            source_type, platform = infer_source_type_from_url(link["url"])
            append_source(
                {
                    "source_type": source_type,
                    "platform": platform,
                    "label": link["label"],
                    "url": link["url"],
                    "is_official": True,
                    "is_primary": False,
                    "notes": None,
                }
            )

        entities.append(
            {
                "entity_group": row["entity_group"],
                "rank": row["rank"],
                "name": row["name"],
                "description": row.get("notes"),
                "official_url": row.get("official_url"),
                "status": "active",
                "sources": sources,
                "raw_entity": row,
            }
        )

    return {
        "domain": domain,
        "snapshot_date": snapshot_date,
        "entities": entities,
    }


def build_person_updates_sync_sql(rows: list[dict[str, Any]]) -> str:
    payload = sql_literal_json(rows)
    return f"""
{PERSON_UPDATES_SCHEMA_SQL}

with source_rows as (
    select *
    from jsonb_to_recordset({payload}::jsonb) as input_rows(
        person_name text,
        published_at timestamptz,
        source_platform text,
        source_url text,
        title text,
        summary text,
        content_type text,
        source_domain text,
        is_official boolean,
        raw_source jsonb
    )
),
matched_rows as (
    select
        entities.id as entity_id,
        source_rows.person_name,
        source_rows.published_at,
        source_rows.source_platform,
        source_rows.source_url,
        source_rows.title,
        source_rows.summary,
        source_rows.content_type,
        source_rows.source_domain,
        coalesce(source_rows.is_official, true) as is_official,
        coalesce(source_rows.raw_source, '{{}}'::jsonb) as raw_source
    from source_rows
    left join public.ai_tracking_entities as entities
        on entities.entity_group = 'person'
       and entities.name = source_rows.person_name
)
insert into public.ai_tracking_person_updates (
    entity_id,
    person_name,
    published_at,
    source_platform,
    source_url,
    title,
    summary,
    content_type,
    source_domain,
    is_official,
    raw_source,
    updated_at
)
select
    entity_id,
    person_name,
    published_at,
    source_platform,
    source_url,
    title,
    summary,
    content_type,
    source_domain,
    is_official,
    raw_source,
    now()
from matched_rows
on conflict (source_url)
do update set
    entity_id = excluded.entity_id,
    person_name = excluded.person_name,
    published_at = excluded.published_at,
    source_platform = excluded.source_platform,
    title = excluded.title,
    summary = excluded.summary,
    content_type = excluded.content_type,
    source_domain = excluded.source_domain,
    is_official = excluded.is_official,
    raw_source = excluded.raw_source,
    updated_at = now();
""".strip()


def normalize_update_rows(update_snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    domain = update_snapshot["domain"]
    normalized: list[dict[str, Any]] = []
    for row in update_snapshot.get("updates", []):
        normalized.append(
            {
                "domain": domain,
                "entity_group": row.get("entity_group", "person"),
                "entity_name": row.get("entity_name") or row.get("person_name"),
                "published_at": row["published_at"],
                "source_platform": row["source_platform"],
                "source_url": row["source_url"],
                "title": row["title"],
                "summary": row.get("summary"),
                "content_type": row["content_type"],
                "source_domain": row["source_domain"],
                "is_official": row.get("is_official", True),
                "raw_source": row.get("raw_source", {}),
            }
        )
    return normalized


def build_generic_domain_sync_sql(
    entity_snapshot: dict[str, Any],
    update_snapshot: dict[str, Any],
    collection_run: dict[str, Any],
) -> str:
    entity_rows: list[dict[str, Any]] = []
    source_rows: list[dict[str, Any]] = []
    for entity in entity_snapshot.get("entities", []):
        entity_rows.append(
            {
                "domain": entity_snapshot["domain"],
                "snapshot_date": entity_snapshot.get("snapshot_date"),
                "entity_group": entity["entity_group"],
                "entity_rank": entity.get("rank"),
                "name": entity["name"],
                "description": entity.get("description"),
                "official_url": entity.get("official_url"),
                "status": entity.get("status"),
                "raw_entity": entity.get("raw_entity", entity),
            }
        )
        for source in entity.get("sources", []):
            source_rows.append(
                {
                    "domain": entity_snapshot["domain"],
                    "entity_group": entity["entity_group"],
                    "entity_name": entity["name"],
                    "source_type": source["source_type"],
                    "platform": source["platform"],
                    "label": source["label"],
                    "url": source["url"],
                    "is_official": source.get("is_official", True),
                    "is_primary": source.get("is_primary", False),
                    "notes": source.get("notes"),
                }
            )

    update_rows = normalize_update_rows(update_snapshot)
    run_rows = [
        {
            "domain": collection_run["domain"],
            "goal": collection_run["goal"],
            "window_start": collection_run["window_start"],
            "window_end": collection_run["window_end"],
            "entity_scope": collection_run.get("entity_scope", []),
            "source_policy": collection_run.get("source_policy", {}),
            "output_targets": collection_run.get("output_targets", []),
            "notes": collection_run.get("notes"),
            "raw_run": collection_run,
        }
    ]

    entity_payload = sql_literal_json(entity_rows)
    source_payload = sql_literal_json(source_rows)
    update_payload = sql_literal_json(update_rows)
    run_payload = sql_literal_json(run_rows)

    return f"""
{GENERIC_SCHEMA_SQL}

with source_rows as (
    select *
    from jsonb_to_recordset({entity_payload}::jsonb) as input_rows(
        domain text,
        snapshot_date date,
        entity_group text,
        entity_rank integer,
        name text,
        description text,
        official_url text,
        status text,
        raw_entity jsonb
    )
)
insert into public.tracked_entities (
    domain,
    snapshot_date,
    entity_group,
    entity_rank,
    name,
    description,
    official_url,
    status,
    raw_entity,
    updated_at
)
select
    domain,
    snapshot_date,
    entity_group,
    entity_rank,
    name,
    description,
    official_url,
    status,
    coalesce(raw_entity, '{{}}'::jsonb),
    now()
from source_rows
on conflict (domain, entity_group, name)
do update set
    snapshot_date = excluded.snapshot_date,
    entity_rank = excluded.entity_rank,
    description = excluded.description,
    official_url = excluded.official_url,
    status = excluded.status,
    raw_entity = excluded.raw_entity,
    updated_at = now();

with source_rows as (
    select *
    from jsonb_to_recordset({source_payload}::jsonb) as input_rows(
        domain text,
        entity_group text,
        entity_name text,
        source_type text,
        platform text,
        label text,
        url text,
        is_official boolean,
        is_primary boolean,
        notes text
    )
),
matched_rows as (
    select
        entities.id as entity_id,
        source_rows.domain,
        source_rows.entity_group,
        source_rows.entity_name,
        source_rows.source_type,
        source_rows.platform,
        source_rows.label,
        source_rows.url,
        coalesce(source_rows.is_official, true) as is_official,
        coalesce(source_rows.is_primary, false) as is_primary,
        source_rows.notes
    from source_rows
    left join public.tracked_entities as entities
        on entities.domain = source_rows.domain
       and entities.entity_group = source_rows.entity_group
       and entities.name = source_rows.entity_name
)
insert into public.entity_sources (
    entity_id,
    domain,
    entity_group,
    entity_name,
    source_type,
    platform,
    label,
    url,
    is_official,
    is_primary,
    notes,
    updated_at
)
select
    entity_id,
    domain,
    entity_group,
    entity_name,
    source_type,
    platform,
    label,
    url,
    is_official,
    is_primary,
    notes,
    now()
from matched_rows
on conflict (domain, entity_group, entity_name, url)
do update set
    entity_id = excluded.entity_id,
    source_type = excluded.source_type,
    platform = excluded.platform,
    label = excluded.label,
    is_official = excluded.is_official,
    is_primary = excluded.is_primary,
    notes = excluded.notes,
    updated_at = now();

with source_rows as (
    select *
    from jsonb_to_recordset({update_payload}::jsonb) as input_rows(
        domain text,
        entity_group text,
        entity_name text,
        published_at timestamptz,
        source_platform text,
        source_url text,
        title text,
        summary text,
        content_type text,
        source_domain text,
        is_official boolean,
        raw_source jsonb
    )
),
matched_rows as (
    select
        entities.id as entity_id,
        source_rows.domain,
        source_rows.entity_group,
        source_rows.entity_name,
        source_rows.published_at,
        source_rows.source_platform,
        source_rows.source_url,
        source_rows.title,
        source_rows.summary,
        source_rows.content_type,
        source_rows.source_domain,
        coalesce(source_rows.is_official, true) as is_official,
        coalesce(source_rows.raw_source, '{{}}'::jsonb) as raw_source
    from source_rows
    left join public.tracked_entities as entities
        on entities.domain = source_rows.domain
       and entities.entity_group = source_rows.entity_group
       and entities.name = source_rows.entity_name
)
insert into public.entity_updates (
    entity_id,
    domain,
    entity_group,
    entity_name,
    published_at,
    source_platform,
    source_url,
    title,
    summary,
    content_type,
    source_domain,
    is_official,
    raw_source,
    updated_at
)
select
    entity_id,
    domain,
    entity_group,
    entity_name,
    published_at,
    source_platform,
    source_url,
    title,
    summary,
    content_type,
    source_domain,
    is_official,
    raw_source,
    now()
from matched_rows
on conflict (source_url)
do update set
    entity_id = excluded.entity_id,
    domain = excluded.domain,
    entity_group = excluded.entity_group,
    entity_name = excluded.entity_name,
    published_at = excluded.published_at,
    source_platform = excluded.source_platform,
    title = excluded.title,
    summary = excluded.summary,
    content_type = excluded.content_type,
    source_domain = excluded.source_domain,
    is_official = excluded.is_official,
    raw_source = excluded.raw_source,
    updated_at = now();

with source_rows as (
    select *
    from jsonb_to_recordset({run_payload}::jsonb) as input_rows(
        domain text,
        goal text,
        window_start date,
        window_end date,
        entity_scope jsonb,
        source_policy jsonb,
        output_targets jsonb,
        notes text,
        raw_run jsonb
    )
)
insert into public.collection_runs (
    domain,
    goal,
    window_start,
    window_end,
    entity_scope,
    source_policy,
    output_targets,
    notes,
    raw_run,
    updated_at
)
select
    domain,
    goal,
    window_start,
    window_end,
    coalesce(entity_scope, '[]'::jsonb),
    coalesce(source_policy, '{{}}'::jsonb),
    coalesce(output_targets, '[]'::jsonb),
    notes,
    coalesce(raw_run, '{{}}'::jsonb),
    now()
from source_rows
on conflict (domain, window_start, window_end, goal)
do update set
    entity_scope = excluded.entity_scope,
    source_policy = excluded.source_policy,
    output_targets = excluded.output_targets,
    notes = excluded.notes,
    raw_run = excluded.raw_run,
    updated_at = now();
""".strip()


def build_postgres_connection_url(database_url: str) -> str:
    parsed = urllib.parse.urlparse(database_url)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    query.setdefault("sslmode", ["require"])
    new_query = urllib.parse.urlencode(query, doseq=True)
    return urllib.parse.urlunparse(parsed._replace(query=new_query))


def derive_project_ref(project_ref: str | None, project_url: str | None) -> str:
    if project_ref:
        return project_ref
    if not project_url:
        raise ValueError("Provide --project-ref or --project-url.")
    parsed = urllib.parse.urlparse(project_url)
    hostname = parsed.netloc or parsed.path
    match = re.match(r"([a-z0-9]+)\.supabase\.co$", hostname)
    if not match:
        raise ValueError(f"Unable to derive project ref from {project_url!r}")
    return match.group(1)


def run_management_query(project_ref: str, access_token: str, sql: str) -> dict[str, Any]:
    url = f"https://api.supabase.com/v1/projects/{project_ref}/database/query"
    payload = json.dumps({"query": sql, "read_only": False}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        data = response.read().decode("utf-8")
    return json.loads(data or "{}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        default="ai-tracking-directory-2026-04-14.md",
        help="Markdown file to parse.",
    )
    parser.add_argument(
        "--source-date",
        default="2026-04-14",
        help="Source snapshot date stored in Supabase.",
    )
    parser.add_argument("--project-url", default=None, help="Supabase project URL.")
    parser.add_argument("--project-ref", default=None, help="Supabase project ref.")
    parser.add_argument(
        "--database-url",
        default=None,
        help="Direct PostgreSQL connection URL. Supabase usually requires sslmode=require.",
    )
    parser.add_argument(
        "--access-token",
        default=None,
        help="Supabase personal access token with database:write scope.",
    )
    parser.add_argument(
        "--print-sql",
        action="store_true",
        help="Print the generated SQL instead of syncing.",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Execute the generated SQL via Supabase Management API.",
    )
    parser.add_argument(
        "--sync-postgres",
        action="store_true",
        help="Execute the generated SQL via a direct PostgreSQL connection using psql.",
    )
    parser.add_argument(
        "--person-updates-input",
        default=None,
        help="JSON snapshot file for person weekly updates.",
    )
    parser.add_argument(
        "--sync-person-updates-postgres",
        action="store_true",
        help="Sync person weekly updates via direct PostgreSQL connection using psql.",
    )
    parser.add_argument(
        "--entity-snapshot-input",
        default=None,
        help="Generic domain entity snapshot JSON file.",
    )
    parser.add_argument(
        "--update-snapshot-input",
        default=None,
        help="Generic domain update snapshot JSON file.",
    )
    parser.add_argument(
        "--collection-run-input",
        default=None,
        help="Generic domain collection-run JSON file.",
    )
    parser.add_argument(
        "--sync-generic-domain-postgres",
        action="store_true",
        help="Sync generic domain entity/source/update/run snapshots via direct PostgreSQL connection using psql.",
    )
    return parser.parse_args(argv)


def run_postgres_query(database_url: str, sql: str) -> dict[str, Any]:
    connection_url = build_postgres_connection_url(database_url)
    command = [
        "/opt/homebrew/opt/libpq/bin/psql",
        connection_url,
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        sql,
    ]
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )
    return {
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    input_path = Path(args.input).expanduser().resolve()
    markdown_text = input_path.read_text(encoding="utf-8")
    rows = parse_tracking_directory(
        markdown_text,
        source_file=str(input_path),
        source_date=args.source_date,
    )
    sql = build_sync_sql(rows)

    if args.print_sql:
        print(sql)
        return 0

    if args.sync:
        access_token = args.access_token or ""
        if not access_token:
            print("SUPABASE access token is required for --sync.", file=sys.stderr)
            return 2
        project_ref = derive_project_ref(args.project_ref, args.project_url)
        try:
            response = run_management_query(project_ref, access_token, sql)
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            print(f"Supabase API error: {exc.code} {error_body}", file=sys.stderr)
            return 1
        except urllib.error.URLError as exc:
            print(f"Network error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps({"project_ref": project_ref, "rows": len(rows), "response": response}, ensure_ascii=False, indent=2))
        return 0

    if args.sync_postgres:
        if not args.database_url:
            print("DATABASE_URL is required for --sync-postgres.", file=sys.stderr)
            return 2
        try:
            response = run_postgres_query(args.database_url, sql)
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.strip() if exc.stderr else ""
            stdout = exc.stdout.strip() if exc.stdout else ""
            print(
                f"PostgreSQL sync failed.\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}",
                file=sys.stderr,
            )
            return 1
        print(json.dumps({"rows": len(rows), "response": response}, ensure_ascii=False, indent=2))
        return 0

    if args.sync_person_updates_postgres:
        if not args.database_url:
            print("DATABASE_URL is required for --sync-person-updates-postgres.", file=sys.stderr)
            return 2
        if not args.person_updates_input:
            print("PERSON_UPDATES_INPUT is required for --sync-person-updates-postgres.", file=sys.stderr)
            return 2
        update_rows = load_person_updates_snapshot(args.person_updates_input)
        sql = build_person_updates_sync_sql(update_rows)
        try:
            response = run_postgres_query(args.database_url, sql)
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.strip() if exc.stderr else ""
            stdout = exc.stdout.strip() if exc.stdout else ""
            print(
                f"PostgreSQL person update sync failed.\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}",
                file=sys.stderr,
            )
            return 1
        print(json.dumps({"rows": len(update_rows), "response": response}, ensure_ascii=False, indent=2))
        return 0

    if args.sync_generic_domain_postgres:
        if not args.database_url:
            print("DATABASE_URL is required for --sync-generic-domain-postgres.", file=sys.stderr)
            return 2
        if not args.entity_snapshot_input or not args.update_snapshot_input or not args.collection_run_input:
            print(
                "ENTITY_SNAPSHOT_INPUT, UPDATE_SNAPSHOT_INPUT, and COLLECTION_RUN_INPUT are required for --sync-generic-domain-postgres.",
                file=sys.stderr,
            )
            return 2
        entity_snapshot = load_json_document(args.entity_snapshot_input)
        update_snapshot = load_json_document(args.update_snapshot_input)
        collection_run = load_json_document(args.collection_run_input)
        sql = build_generic_domain_sync_sql(
            entity_snapshot=entity_snapshot,
            update_snapshot=update_snapshot,
            collection_run=collection_run,
        )
        try:
            response = run_postgres_query(args.database_url, sql)
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.strip() if exc.stderr else ""
            stdout = exc.stdout.strip() if exc.stdout else ""
            print(
                f"PostgreSQL generic domain sync failed.\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}",
                file=sys.stderr,
            )
            return 1
        print(
            json.dumps(
                {
                    "entities": len(entity_snapshot.get("entities", [])),
                    "updates": len(update_snapshot.get("updates", [])),
                    "response": response,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print(json.dumps({"rows": len(rows), "first_entity": rows[0]["name"] if rows else None}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
