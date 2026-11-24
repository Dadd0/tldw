# TL;DW

TL;DW ("too long; didn't watch") turns talk-heavy YouTube videos into short essays you can read in a few minutes. It watches a list of channels, transcribes each new video with speaker labels and timestamps, writes one standalone essay per video, and shows the essays on a private front page that looks like Hacker News. A chat page answers questions across every transcript and links each answer to the essay and to the moment in the video.

The premise is that reading is several times faster than listening, and that for talks, interviews and podcasts the picture adds nothing.

This file is the specification. The "Status" section says which parts are built; everything else is the target.

## Priorities

In this order: a working product, a small codebase, simple and readable code in small modules. One person uses this on one server. Anything that adds code, files, settings, dependencies or moving parts without being needed for the product to work does not belong here. When two designs both work, build the one with less code.

## Who it is for

One person, the owner, on one VPS. There are no accounts and no authentication, and there never will be. The site and the chat listen only on the VPS's loopback address and the owner reaches them through an SSH tunnel.

## Out of scope

Do not build any of these unless the owner asks:

- Public access, login, or multiple users
- Votes, comments, read/unread tracking, search, tags, per-channel pages
- More than one writing style, or per-channel styles
- Automatic rewriting of existing essays when `style.md` changes
- A JavaScript framework or a build step for the front page
- A separate vector database, or a vector index
- Retries, queues, or background workers beyond cron
- Settings for values that have one working choice (see "Fixed in code")

## Status

### Built and working

