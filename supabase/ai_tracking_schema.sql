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
