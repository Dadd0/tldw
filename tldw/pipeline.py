"""Processes one video end to end: metadata, download, chunking, transcription, storage."""

import tempfile
from pathlib import Path

from tldw.audio import CHUNK_SECONDS, download_mp3, fetch_metadata, split_mp3
from tldw.db import upsert_video
from tldw.errors import TRANSCRIPTION, StageError
from tldw.segments import build_segments
from tldw.transcription import transcribe

MIN_DURATION_SECONDS = 180


def process_video(
    video: str, settings: dict, skip_short: bool, language: str | None = None
) -> str:
    """Transcribe and store a video ID or URL, and return the status of the stored row."""
    metadata = fetch_metadata(video)
    if skip_short and metadata["duration_seconds"] < MIN_DURATION_SECONDS:
        upsert_video(
            settings["SUPABASE_DB_URL"],
            metadata | {"status": "skipped"},
            [],
        )
        return "skipped"

    with tempfile.TemporaryDirectory() as directory:
        mp3 = download_mp3(metadata["video_id"], Path(directory))
        words_by_chunk = [
            transcribe(chunk, settings["OPENROUTER_API_KEY"], language=language)
            for chunk in split_mp3(mp3)
        ]

    segments = build_segments(words_by_chunk, CHUNK_SECONDS)
    if not segments:
        raise StageError(TRANSCRIPTION, "transcription", "empty transcript")

    upsert_video(
        settings["SUPABASE_DB_URL"],
        metadata | {"status": "transcribed"},
        segments,
    )
    return "transcribed"
