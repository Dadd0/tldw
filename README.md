# TL;DW

![Python 3.14+](https://img.shields.io/badge/python-3.14+-3776AB?logo=python&logoColor=white)
![uv](https://img.shields.io/badge/uv-managed-DE5FE9?logo=uv&logoColor=white)
![Ruff](https://img.shields.io/badge/code%20style-ruff-D7FF64?logo=ruff&logoColor=black)
![Postgres + pgvector](https://img.shields.io/badge/postgres-pgvector-4169E1?logo=postgresql&logoColor=white)

TL;DW ("too long; didn't watch") turns talk-heavy YouTube videos into short standalone essays on a private Hacker News-style front page, plus a Q&A chat over every transcript with links back to the essay and video timestamp.

Single-user, self-hosted on one VPS behind an SSH tunnel. See [AGENTS.md](AGENTS.md) for the full specification and current build status.

## Requirements

- Python >= 3.14, [uv](https://docs.astral.sh/uv/)
- `ffmpeg`
- An [OpenRouter](https://openrouter.ai/) API key
- A Postgres database with `pgvector` (e.g. Supabase)

## Configuration

Create `.env` with four required variables:

```env
OPENROUTER_API_KEY=...
SUPABASE_DB_URL=...
ESSAY_MODEL_ID=...
CHAT_MODEL_ID=...
```

Add YouTube channel IDs to `channels.txt` (optionally followed by a two-letter language code) and customize essay style in `style.md`.

Initialize the database (safe to re-run):

```bash
psql "$SUPABASE_DB_URL" -f schema.sql
```

## Commands

```bash
uv run main.py poll                                                        # poll channels and run pipeline stages
uv run main.py transcribe <video-id-or-url> [--language it]                # process one video
uv run main.py write <video-id>                                            # rewrite one essay
uv run uvicorn --factory tldw.site:build_site --host 127.0.0.1 --port 8000 # front page
uv run uvicorn --factory tldw.answering:build_chat --host 127.0.0.1 --port 7932 # chat
uv run pytest                                                              # unit tests
```