- Loading and validating `.env` and `channels.txt`, including optional two-letter language codes per channel.
- Fetching and parsing a channel's RSS feed, and selecting which entries are new.
- Unit tests for feed parsing, candidate selection, and config parsing.
- `transcribe <video> [--language it]` requests word timestamps and speaker labels, builds segments, and saves the video and its segments in one Postgres transaction.
- `schema.sql` defines the new database schema. `uv run pytest` passed locally, including the segment tests. The CLI help and invalid-language checks also passed.
- Live verification passed with [Apollo 11: Landing on the Moon](https://www.youtube.com/watch?v=nOcDftgR5UQ). Supabase stored the video as `transcribed` with 11 timestamped segments and speaker labels.
- `transcribe <video> --max-minutes N` analyzes up to the first N minutes and prints the segments in the terminal as an unsaved preview.
- `poll` uses a non-blocking file lock on Linux and WSL. Live checks confirmed that a video under three minutes was stored as `skipped`, an eligible video was transcribed with stored segments, and a second poll skipped the stored video.
- `uv run pytest` passed on WSL, including the poll lock test.
- `write <video-id>` writes or replaces an essay using `style.md`. A live run for Apollo 11 saved an essay in Supabase.
- `transcribe` writes the essay after saving the transcript. After scanning the feeds, `poll` writes essays for stored transcripts that still need one.
- Stage 3 embeds segments of 20 words or more: `transcribe` runs it after the essay, and `poll` runs it for every video with unembedded segments. A live run with `mongodb/voyage-4-lite` stored 1024-dimension vectors for all 9 eligible segments, and a cosine search for "astronauts landing on the moon" returned the Apollo 11 landing segment first. That run called `embed_video` directly. The stage 3 path through `poll` and `transcribe` has not been run live yet: confirm it on the next real poll that has new segments.
- The private front page lists saved essays and renders them as HTML. A local browser check passed with an essay stored in Supabase.
- The private chat searches embedded transcript segments and streams answers grounded in them. A local browser check used the Apollo 11 transcript.
- The site includes an essay chat panel and an Ask page that share a list of chats kept in the browser's `localStorage`.

## Tech stack

- Python >= 3.14, managed with uv
- `yt-dlp` (Python library) and `ffmpeg` on the host, for audio download and chunking
- OpenRouter for every model call: transcription, embeddings, essay writing, chat. One key.
- `requests` for the RSS feeds, the transcription endpoint and the embeddings endpoint
- `python-dotenv` to load `.env`
- `psycopg[binary]` for Postgres. The database is Supabase, used as plain Postgres with the `pgvector` extension. No Supabase client library.
- `pydantic-ai-slim[openrouter,web]` for the two agents only: the essay writer and the chat. The `web` extra also installs Starlette and Uvicorn, which serve both web apps.
- `jinja2` for the front page's HTML and `markdown-it-py` to render essay bodies
- `pytest` as the only dev dependency

PydanticAI is not used for transcription or embeddings. It has no transcription API, and both are single HTTP calls.

## Configuration

`.env` holds four settings, all required. A missing value stops the program at startup with exit code 2, before any network call. Only `config.py` reads environment variables.

| Variable | Meaning |
|---|---|
| `OPENROUTER_API_KEY` | OpenRouter key |
| `SUPABASE_DB_URL` | Postgres connection string (session pooler) |
| `ESSAY_MODEL_ID` | OpenRouter model that writes essays |
| `CHAT_MODEL_ID` | OpenRouter model that answers in the chat |

The local setup uses `nvidia/nemotron-3-ultra-550b-a55b:free` for both `ESSAY_MODEL_ID` and `CHAT_MODEL_ID`.

Fixed in code, each as a constant in the one module that uses it:

| Constant | Value | Module |
|---|---|---|
| Transcription model | `x-ai/grok-stt-2.0` | `transcription.py` |
| Embedding model | `mongodb/voyage-4-lite` (1024 dimensions) | `embedding.py` |
| Audio chunk length | 300 seconds | `audio.py` |
| mp3 bitrate | 64 kbps | `audio.py` |
| Minimum video duration when polling | 180 seconds | `pipeline.py` |
| Segment size | 200 words | `segments.py` |
| Smallest segment that gets embedded | 20 words | `db.py` (in the query) |
| Segments returned per chat search | 8 | `answering.py` |
| Essays per page | 30 | `site.py` |
| Front page address | `http://localhost:8000` | `answering.py` |

The transcription and embedding models are constants because the request shape is specific to the first and the database column size is specific to the second.

`channels.txt` holds one channel per line: a channel ID (`UC` followed by 22 characters), optionally followed by a two-letter language code. Text after `#` is a comment. Blank lines are ignored. An invalid line stops the program with exit code 2.

```
UCxxxxxxxxxxxxxxxxxxxxxx        # language is detected
UCyyyyyyyyyyyyyyyyyyyyyy it     # always transcribe as Italian
```

`style.md` is one plain-language description of how essays should read. It applies to every essay. See "Stage 2".

## Local setup

Requires `uv` (manages Python >= 3.14), `ffmpeg`, and `psql` (for database setup).

1. Install dependencies: `uv sync`
2. Create `.env` from `env.example` (`cp env.example .env`) and set `OPENROUTER_API_KEY`, `SUPABASE_DB_URL` (Supabase Session pooler URL), `ESSAY_MODEL_ID`, and `CHAT_MODEL_ID`.
3. Add followed channel IDs to `channels.txt` (see "Configuration").
4. Initialize the database: `set -a; source .env; set +a && psql "$SUPABASE_DB_URL" -f schema.sql`
5. Verify the setup: `uv run pytest` (runs offline, no network or database required).

## Commands

```
Poll:              uv run main.py poll
One video:         uv run main.py transcribe <video-id-or-url> [--language it]
Rewrite an essay:  uv run main.py write <video-id>
Essays and Ask:    uv run uvicorn --factory tldw.site:build_site --host 127.0.0.1 --port 8000
Standalone chat:   uv run uvicorn --factory tldw.answering:build_chat --host 127.0.0.1 --port 7932
Format:            uvx ruff format
Test:              uv run pytest
Database setup:    psql "$SUPABASE_DB_URL" -f schema.sql
```

Crontab on the VPS. Cron's default `PATH` does not include uv, so set it:

```
PATH=/home/<user>/.local/bin:/usr/local/bin:/usr/bin:/bin
*/30 * * * * cd /path/to/tldw && uv run main.py poll >> poll.log 2>&1
```

From the owner's machine, one tunnel reaches both apps. Then open `http://localhost:8000`.

```
ssh -N -L 8000:127.0.0.1:8000 -L 7932:127.0.0.1:7932 <user>@<vps>
```

## How a video becomes an essay

Three stages. Each decides what to do from what is stored, so work that failed is picked up on the next poll without repeating the stages before it.

| Stage | Runs for | Writes |
|---|---|---|
| 1. Transcribe | Videos with no `videos` row | One `videos` row and its `segments` |
| 2. Write | Videos with status `transcribed` and no `essays` row | One `essays` row |
| 3. Embed | Videos that have segments of 20 words or more with no embedding | `segments.embedding` |

`pipeline.py` has one function per stage, each taking one video. The commands call them like this:

- `poll` takes a non-blocking exclusive lock on `.poll.lock` and exits 0 silently if another poll holds it. It then runs stage 1 for every new video of every channel, then stage 2 for every video the stage 2 query returns, then stage 3 likewise. Stages 2 and 3 look at the whole database, not only at the videos found in this poll.
- `transcribe <video>` runs stages 1, 2 and 3 for that video, whether or not it is already stored. If stage 2 or 3 fails, it deletes the video with its segments and essay, so a failed run leaves nothing stored. The submit page uses this command. `poll` keeps a transcript whose essay or embedding failed, so the next poll retries those stages without paying for transcription again.
- `write <video-id>` runs stage 2 for that video, replacing its essay. If the video is not stored with status `transcribed`, it prints an error and exits with code 2.

### Finding new videos

For each channel in `channels.txt`:

1. Fetch `https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}` and parse each entry into video ID, title and published time.
2. Look the channel up in the `channels` table. If it is not there, insert it with `tracking_since` set to the published time of the latest feed entry, or to now if the feed is empty.
3. The candidates are the feed entries published at or after `tracking_since` whose video ID is not in `videos`.
4. Process the candidates oldest first.

So a newly added channel gets exactly its latest video, an outage is caught up from the roughly 15 entries the feed holds, and a video whose transcription failed is a candidate again on the next poll.

### Stage 1: transcribe

All files live in a temporary directory that is removed when the video finishes.

1. **Metadata.** Ask yt-dlp for the video's ID, channel ID, channel name, title, duration and publish time, without downloading.
2. **Duration filter (poll only).** Under 180 seconds: store a row with status `skipped` and stop. This drops Shorts, which can be up to 3 minutes long, without re-checking them on every poll. There is no upper limit; a 4-hour video is transcribed.
3. **Download.** Best audio stream, converted to mp3 at 64 kbps.
4. **Chunk.** Split with ffmpeg into pieces of at most 300 seconds, without re-encoding.
5. **Transcribe.** Send each chunk, in order, with the request below. A non-200 response fails the video. A chunk with an empty `words` array is normal (music, silence) and contributes nothing. The video fails only if all chunks together have no words.
6. **Build segments.** See "Segments".
7. **Store.** In one transaction: upsert the `videos` row with status `transcribed`, replace all of the video's segments, and delete the video's essay if it has one. Deleting the essay is what makes stage 2 write a new one from the new transcript.

Request to `POST https://openrouter.ai/api/v1/audio/transcriptions`:

```json
{
  "model": "x-ai/grok-stt-2.0",
  "input_audio": {"data": "<base64 mp3>", "format": "mp3"},
  "response_format": "verbose_json",
  "timestamp_granularities": ["segment", "word"],
  "language": "it",
  "provider": {"options": {"xai": {"diarize": true}}}
}
```

`language` is sent only when there is one: from the channel's line in `channels.txt` when polling, from `--language` for the `transcribe` command. The `transcribe` command does not read `channels.txt`.

The response's `words` array is the only part used:

```json
{"word": "Supposedly", "start": 0.12, "end": 0.46, "speaker": 0}
```

### Segments

A segment is a run of consecutive words by one speaker, with the time it starts and ends. Segments are what the essay writer reads and what the chat searches. `segments.py` builds them with no network or database access:

- Add `chunk_index * 300` to every word's `start` and `end`, so times are measured from the start of the video.
- Walk the words of one chunk in order. Start a new segment when the speaker changes or the current segment reaches 200 words. A segment never spans two chunks.
- A segment's text is its words joined with spaces. Its speaker is the string `"{chunk_index}.{speaker}"`, for example `"3.1"`.
- `idx` numbers the segments of a video from 0, across all chunks.

Speaker numbers are assigned per request, so speaker 0 in one chunk is not necessarily speaker 0 in the next. The label makes that explicit. Nothing tries to match speakers across chunks.

### Stage 2: write the essay

The essay writer is a PydanticAI agent in `essay.py`, built with `OpenRouterModel(ESSAY_MODEL_ID, provider=OpenRouterProvider(api_key=...))`. Its output is a Pydantic model with two fields: `title` and `body` (Markdown, no top-level heading).

Its instructions are the fixed rules below followed by the contents of `style.md`. Its input is the video title, the channel name, and every segment in order, one per line:

```
[0:12:45] 2.1: text of the segment
```

Fixed rules, written into the agent's instructions:

- Write a standalone essay, as if the ideas had been written down in the first place. State the thesis first and follow the logic of the argument, not the order of the video.
- Never mention the video, the speaker, the host, the channel, or the audience. No "in this talk".
- Drop sponsor reads, greetings, banter, repetition and housekeeping.
- Explain and connect the ideas, but add no fact, number, quotation or claim that is not in the transcript.
- Speaker labels are local to a chunk (the number before the dot). Use them to tell questions from answers. Do not name speakers.
- The transcript is machine-made. Ignore passages that are incoherent, repeated in a loop, or in a different script from the rest.
- Give the essay its own title. Do not reuse the video title.

`style.md` starts with these lines, and the owner edits it freely:

```
Write in English, whatever the language of the source.
Write like a good technical blog post: Simon Willison, Sean Goedecke, Karpathy, LessWrong.
Direct, first-principles, no preamble and no summary at the end.
Short paragraphs. Section headings only when the essay has distinct parts.
For a 10–20 minute talk with several substantive points, aim for 650–900 words.
Develop each major step of the argument and explain how the strongest examples from the transcript support it.
Use fewer words when the source has less to develop. Keep the essay under 1,500 words.
```

A changed `style.md` affects only essays written afterwards.

The whole transcript goes to the model in one request. A model whose context cannot hold a multi-hour transcript fails that video; pick `ESSAY_MODEL_ID` accordingly.

### Stage 3: embed

For one video, take its segments of 20 words or more that have no embedding, in `idx` order, and send their texts in one request. Store all the vectors together. Shorter segments are never embedded, so interjections do not pollute search.

Request to `POST https://openrouter.ai/api/v1/embeddings`:

```json
{"model": "mongodb/voyage-4-lite", "input": ["text of segment 0", "text of segment 1"]}
```

The response has a `data` array of `{"index": 0, "embedding": [1024 floats]}`. Match each vector to its input by `index`. A non-200 response, or a `data` array whose length differs from the input's, fails the video.

`embedding.py` exposes one function that takes a list of texts and returns a list of vectors. The chat's search calls the same function with one text.

### Failure handling

- The first error in a stage abandons that video for that stage. There are no retries inside a run and nothing partial is stored.
- A poll continues with the remaining videos, channels and stages.
- Each failure prints one line to stderr: `FAILED <video-id or channel-id> <stage>: <message>`.
- The exit code is that of the first failure:

| Code | Meaning |
|---|---|
| 0 | Success, or another poll is running |
| 2 | Configuration or usage error |
| 3 | Feed fetch or parse failed |
| 4 | Metadata or download failed |
| 5 | Chunking or transcription failed |
| 6 | Database read or write failed |
| 7 | Essay writing failed |
| 8 | Embedding failed |

Known and accepted:

- A permanently unavailable video (private, members-only) fails on every poll until it leaves the feed.
- An upcoming livestream or premiere fails with code 4 until it has aired.
- A download sometimes fails with `HTTP Error 403` and works when tried again. The next poll is the retry.
- A long video that fails on a late chunk pays again for the earlier chunks on the next poll.
- A video whose essay keeps failing is attempted on every poll, and a failed attempt can still cost a model call.
- A chunk boundary can cut a word in half, and a segment boundary can cut a sentence.
- The transcription model sometimes invents text on unclear audio and puts a turn boundary a word or two off. See "Verified facts".

## Front page

`site.py` builds a Starlette app with four pages rendered on the server with Jinja2. The chat views use native JavaScript and CSS.

**`/`** lists essays newest first by the video's publish time (the row's creation time when the publish time is unknown), 30 per page, with a "More" link to `/?p=2`. The design uses an orange (`#ff6600`) top bar, a `#f6f6ef` background, Verdana at 10pt, and a numbered list. The top bar holds the name "TL;DW" and the **Read**, **Ask** and **Submit** links. Each row is:

