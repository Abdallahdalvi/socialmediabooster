-- ================================================================
-- YT Views Booster — Supabase schema
-- Run this once in your Supabase SQL Editor (or via psql).
-- Uses default `public` schema; policies allow the SERVICE_ROLE_KEY
-- to read/write everything (backend uses service role only).
-- ================================================================

create table if not exists public.yt_jobs (
  id                     uuid primary key,
  video_urls             jsonb not null,
  views_per_video        int  not null default 1,
  watch_seconds          int  not null default 8,
  location_mode          text not null default 'random',
  countries              jsonb not null default '[]'::jsonb,
  status                 text not null default 'queued',
  created_at             timestamptz not null default now(),
  completed_at           timestamptz,
  total_videos           int not null default 0,
  processed_videos       int not null default 0,
  total_views_delivered  int not null default 0,
  unique_ips             jsonb not null default '[]'::jsonb,
  countries_covered      jsonb not null default '[]'::jsonb,
  failures               int not null default 0,
  current_ip             text,
  current_country        text,
  current_country_code   text
);

create index if not exists yt_jobs_created_at_idx on public.yt_jobs (created_at desc);
create index if not exists yt_jobs_status_idx     on public.yt_jobs (status);

create table if not exists public.yt_job_logs (
  id       bigserial primary key,
  job_id   uuid not null references public.yt_jobs(id) on delete cascade,
  level    text not null,
  msg      text not null,
  ip       text,
  country  text,
  country_code text,
  ts       timestamptz not null default now()
);

create index if not exists yt_job_logs_job_ts_idx on public.yt_job_logs (job_id, ts);

-- Optional: view for job summaries
create or replace view public.yt_job_summary as
select id, status, created_at, completed_at,
       total_videos, processed_videos, total_views_delivered,
       jsonb_array_length(unique_ips)        as unique_ip_count,
       jsonb_array_length(countries_covered) as country_count
from public.yt_jobs
order by created_at desc;

-- Enable RLS but allow service_role full access (default anyway).
alter table public.yt_jobs      enable row level security;
alter table public.yt_job_logs  enable row level security;

-- Service role bypasses RLS by design; add a permissive policy for
-- anon/authenticated read-only if you want to expose data publicly.
-- (Left disabled by default.)
