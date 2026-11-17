CREATE TABLE IF NOT EXISTS channels (
  channel_id     TEXT PRIMARY KEY,
  tracking_since TIMESTAMPTZ NOT NULL,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS videos (
  video_id         TEXT PRIMARY KEY,
  channel_id       TEXT NOT NULL,
  title            TEXT NOT NULL,
  published_at     TIMESTAMPTZ,
  duration_seconds INTEGER NOT NULL,
  status           TEXT NOT NULL CHECK (status IN ('transcribed', 'skipped')),
  transcript       TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK ((status = 'transcribed') = (transcript IS NOT NULL))
);

ALTER TABLE channels ENABLE ROW LEVEL SECURITY;
ALTER TABLE videos ENABLE ROW LEVEL SECURITY;
