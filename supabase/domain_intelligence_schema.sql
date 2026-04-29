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
