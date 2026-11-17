"""Processes one video end to end: metadata, download, chunking, transcription, storage."""

import tempfile
from pathlib import Path

from yt_smart_transcribe.audio import download_mp3, fetch_metadata, split_mp3
from yt_smart_transcribe.db import upsert_video
from yt_smart_transcribe.transcription import transcribe

MIN_DURATION_SECONDS = 60


def process_video(video: str, settings: dict, skip_short: bool) -> str:
    """Transcribe and store a video ID or URL, and return the status of the stored row."""
    metadata = fetch_metadata(video)
    if skip_short and metadata["duration_seconds"] < MIN_DURATION_SECONDS:
        upsert_video(settings["SUPABASE_DB_URL"], metadata | {"status": "skipped", "transcript": None})
        return "skipped"
    with tempfile.TemporaryDirectory() as directory:
        mp3 = download_mp3(metadata["video_id"], Path(directory))
        texts = [
            transcribe(chunk, settings["OPENROUTER_API_KEY"], settings["TRANSCRIPTION_MODEL_ID"])
            for chunk in split_mp3(mp3, settings["CHUNK_SECONDS"])
        ]
    upsert_video(settings["SUPABASE_DB_URL"], metadata | {"status": "transcribed", "transcript": "\n".join(texts)})
    return "transcribed"