```
1. Essay title
   Channel name | 1h 42m video | 6 min read | 3 hours ago
```

The title links to the essay page. Reading time is the essay's word count divided by 230, rounded up.

**`/essay/{video_id}`** shows the essay title, the same line of details, and the body rendered with `MarkdownIt("commonmark", {"html": False})`. The option matters: without it, markdown-it-py passes raw HTML in the essay straight into the page.

**`/submit`** accepts an 11-character video ID or a YouTube watch, youtu.be, shorts or live URL. A same-origin form POST on the loopback site starts `uv run main.py transcribe <video>` in a detached process from the project root and redirects to a confirmation page. Its output and errors append to the git-ignored `transcribe.log`. Submitting a stored video again replaces its transcript and essay, just as the CLI does.

**`/ask`** shows the chat in the main area, beside a sidebar that lists the saved chats newest first, opens the one clicked, and starts an empty one with **new chat**. Chats are kept in `localStorage` under one key, `tldw.chats`, so they survive browser restarts and every tab sees them. The key holds the ID of the current chat and the list of chats, each with an ID, a title taken from its first question, the time of its last answer and its turns. The essay panel shows the current chat, so one chat can continue on either page. There is no context selector: a question sent from an essay's panel is about that essay, and a question sent from `/ask` or from the panel on the home page searches everything. A retry uses the page it is sent from. A chat with no answers is dropped once another chat is used; other chats are never deleted. Read and Ask are separate server-rendered pages joined by plain links; `chat.js` handles only the chat. Leaving a page or opening another chat cancels a reply that is still in flight, and the question is kept ready to retry. **Back to Read** links to the last Read page visited, or to the home page.

