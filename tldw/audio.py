"""Fetches video metadata and the mp3 with yt-dlp, and splits the mp3 into chunks with ffmpeg."""

import logging
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import yt_dlp

from tldw.errors import DOWNLOAD, TRANSCRIPTION, StageError

MP3_BITRATE_KBPS = 64
CHUNK_SECONDS = 300
# yt-dlp prints its errors unless it has a logger, and the caller already reports them
LOGGER = logging.getLogger("yt_dlp")
LOGGER.addHandler(logging.NullHandler())
QUIET = {
    "quiet": True,
    "no_warnings": True,
    "noprogress": True,
    "color": "never",
    "logger": LOGGER,
}


def fetch_metadata(video: str) -> dict:
    """Return the ID, channel, title, duration and publish time of a video ID or URL."""
    try:
        with yt_dlp.YoutubeDL(QUIET) as ydl:
            info = ydl.extract_info(video, download=False)
    except yt_dlp.utils.DownloadError as e:
        raise StageError(DOWNLOAD, "metadata", str(e).removeprefix("ERROR: ")) from e
    if not info.get("duration"):
        raise StageError(
            DOWNLOAD, "metadata", f"{info['id']} has no duration (live or upcoming?)"
        )
    timestamp = info.get("timestamp")
    return {
        "video_id": info["id"],
        "channel_id": info["channel_id"],
        "channel_name": (
            info.get("channel") or info.get("uploader") or info["channel_id"]
        ),
        "title": info["title"],
        "duration_seconds": int(info["duration"]),
        "published_at": datetime.fromtimestamp(timestamp, UTC) if timestamp else None,
    }


def download_mp3(video_id: str, directory: Path) -> Path:
    """Download the video's audio into the directory as an mp3 and return its path."""
    options = QUIET | {
        "format": "bestaudio/best",
        "outtmpl": str(directory / "%(id)s.%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": str(MP3_BITRATE_KBPS),
            }
        ],
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
    except yt_dlp.utils.DownloadError as e:
        raise StageError(DOWNLOAD, "download", str(e).removeprefix("ERROR: ")) from e
    return directory / f"{video_id}.mp3"


def split_mp3(mp3: Path, *, max_seconds: int | None = None) -> list[Path]:
    """Split the start of the audio into chunks, up to the optional time limit."""
    # shortcut: cuts at fixed times so a word can be split across chunks, switch to silence detection if transcripts show it
    audio_options = ["-c", "copy"]
    if max_seconds is not None:
        audio_options = [
            "-af",
            f"atrim=duration={max_seconds}",
            "-c:a",
            "libmp3lame",
            "-b:a",
            f"{MP3_BITRATE_KBPS}k",
        ]
    command = [
        "ffmpeg",
        "-nostdin",
        "-loglevel",
        "error",
        "-i",
        str(mp3),
        "-f",
        "segment",
        "-segment_time",
        str(CHUNK_SECONDS),
        *audio_options,
        str(mp3.with_name(f"{mp3.stem}_%04d.mp3")),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True)
    except OSError as error:
        raise StageError(
            TRANSCRIPTION, "chunking", f"cannot start ffmpeg: {error}"
        ) from error
    chunks = sorted(mp3.parent.glob(f"{mp3.stem}_*.mp3"))
    if result.returncode != 0 or not chunks:
        raise StageError(
            TRANSCRIPTION,
            "chunking",
            result.stderr.strip() or "ffmpeg produced no chunks",
        )
    if max_seconds is not None:
        max_chunks = (max_seconds + CHUNK_SECONDS - 1) // CHUNK_SECONDS
        chunks = chunks[:max_chunks]

    return chunks
