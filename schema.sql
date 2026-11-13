create table channels (
  channel_id     text primary key,
  tracking_since timestamptz not null,
  created_at     timestamptz not null default now()
);

create table videos (
  video_id         text primary key,
  channel_id       text not null,
  title            text not null,
  published_at     timestamptz,
  duration_seconds integer not null,
  status           text not null check (status in ('transcribed', 'skipped')),
  transcript       text,
  created_at       timestamptz not null default now(),
  check ((status = 'transcribed') = (transcript is not null))
);

alter table channels enable row level security;
alter table videos enable row level security;
