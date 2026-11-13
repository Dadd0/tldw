"""Loads and validates the settings in .env and the channel IDs in channels.txt."""

import os
import re
from collections.abc import Mapping
from pathlib import Path

from dotenv import load_dotenv

from yt_smart_transcribe.errors import CONFIG, StageError

CHANNELS_FILE = Path("channels.txt")
REQUIRED = ("OPENROUTER_API_KEY", "TRANSCRIPTION_MODEL_ID", "SUPABASE_URL", "SUPABASE_KEY")
DEFAULTS = {"POLL_INTERVAL_MINUTES": 30, "CHUNK_SECONDS": 600}
CHANNEL_ID = re.compile(r"UC[A-Za-z0-9_-]{22}")


def load_settings(env: Mapping[str, str] | None = None) -> dict:
    """Return the settings keyed by variable name, reading .env when no mapping is given."""
    if env is None:
        load_dotenv()
        env = os.environ
    missing = [name for name in REQUIRED if not env.get(name)]
    if missing:
        raise StageError(CONFIG, "config", f"missing in .env: {', '.join(missing)}")
    settings: dict = {name: env[name] for name in REQUIRED}
    for name, default in DEFAULTS.items():
        raw = env.get(name) or str(default)
        if not raw.isdecimal() or int(raw) == 0:
            raise StageError(CONFIG, "config", f"{name} must be a positive integer, got {raw!r}")
        settings[name] = int(raw)
    return settings


def load_channels(path: Path = CHANNELS_FILE) -> list[str]:
    """Return the channel IDs in the file, without duplicates, in file order."""
    try:
        lines = path.read_text().splitlines()
    except OSError as e:
        raise StageError(CONFIG, "config", f"cannot read {path}: {e}") from e
    channels = []
    for number, line in enumerate(lines, 1):
        channel = line.split("#")[0].strip()
        if not channel:
            continue
        if not CHANNEL_ID.fullmatch(channel):
            raise StageError(CONFIG, "config", f"{path} line {number}: not a channel ID: {channel!r}")
        if channel not in channels:
            channels.append(channel)
    return channels
