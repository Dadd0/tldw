# Spec: yt-smart-transcribe (ingestion and transcription)

## Objective

A service on a VPS that watches a list of YouTube channels and stores a plain-text transcript of every new video in Supabase. The transcripts are the input for a later article-generation stage, which is not part of this spec.

The only user is the owner, on one VPS.

Two entry points share one pipeline:

- `poll` finds new videos on the followed channels and transcribes them. Cron runs it.
- `transcribe <video>` runs the pipeline for one video on demand.

## Tech Stack

- Python >= 3.14, managed with uv
- `yt-dlp` (Python library) for metadata and audio download
- `ffmpeg` on the host, used by yt-dlp for mp3 extraction and by the program for chunking
- `requests` for the RSS feeds and OpenRouter
- `psycopg` for a direct Postgres connection to Supabase. No Supabase client library.
- `python-dotenv` for configuration
- Standard library for the rest: `argparse`, `xml.etree.ElementTree`, `fcntl`, `tempfile`, `subprocess`
- `pytest` as the only dev dependency

## Configuration

All settings live in `.env`. A missing or invalid value stops the program at startup with exit code 2, before any network call.

| Variable | Meaning | Default |
|---|---|---|
| `OPENROUTER_API_KEY` | OpenRouter key | required |
| `TRANSCRIPTION_MODEL_ID` | OpenRouter model used for transcription | required |
| `SUPABASE_DB_URL` | Postgres connection string (session pooler) | required |
| `POLL_INTERVAL_MINUTES` | Minimum time between two polls | 30 |
| `CHUNK_SECONDS` | Maximum audio length sent in one transcription request | 3600 |

Fixed in code: channel list path `channels.txt`, minimum video duration 60 seconds, mp3 bitrate 64 kbps.

`channels.txt` holds one channel ID per line. Blank lines and lines starting with `#` are ignored. A line that is not a valid channel ID (`UC` followed by 22 characters) stops the program with exit code 2.

## Commands

```
Poll:        uv run main.py poll
Manual:      uv run main.py transcribe <video-id-or-url>
Test:        uv run pytest
Add a dep:   uv add <package>
```

Crontab on the VPS, written once:

```
* * * * * cd /path/to/yt-smart-transcribe && uv run main.py poll >> poll.log 2>&1
```

Database setup: `psql "$SUPABASE_DB_URL" -f schema.sql`, safe to re-run. See `docs/database.md`.

## Behavior

### Poll scheduling

Cron fires `poll` every minute. The program decides whether it is due, using one local file, `.poll.lock`:

1. Take a non-blocking exclusive lock on `.poll.lock`. If another poll holds it, exit 0 silently.
2. If the file's modification time is less than `POLL_INTERVAL_MINUTES` ago, exit 0 silently.
3. Set the modification time to now and run the poll.

A tick that is not due touches neither the network nor the DB and prints nothing.

### Finding new videos

For each channel in `channels.txt`:

1. Fetch `https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}` and parse each entry into video ID, title, and published time.
2. Look the channel up in the `channels` table.
   - **Not there (first sight):** insert it with `tracking_since` set to the published time of the latest feed entry, or to now if the feed is empty.
   - **There:** read its `tracking_since`.
3. The candidates are the feed entries published at or after `tracking_since` whose video ID is not in the `videos` table. One query per channel checks all feed IDs.
4. Process the candidates oldest first.

Consequences:

- A newly added channel gets exactly its latest video transcribed.
- After an outage, the next poll picks up everything missed, up to the ~15 entries the feed holds.
- A video that failed is a candidate again on the next poll, because nothing was recorded for it.
- A video transcribed manually from a channel that is not followed does not affect that channel's first sight later.

### Pipeline for one video

All files live in a temporary directory that is removed when the video finishes, whether it succeeded or failed.

1. **Metadata.** Ask yt-dlp for the video's info without downloading.
2. **Duration filter (poll only).** If the duration is under 60 seconds, store a row with status `skipped` and no transcript, and stop. This is how Shorts are dropped without being re-checked on every poll.
3. **Download.** Download the best audio stream and convert it to mp3 at 64 kbps.
4. **Chunk.** Split the mp3 with ffmpeg into segments of at most `CHUNK_SECONDS`, without re-encoding. A shorter audio gives one segment.
5. **Transcribe.** For each segment in order, POST to `https://openrouter.ai/api/v1/audio/transcriptions` with the model ID and the base64 audio, as `main.py` does today. A non-200 response or an empty `text` is a failure.
6. **Store.** Join the segment texts with a newline and upsert one row into `videos` with status `transcribed`.

The manual command differs in two ways: it ignores the duration filter, and it always runs, overwriting any existing row for that video.

### Failure handling

- The first error in a video abandons that video. There are no retries inside a run, no partial transcript, and no DB write.
- A poll continues with the remaining videos and channels.
- Each failure prints one line to stderr: `FAILED <video-id or channel-id> <stage>: <message>`.
- The exit code names the stage of the first failure:

| Code | Meaning |
|---|---|
| 0 | Success, or poll not due |
| 2 | Configuration or usage error |
| 3 | Feed fetch or parse failed |
| 4 | Metadata or download failed |
| 5 | Chunking or transcription failed |
| 6 | Database read or write failed |