## Chat

`answering.py` builds the agent using `CHAT_MODEL_ID`. The blog's `POST /api/ask` accepts a question, the context of the page it was sent from, and the completed turns. The `essay` context filters by that essay's video. The `all` context searches all embedded segments, including videos without essays. When a chat moves between pages, earlier turns help resolve references and the new page's context controls retrieval.

`search(query)` embeds the query and selects up to 8 nearest embedded segments by cosine distance within the selected scope. It returns the segment text, video title, channel name, optional essay title and URL, and the video URL at that moment (`https://www.youtube.com/watch?v={video_id}&t={start}s`, with `start` rounded down to a whole second). The standalone chat on `7932` uses `agent.to_web()` and searches only videos with essays.

The agent's instructions:

- Search before answering, more than once with different wording when a question spans several topics or sources, and build the answer on what `search` returns.
- When the answer draws on several videos, say which part comes from which.
- Always answer. Where the transcripts do not cover the question, fill the gap from general knowledge and say which parts do not come from the transcripts.
- Format in Markdown: bold the key terms and the sentences that carry the answer, italics for quotations, lists and headings only when the content needs them.
- Write plainly for one reader, without greetings, run-ups, closing summaries or common AI phrasing.
- The standalone chat links each claim from the transcripts to the essay and the moment in the video.

