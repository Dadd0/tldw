"""Loads and validates the settings in .env and the channel IDs in channels.txt."""

import os
import re
from collections.abc import Mapping
from pathlib import Path

from dotenv import load_dotenv

from tldw.errors import CONFIG, StageError

CHANNELS_FILE = Path("channels.txt")
REQUIRED = ("OPENROUTER_API_KEY", "SUPABASE_DB_URL", "ESSAY_MODEL_ID", "CHAT_MODEL_ID")
CHANNEL_ID = re.compile(r"UC[A-Za-z0-9_-]{22}")


def load_settings(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return the settings keyed by variable name, reading .env when no mapping is given."""
    if env is None:
        load_dotenv()
        env = os.environ
    missing = [name for name in REQUIRED if not env.get(name)]
    if missing:
        raise StageError(CONFIG, "config", f"missing in .env: {', '.join(missing)}")
    return {name: env[name] for name in REQUIRED}


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
            raise StageError(
                CONFIG, "config", f"{path} line {number}: not a channel ID: {channel!r}"
            )
        if channel not in channels:
            channels.append(channel)
    return channels