Known and accepted:

- A permanently unavailable video (private, members-only) fails on every poll until it leaves the feed.
- An upcoming livestream or premiere fails with code 4 until it has aired, then succeeds.
- A long video that fails on a late chunk pays again for the earlier chunks on the next poll.
- A chunk boundary can cut a word in half.

## Database Schema

`schema.sql`:

```sql
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
```

- Row level security is on with no policies, so Supabase's public API key cannot read or write the tables. The program connects directly as the table owner, which row level security does not restrict.
- `videos.channel_id` has no foreign key, because manual videos can come from channels that are not followed.
- Removing a channel from `channels.txt` stops polling it and leaves its rows. Adding it back resumes from the old `tracking_since`.

## Project Structure

```
main.py                  → entry point: parses the CLI arguments, calls the package, sets the exit code
yt_smart_transcribe/
  config.py              → loads and validates `.env` and `channels.txt`
  errors.py              → `StageError` and the exit codes
  feed.py                → fetches and parses a channel's RSS feed, selects the candidates
  audio.py               → yt-dlp metadata and mp3 download, ffmpeg chunking
  transcription.py       → the OpenRouter transcription request
  db.py                  → Supabase reads and writes for `channels` and `videos`
  pipeline.py            → processes one video end to end
  poll.py                → the lock and due check, the loop over channels and candidates
tests/                   → one test file per module tested, plus a sample feed XML
schema.sql               → the two tables above
channels.txt             → followed channel IDs
SPEC.md                  → this file
.env                     → secrets and settings (git-ignored)
.poll.lock               → poll lock and last-run time (git-ignored)
poll.log                 → cron output (git-ignored)
```

Module rules:

- `main.py` holds no logic beyond argument parsing and turning a `StageError` into an exit code.
- `feed.py`, `audio.py`, `transcription.py`, and `db.py` each wrap one external system and do not import each other.
- Only `pipeline.py` and `poll.py` combine them. `poll.py` calls `pipeline.py`, never the reverse.
- Only `config.py` reads environment variables. The other modules receive values as arguments.
- The package is not installed. `main.py` imports it from the project root, and `pyproject.toml` sets pytest's `pythonpath` to `.` so the tests can do the same.

## Code Style

Plain functions, type hints, no classes beyond one exception type that carries the exit code. Errors propagate; nothing is caught except at the per-video and per-channel boundary in `poll.py` and at the top of `main.py`.

```python
class StageError(Exception):
    def __init__(self, code: int, stage: str, message: str):
        super().__init__(message)
        self.code, self.stage = code, stage


def parse_feed(xml: str) -> list[dict]:
    """Return the feed's entries as {video_id, title, published}, oldest first."""
    ns = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
    entries = [
        {
            "video_id": e.findtext("yt:videoId", namespaces=ns),
            "title": e.findtext("a:title", namespaces=ns),
            "published": datetime.fromisoformat(e.findtext("a:published", namespaces=ns)),
        }
        for e in ElementTree.fromstring(xml).findall("a:entry", ns)
    ]
    return sorted(entries, key=lambda e: e["published"])
```

## Testing Strategy

- pytest, tests in `tests/`.
- Unit tests cover the logic that has branches and needs no network:
  - `feed.py`: feed parsing, against a saved feed XML
  - `feed.py`: candidate selection (first sight, `tracking_since`, already stored IDs)
  - `config.py`: `channels.txt` parsing and validation
  - `poll.py`: the due check on `.poll.lock`
  - `poll.py`: exit code selection when several videos fail
- yt-dlp, ffmpeg, OpenRouter, and Supabase are not mocked. They are checked by one manual end-to-end run: `uv run main.py transcribe <id of a short spoken video>`, then confirming the row in Supabase.

## Boundaries

- **Always:** run `uv run pytest` before a commit; validate configuration and `channels.txt` at startup; clean up audio files on every path.
- **Ask first:** changing `schema.sql`; adding a dependency; writing anything to the DB on failure; adding in-run retries.
- **Never:** commit `.env` or print its values; store audio in Supabase; catch an error and continue within a single video.

## Success Criteria

1. With a channel newly added to `channels.txt`, one `poll` stores exactly one `transcribed` row, for that channel's latest video (or one `skipped` row if it is under 60 seconds).
2. A second `poll` right after makes no transcription request and stores nothing.
3. A video published after the channel was added has its transcript in `videos` after the next due poll.
4. `poll` run twice within `POLL_INTERVAL_MINUTES` does nothing the second time and exits 0. Two simultaneous polls never both run.
5. A video longer than `CHUNK_SECONDS` is stored as one transcript containing the text of all its chunks in order.
6. With one video failing and one healthy video in the same poll, the healthy one is stored, the failed one leaves no row, stderr has one `FAILED` line, and the exit code matches the failed stage.
7. `transcribe <video>` stores the transcript of any single video, including one already stored or under 60 seconds.
8. No mp3 or chunk file remains on disk after any run.
9. With a required variable missing from `.env`, either command exits 2 without a network call.


