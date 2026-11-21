CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;

CREATE TABLE IF NOT EXISTS channels (
  channel_id     TEXT PRIMARY KEY,
  tracking_since TIMESTAMPTZ NOT NULL,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS videos (
  video_id         TEXT PRIMARY KEY,
  channel_id       TEXT NOT NULL,
  channel_name     TEXT NOT NULL,
  title            TEXT NOT NULL,
  published_at     TIMESTAMPTZ,
  duration_seconds INTEGER NOT NULL,
  status           TEXT NOT NULL CHECK (status IN ('transcribed', 'skipped')),
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS segments (
  video_id      TEXT NOT NULL REFERENCES videos (video_id) ON DELETE CASCADE,
  idx           INTEGER NOT NULL,
  start_seconds REAL NOT NULL,
  end_seconds   REAL NOT NULL,
  speaker       TEXT NOT NULL,
  text          TEXT NOT NULL,
  word_count    INTEGER NOT NULL,
  embedding     extensions.vector(1024),
  PRIMARY KEY (video_id, idx)
);

CREATE TABLE IF NOT EXISTS essays (
  video_id   TEXT PRIMARY KEY REFERENCES videos (video_id) ON DELETE CASCADE,
  title      TEXT NOT NULL,
  body       TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE channels ENABLE ROW LEVEL SECURITY;
ALTER TABLE videos   ENABLE ROW LEVEL SECURITY;
ALTER TABLE segments ENABLE ROW LEVEL SECURITY;
ALTER TABLE essays   ENABLE ROW LEVEL SECURITY;