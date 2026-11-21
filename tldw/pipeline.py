"""Processes one video end to end: metadata, download, chunking, transcription, storage."""

import tempfile
from pathlib import Path

from tldw.audio import CHUNK_SECONDS, download_mp3, fetch_metadata, split_mp3
from tldw.config import load_style
from tldw.db import get_essay_source, save_essay, upsert_video
from tldw.errors import CONFIG, ESSAY, TRANSCRIPTION, StageError
from tldw.essay import generate_essay
from tldw.segments import build_segments
from tldw.transcription import transcribe

MIN_DURATION_SECONDS = 180


def transcribe_video(
    video: str,
    settings: dict,
    skip_short: bool,
    language: str | None = None,
    *,
    max_minutes: int | None = None,
) -> str | None:
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
        return None

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
        return None

    upsert_video(
        settings["SUPABASE_DB_URL"],
        metadata | {"status": "transcribed"},
        segments,
    )
    return metadata["video_id"]


def write_essay(video_id: str, settings: dict[str, str], *, replace: bool) -> None:
    """Generate and save an essay for one stored transcript."""
    db_url = settings["SUPABASE_DB_URL"]
    source = get_essay_source(db_url, video_id)
    if not source:
        raise StageError(CONFIG, "write", "video is not stored with status transcribed")

    video = source[0]
    if video["idx"] is None:
        raise StageError(ESSAY, "essay", "stored transcript has no segments")

    essay = generate_essay(
        video["title"],
        video["channel_name"],
        source,
        style=load_style(),
        model_id=settings["ESSAY_MODEL_ID"],
        api_key=settings["OPENROUTER_API_KEY"],
    )
    if not save_essay(
        db_url, video_id, source, essay.title, essay.body, replace=replace
    ):
        raise StageError(ESSAY, "essay", "transcript changed during essay generation")


def process_video(
    video: str,
    settings: dict[str, str],
    *,
    language: str | None = None,
    max_minutes: int | None = None,
) -> None:
    """Transcribe a video and write its essay after saving the transcript."""
    video_id = transcribe_video(
        video,
        settings,
        skip_short=False,
        language=language,
        max_minutes=max_minutes,
    )
    if video_id is not None:
        write_essay(video_id, settings, replace=False)
