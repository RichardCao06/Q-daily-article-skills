-- Two-axis editorial model for Q-daily articles.
--
-- Before this migration the only routing axis was `articles.category_slug`,
-- which conflated TWO independent concepts:
--
--   - 领域 (topic domain): smart / business / design / fashion / ...
--   - 栏目 (editorial column): 好文章 / 好观点 / 好家伙 / 好论文
--
-- This migration introduces the column axis as a first-class FK on `articles`,
-- leaving `category_slug` to mean strictly "topic domain".
--
-- column_slug is nullable on purpose: existing rows were written before the
-- axis existed, and we want to backfill them as a separate editorial pass
-- rather than gate this migration on full coverage.

create table if not exists public.columns (
    slug        text primary key,
    name        text not null,
    description text,
    sort_order  integer not null default 0,
    created_at  timestamptz not null default now()
);

insert into public.columns (slug, name, description, sort_order) values
    ('good-article', '好文章', '深度特稿、人物、复盘、组合——长读、需要叙事弧的报道',                 10),
    ('good-take',    '好观点', '评论、立场、解读——以判断和论证为核心的稿件',                       20),
    ('good-grief',   '好家伙', '产业级动作、大公司事件、震撼发布——节奏快、信号强、带惊讶感的新闻特写', 30),
    ('good-paper',   '好论文', '研究、调研、技术机制解释——以论文/数据/机制为基础的解释类稿件',       40)
on conflict (slug) do update set
    name        = excluded.name,
    description = excluded.description,
    sort_order  = excluded.sort_order;

alter table public.articles
    add column if not exists column_slug text
        references public.columns(slug) on update cascade;

create index if not exists articles_column_slug_idx
    on public.articles (column_slug, published_at desc);

-- Public read on the columns dictionary, mirroring categories.
alter table public.columns enable row level security;

drop policy if exists "Public read columns" on public.columns;
create policy "Public read columns" on public.columns
    for select using (true);
