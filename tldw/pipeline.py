"""Processes one video end to end: metadata, download, chunking, transcription, storage."""

import tempfile
from pathlib import Path

from tldw.audio import CHUNK_SECONDS, download_mp3, fetch_metadata, split_mp3
from tldw.db import upsert_video
from tldw.errors import TRANSCRIPTION, StageError, CONFIG
from tldw.segments import build_segments
from tldw.transcription import transcribe

MIN_DURATION_SECONDS = 180


def process_video(
    video: str,
    settings: dict,
    skip_short: bool,
    language: str | None = None,
    *,
    max_minutes: int | None = None,
) -> str:
    """Transcribe a video and either preview or store its segments."""
    if max_minutes is not None and max_minutes <= 0:
        raise StageError(CONFIG, "usage", "--max-minutes must be a positive integer")

    max_seconds = None if max_minutes is None else max_minutes * 60
    metadata = fetch_metadata(video)
    if (
        max_seconds is None
        and skip_short
        and metadata["duration_seconds"] < MIN_DURATION_SECONDS
    ):
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
            for chunk in split_mp3(mp3, max_seconds=max_seconds)
        ]

    segments = build_segments(words_by_chunk, CHUNK_SECONDS)
    if not segments:
        raise StageError(TRANSCRIPTION, "transcription", "empty transcript")

    if max_seconds is not None:
        for segment in segments:
            print(
                f"[{segment['start_seconds']:.2f}-{segment['end_seconds']:.2f}s] "
                f"{segment['speaker']}: {segment['text']}"
            )
        return "preview"

    upsert_video(
        settings["SUPABASE_DB_URL"],
        metadata | {"status": "transcribed"},
        segments,
    )
    return "transcribed"
