"""Find and transcribe new videos from followed channels."""

import sys
from pathlib import Path

from tldw.config import load_channels, load_settings
from tldw.db import (
    get_tracking_since,
    insert_channel,
    stored_video_ids,
    pending_essay_video_ids,
)
from tldw.errors import CONFIG, StageError
from tldw.feed import fetch_feed, first_tracking_since, select_candidates
from tldw.pipeline import transcribe_video, write_essay

LOCK_FILE = Path(".poll.lock")


def run_poll() -> int:
    """Run polling while holding a non-blocking exclusive lock."""
    try:
        import fcntl
    except ImportError as error:
        raise StageError(
            CONFIG, "poll", "poll requires Unix file locking (use Linux or WSL)"
        ) from error

    try:
        lock_file = LOCK_FILE.open("a")
    except OSError as error:
        raise StageError(CONFIG, "poll", f"cannot open {LOCK_FILE}: {error}") from error

    with lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        except OSError as error:
            raise StageError(
                CONFIG, "poll", f"cannot lock {LOCK_FILE}: {error}"
            ) from error

        settings = load_settings()
        return poll_channels(load_channels(), settings)


def poll_channels(
    channels: list[tuple[str, str | None]], settings: dict[str, str]
) -> int:
    """Process new videos and return the exit code of the first failure."""
    db_url = settings["SUPABASE_DB_URL"]
    exit_code = 0

    for channel_id, language in channels:
        try:
            entries = fetch_feed(channel_id)
            tracking_since = get_tracking_since(db_url, channel_id)
            if tracking_since is None:
                tracking_since = first_tracking_since(entries)
                insert_channel(db_url, channel_id, tracking_since)

            if not entries:
                continue

            stored_ids = stored_video_ids(
                db_url, [entry["video_id"] for entry in entries]
            )
            candidates = select_candidates(entries, tracking_since, stored_ids)
        except StageError as error:
            _log_failure(channel_id, error, settings)
            exit_code = exit_code or error.code
            continue

        for entry in candidates:
            video_id = entry["video_id"]
            try:
                transcribe_video(video_id, settings, skip_short=True, language=language)
            except StageError as error:
                _log_failure(video_id, error, settings)
                exit_code = exit_code or error.code
    try:
        pending_ids = pending_essay_video_ids(db_url)
    except StageError as error:
        _log_failure("poll", error, settings)
        return exit_code or error.code

    for video_id in pending_ids:
        try:
            write_essay(video_id, settings, replace=False)
        except StageError as error:
            _log_failure(video_id, error, settings)
            exit_code = exit_code or error.code
    return exit_code


def _log_failure(item_id: str, error: StageError, settings: dict[str, str]) -> None:
    """Print one failure with configured secrets redacted."""
    message = str(error)
    for name in ("SUPABASE_DB_URL", "OPENROUTER_API_KEY"):
        message = message.replace(settings[name], "[redacted]")
    message = " ".join(message.splitlines())
    print(f"FAILED {item_id} {error.stage}: {message}", file=sys.stderr)