Facts about `to_web()` that shape the design:

- It claims the routes `/` and `/{id}` and cannot be mounted under a sub-path. The standalone app serves it on its own port.
- It answers only to requests whose `Host` is an IP address or `localhost`. Through the SSH tunnel the host is `localhost`, so no setting is needed.
- By default it downloads its UI from a CDN on first use and caches it.
- PydanticAI documents it as meant for local development. That is acceptable here because one person uses it through a tunnel.

## Database schema

`schema.sql`, safe to re-run:

```sql
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
  video_id      TEXT NOT NULL REFERENCES videos ON DELETE CASCADE,
  idx           INTEGER NOT NULL,
  start_seconds REAL NOT NULL,
  end_seconds   REAL NOT NULL,
  speaker       TEXT NOT NULL,
  text          TEXT NOT NULL,
  word_count    INTEGER NOT NULL,
  embedding     vector(1024),
  PRIMARY KEY (video_id, idx)
);

CREATE TABLE IF NOT EXISTS essays (
  video_id   TEXT PRIMARY KEY REFERENCES videos ON DELETE CASCADE,
  title      TEXT NOT NULL,
  body       TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE channels ENABLE ROW LEVEL SECURITY;
ALTER TABLE videos   ENABLE ROW LEVEL SECURITY;
ALTER TABLE segments ENABLE ROW LEVEL SECURITY;
ALTER TABLE essays   ENABLE ROW LEVEL SECURITY;
```

