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