- Row level security is on with no policies, so Supabase's public API key cannot read or write the tables. The program connects as the table owner, which row level security does not restrict.
- `videos.channel_id` has no foreign key, because a video transcribed by hand can come from a channel that is not followed.
- Removing a channel from `channels.txt` stops polling it and leaves its rows.
- Vectors are passed to Postgres as text (`'[0.1,0.2,...]'::vector`) and compared with `<=>`. No extra Python package is needed.
- There is no vector index. At this size an exact scan is fast and always returns the true nearest segments.
- The extension lives in Supabase's `extensions` schema. If Postgres reports that the type `vector` does not exist, that schema is not on the connection's search path: write `extensions.vector` in the schema and the queries.

On a fresh Supabase database, apply `schema.sql` directly. If the database still has the older `videos` table with a `transcript TEXT` column and no `channel_name`, confirm that its rows can be discarded before running `DROP TABLE videos;` and applying `schema.sql`. Keep the `channels` table.

If `segments.embedding` is still `vector(1536)` (from the earlier `openai/text-embedding-3-small` model), re-running `schema.sql` does not change it. Run `ALTER TABLE segments ALTER COLUMN embedding TYPE vector(1024) USING NULL;` once: it clears the old vectors, and the next poll embeds the segments again. The shared Supabase database was converted on 2026-11-21.

## Project structure

```
main.py            → CLI entry point: parses arguments, calls the package, sets the exit code
tldw/
  config.py        → loads and validates .env, channels.txt and style.md
  errors.py        → StageError and the exit codes
  feed.py          → fetches and parses a channel's RSS feed, selects the candidates
  audio.py         → yt-dlp metadata and mp3 download, ffmpeg chunking
  transcription.py → the OpenRouter transcription request, returns the words of one chunk
  segments.py      → turns words into segments; no network, no database
  embedding.py     → the OpenRouter embeddings request
  essay.py         → the essay-writing agent
  db.py            → every SQL statement
  pipeline.py      → one function per stage, each for one video
  poll.py          → the lock, then the loops over channels, videos and stages
  site.py          → build_site(): the essay and Ask pages and their formatting helpers
  answering.py     → chat agent, transcript search, Ask endpoint, and standalone chat
  templates/       → essay list, essay, and shared chat markup
  static/          → integrated chat behavior and layout
tests/             → one test file per module tested, plus a sample feed XML
schema.sql
channels.txt
style.md
env.example        → template for .env
.env               → secrets and settings (git-ignored)
.poll.lock         → poll lock (git-ignored)
poll.log           → cron output (git-ignored)
```

Module rules:

- `main.py` holds no logic beyond argument parsing and turning a `StageError` into an exit code.
- `build_site()` and `build_chat()` take no arguments and call `load_settings()` themselves, so importing their modules has no side effects.
- `feed.py`, `audio.py`, `transcription.py`, `embedding.py`, `essay.py` and `db.py` each wrap one external system and do not import each other.
- `pipeline.py`, `poll.py`, `site.py` and `answering.py` combine them. `poll.py` calls `pipeline.py`, never the reverse.
- Only `config.py` reads environment variables and the settings files. The other modules receive values as arguments.
- Only `db.py` contains SQL. A write that touches several tables is one function using one connection and one transaction.
- The package is not installed. `main.py` imports it from the project root, and `pyproject.toml` sets pytest's `pythonpath` to `.`.

## Code style

Plain functions with type hints and a one-line docstring. Rows are plain dicts keyed by column name. There are two classes in the whole codebase: `StageError`, which carries the exit code and the stage name, and the essay output model.

Each module that wraps an external system catches that system's own errors and raises `StageError`. The poll catches it per video and channel so it can continue. The CLI uses it to set the exit code. The Ask endpoint uses it to return a retryable error to the browser.

```python
def select_candidates(
    entries: list[dict], tracking_since: datetime, stored_ids: set[str]
) -> list[dict]:
    """Return the entries published at or after tracking_since that are not stored yet, oldest first."""
    return [
        e
        for e in entries
        if e["published"] >= tracking_since and e["video_id"] not in stored_ids
    ]
```

A shortcut with a known limit gets a comment in this form: `# shortcut: <the limit>, <when to upgrade>`.

## Commits

Use short Conventional Commits: `<type>: <short imperative summary>` (optional scope when useful, e.g. `fix(feed): ...`).

- Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`.
- Imperative mood, lowercase, no trailing period, under 72 characters (prefer ~50).
- One line is enough; add a blank line and short body only when the *why* is not obvious from the diff.

Examples:

```
feat: add segment builder and diarized transcription
fix(feed): reject entries without a published date
refactor: move chunk length and model ID to constants
docs: add local setup and commit conventions
```

## Testing

- pytest, tests in `tests/`.
- Unit tests cover logic that has branches and needs no network:
  - `feed.py`: feed parsing against a saved feed XML, and candidate selection
  - `config.py`: `channels.txt` parsing, including the language code
  - `segments.py`: speaker changes, the 200-word limit, time offsets per chunk, the speaker label, an empty chunk
  - `site.py`: reading time, duration and age formatting
- yt-dlp, ffmpeg, OpenRouter and Supabase are not mocked. They are checked by one manual run: `uv run main.py transcribe <id of a short video with two speakers>`, then confirming the segments and the essay in the database and on the front page.

## Build order

Each step ends with something that can be checked.

1. (Done) Delete the superseded files and reduce `.env` to the four settings. Tests pass and `transcribe` still stores a transcript.
2. (Done) Apply `schema.sql` as described in "Database schema". Run `uv run main.py transcribe <video>` on a short video with two speakers. Check that Supabase has a `transcribed` video row and segments with text, timestamps and speaker labels.
3. (Done) Add `poll` with the lock, and the language code in `channels.txt`.
4. (Done) Add stage 2 and the `write` command. An essay row appears for a transcribed video.
5. (Done) Add stage 3. Segments of 20 words or more have vectors.
6. (Done) Add the front page.
7. (Done) Add the chat. A question about a transcribed video returns an answer with both links.

## Verified facts

Measured on 2026-11-20 through OpenRouter. Re-check before relying on them much later.

- `x-ai/grok-stt-2.0` returns word timestamps and a speaker index on every word in one response, with the request shown above. It costs about $0.10 per hour of audio. A 5-minute chunk took about 17 seconds.
- Its `segments` array is a single segment covering the whole chunk, with no speaker. Only `words` is useful.
- A top-level `diarize` field is rejected with HTTP 400 ("The selected model does not support diarize"). Diarization goes under `provider.options.xai`.
- On a 5-minute Italian conversation with people talking over each other, it found the two speakers and placed most turn boundaries within a word or two, but on one unclear stretch it repeated a phrase and then produced 40 words in Hebrew script. Sending `language: "it"` removed the Hebrew; that stretch was still unreliable.
- `google/gemini-3.5-transcribe` was rejected. It labelled all words with speakers on one call and a quarter of them on an identical repeat, dropped the last 20 to 28 seconds, and costs about $0.27 per hour.
- `openai/whisper-large-v3-turbo` cannot return speakers.
- `mongodb/voyage-4-lite` (checked 2026-11-21): the embeddings request shown above returns HTTP 200 with one 1024-float vector per input, each carrying its `index`. It costs $0.02 per million tokens, the same as `openai/text-embedding-3-small`, and accepts 32,000 tokens per input. A `dimensions` field accepts only 256, 512, 1024 or 2048; 1536 is rejected with HTTP 400.
- `yt-dlp` 2026.10.26 downloaded the test video on three later attempts after one `HTTP Error 403`, with no extra components and no Deno installed (Node and Bun were present). If downloads fail consistently on the VPS, check whether yt-dlp there needs a JavaScript runtime.
- `MarkdownIt()` with no arguments renders a `<script>` tag in its input unchanged. `MarkdownIt("commonmark", {"html": False})` escapes it.
- On the project's Supabase (checked 2026-11-21) the search path is `"$user", public, extensions`, so `'[1,2,3]'::vector` works without the `extensions.` prefix.

From documentation, not measured here:

- OpenRouter: providers time out after 60 seconds of processing per transcription request. This and the 17-second measurement are why chunks are 300 seconds.
- OpenRouter: outside OpenAI and Groq models, a transcription request is limited to 25 MB of audio, about 52 minutes at 64 kbps.
- PydanticAI: the four `to_web()` facts in "Chat".

## Boundaries

- Always: format code with `uvx ruff format` after each change; run `uv run pytest` before calling a change done; keep the module rules; keep both web apps on `127.0.0.1`.
- Ask first: adding a dependency that "Tech stack" does not list, changing the schema beyond what "Database schema" specifies, changing the transcription or embedding model, adding a setting, anything that spends more than a few cents of OpenRouter credit in testing.
- Never: commit `.env`, print the API key or the database URL, bind a web app to a public address, add authentication or accounts, mock the external services in tests.
